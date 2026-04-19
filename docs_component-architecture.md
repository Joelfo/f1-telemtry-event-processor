# F1 24 Event-Driven Real-Time Telemetry Dashboard — Component Architecture

**Date:** 2026-04-19 (updated)  
**Scope:** Local machine app that ingests F1 24 UDP telemetry from the game running on the same machine and renders a real-time dashboard in a web browser.  
**Primary goals:** Low latency, clear separation of concerns, event-driven design, easy to extend with new metrics and UI panels.

---

## 1. System Context (What runs where)

- **F1 24 Game** runs locally and emits telemetry via **UDP**.
- **Telemetry Ingestor** (`f1-telemetry-ingestor`) runs locally:
  - Listens to UDP packets
  - Parses packets into typed events
  - Serializes events with MessagePack
  - Publishes to Redis channels
- **Redis** acts as the message broker — the event bus between all backend components.
- **Event Processor** (separate service / repository) subscribes to Redis channels:
  - Derives higher-level metrics
  - Maintains a session state snapshot
  - Streams events/state to browser clients over WebSocket
- **Frontend dashboard** runs in a browser and connects over **WebSocket**.

---

## 2. High-Level Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│                        F1 24 GAME (UDP)                          │
└─────────────────────┬───────────────────────────────────────────┘
                      │ UDP packets (binary, port 20777)
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│  [1] TELEMETRY INGESTOR  (f1-telemetry-ingestor repo)           │
│  ┌─────────────────┐    ┌──────────────────────────────────┐    │
│  │  UDP Listener   │───▶│  Packet Parser / Deserializer    │    │
│  │  (asyncio)      │    │  (struct, player-car slice)      │    │
│  └─────────────────┘    └──────────────┬─────────────────-┘    │
│                                         │ TelemetryEvent        │
│                          ┌──────────────▼──────────────────┐   │
│                          │  Serializer (MessagePack, v=1)  │   │
│                          └──────────────┬───────────────────┘   │
└─────────────────────────────────────────┼───────────────────────┘
                                          │ PUBLISH topic <bytes>
                                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  [2] REDIS PUB/SUB (message broker)                              │
│      Channels: car_telemetry · lap_data · car_status · motion_ex │
│                session · event · session_history · car_damage    │
│      Encoding: MessagePack (schema v=1, see docs_message-schema) │
└────────────────┬────────────────────────────────────────────────┘
                 │ SUBSCRIBE
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  [3] EVENT PROCESSOR  (separate repository)                      │
│  ┌────────────────┐   ┌────────────────────┐                    │
│  │  Processors /  │   │  State Store       │                    │
│  │  Aggregators   │   │  (session snapshot)│                    │
│  └───────┬────────┘   └────────┬───────────┘                    │
└──────────┼─────────────────────┼──────────────────────────────-┘
           └──────────┬──────────┘
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│  [4] WEBSOCKET GATEWAY                                           │
│  - Manages browser connections                                   │
│  - Sends initial snapshot on connect                             │
│  - Broadcasts updates (optionally throttled)                     │
└──────────────────────────────┬──────────────────────────────────┘
                               │ WebSocket (ws://)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  [5] FRONTEND DASHBOARD (Browser)                                │
│  - Real-time UI: gauges, charts, track map, timing, standings    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Components and Responsibilities

### [1] Telemetry Ingestor

**Repository:** `f1-telemetry-ingestor`  
**Responsibility:** Turn raw UDP packets into MessagePack-encoded events published to Redis.

**Subcomponents:**
- **UDP Listener** (`udp_listener.py`)
  - Binds to `0.0.0.0:20777` (configurable via `UDP_HOST` / `UDP_PORT` env vars)
  - Receives datagrams via `asyncio.DatagramProtocol`
  - Schedules the async packet handler via `asyncio.ensure_future` — never blocks the socket loop
- **Packet Parser** (`packet_parser.py`)
  - Reads the 29-byte common header to determine `packetId`
  - Dispatches to the appropriate per-type parser
  - Validates minimum packet size before parsing
  - Silently drops unknown, unregistered, or malformed packets
- **Per-type parsers** (`packets/`)
  - Extract only the player's car entry from 22-car arrays (by `player_car_index`)
  - Return a frozen `@dataclass` payload (e.g. `PlayerCarTelemetry`)
- **Serializer** (`serializer.py`)
  - Calls `dataclasses.asdict()` on the payload — field names are preserved as-is
  - Encodes the event envelope + payload with MessagePack (`use_bin_type=True`)
  - Embeds schema version `v=1` for future-proofing
- **Redis Event Bus** (`redis_event_bus.py`)
  - Uses `redis.asyncio` — shares the ingestor's event loop, no threads
  - Publishes encoded bytes to the channel named by `event.topic`
- **Orchestrator** (`ingestor.py`)
  - Wires listener → parser → bus
  - Fault-isolated: a failing bus publish never crashes the UDP listener

**Inputs:** UDP datagrams (binary)  
**Outputs:** MessagePack blobs published to Redis Pub/Sub channels

**Running:**
```
python -m f1_ingestor              # production (→ Redis)
python -m f1_ingestor --bus console --topics car_telemetry --throttle 0.5  # functional test
```

**Environment variables:**

| Variable | Default | Description |
|---|---|---|
| `UDP_HOST` | `0.0.0.0` | Local interface to bind |
| `UDP_PORT` | `20777` | UDP port |
| `REDIS_HOST` | `localhost` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `LOG_LEVEL` | `INFO` | Python logging level |

---

### [2] Redis Pub/Sub (Event Bus)

**Responsibility:** Decouple the ingestor from all downstream consumers, allowing each to be developed and deployed independently.

**Key properties:**
- Fire-and-forget (no acknowledgement, no persistence) — matches UDP's lossy nature
- Sub-millisecond latency on localhost
- Multiple consumers can subscribe to the same channel independently
- The ingestor does not need to know if any consumer is up

**Channels (Tier 1, currently active):**

| Channel | Packet ID | Rate |
|---|---|---|
| `car_telemetry` | 6 | up to 60 Hz |
| `lap_data` | 2 | up to 60 Hz |
| `car_status` | 7 | up to 60 Hz |
| `motion_ex` | 13 | up to 60 Hz |

**Message format:** MessagePack map. Full schema in [docs_message-schema.md](docs_message-schema.md).  
**Event field reference:** [docs_telemetry-event-spec.md](docs_telemetry-event-spec.md).

---

### [3] Event Processor (separate repository)

**Responsibility:** Subscribe to Redis channels, derive higher-level metrics, maintain a session state snapshot, and expose data to the WebSocket Gateway.

**Subcomponents:**
- **Processors / Aggregators**
  - Subscribe to one or more Redis channels
  - Deserialize MessagePack events using the schema in `docs_message-schema.md`
  - Compute derived metrics (lap delta, tyre trends, ERS usage, etc.)
  - Publish derived events back to Redis (recommended) and/or update the State Store
- **State Store**
  - Maintains the latest known values per topic
  - Provides an initial snapshot for new WebSocket clients

**Inputs:** MessagePack blobs from Redis Pub/Sub channels  
**Outputs:** Derived events and State Store updates

**Design guidance:**
- Always check `v` (schema version) on every message and reject if unexpected.
- Use `overall_frame_identifier` for ordering — `frame_identifier` rewinds after flashbacks.
- Reset all state when `session_uid` changes — this signals a new game session.
- See [docs_telemetry-event-spec.md](docs_telemetry-event-spec.md) for field semantics, valid ranges, and recommended patterns.

---

### [4] WebSocket Gateway

**Responsibility:** Bridge backend events to frontend clients in real time.

**Core behaviors:**
- Accept WebSocket connections from browsers
- On client connect: send current State Store snapshot
- Stream updates: broadcast event processor outputs to clients
- Optionally throttle high-frequency streams (e.g. 60 Hz → 10 Hz for the UI)

**Inputs:** Event Processor outputs + State Store reads  
**Outputs:** WebSocket messages to connected clients (JSON)

**Recommended message categories:**
- `snapshot` — initial full state on connect
- `update` — incremental events
- `meta` — connection status, version, config

---

### [5] Frontend Dashboard (Browser)

**Responsibility:** Render real-time telemetry and derived insights.

**Core UI panels (suggested):**
- Car telemetry: speed, throttle, brake, gear, RPM, DRS, ERS
- Timing: current lap, best lap, delta, sector splits
- Tyres: temps, wear per corner
- Track map: car position (from motion data)
- Standings / gaps

**Inputs:** WebSocket messages from the backend  
**Outputs:** Interactive dashboard UI

**Frontend guidance:**
- Apply `snapshot` first, then apply incremental `update` messages on top.
- Smooth animations and decimation for high-frequency charts.

---

## 4. Data Flow (Sequence)

1. Game emits UDP telemetry datagram.
2. UDP Listener receives bytes; schedules `_handle_raw_packet` as an asyncio task.
3. Packet Parser decodes header → identifies type → deserializes player's payload into a frozen dataclass.
4. Serializer converts the `TelemetryEvent` to a MessagePack blob (schema `v=1`).
5. `RedisEventBus.publish()` calls `await redis.publish(topic, blob)`.
6. Redis delivers the blob to all subscribers of that channel.
7. Event Processor deserializes the blob, computes derived metrics, updates State Store.
8. WebSocket Gateway sends `snapshot` on new connections and `update` messages continuously.
9. Frontend renders the dashboard in real time.

---

## 5. Technology Stack

| Layer | Technology |
|---|---|
| UDP reception | Python `asyncio.DatagramProtocol` |
| Binary parsing | Python `struct.Struct` (little-endian, pre-compiled) |
| Event envelope | Python `@dataclass(frozen=True)` |
| Serialization | MessagePack (`msgpack` + `hiredis`) |
| Message broker | Redis Pub/Sub (`redis.asyncio`) |
| Event Processor | TBD (separate repository) |
| WebSocket Gateway | TBD |
| Frontend | TBD |

---

## 6. Extensions / Future Enhancements (Optional)

- **Telemetry recording and replay**
  - Store raw UDP packets or Redis messages to disk
  - Replay sessions for UI development and regression tests
- **Tier 2 / Tier 3 packet support**
  - Session, Event, Session History, Car Damage parsers (stubs exist)
- **Config UI**
  - Toggle topics, sampling rate, and panel visibility
- **Multi-client support**
  - Multiple dashboards connected simultaneously
- **Profiles**
  - Race vs. Time Trial presets (different panels and update rates)

---

## 7. Event Processor Output Contract (Release 1: Main Player Car Only)

This section defines the exact outputs produced by the Event Processor for the first release.

### 7.1 Scope and Assumptions

- Scope is restricted to the main player car only.
- Inputs may still come from multiple topics, but outputs represent only the player car state.
- Output encoding should match the current pipeline convention: MessagePack with schema versioning.

### 7.2 Output Types

The Event Processor produces three output classes:

1. **Derived events (stream):** higher-level metrics computed from raw telemetry.
2. **State updates (stream):** partial patches to the latest session snapshot.
3. **Snapshot (read model):** full in-memory state served to new WebSocket clients.

### 7.3 Redis Channels (Release 1)

| Channel | Purpose | Frequency |
|---|---|---|
| `ep.r1.player.derived.lap_metrics` | Timing metrics for current lap and deltas | up to 10 Hz |
| `ep.r1.player.derived.car_metrics` | Normalized live car metrics (speed, controls, rpm, drs, ers) | up to 20 Hz |
| `ep.r1.player.derived.tyre_metrics` | Tyre temperatures/wear and short-term trend | up to 5 Hz |
| `ep.r1.player.state.patch` | Incremental patch updates for snapshot state | up to 20 Hz |
| `ep.r1.player.meta` | Session lifecycle and processor metadata | event-driven |

Notes:
- Prefix `ep.r1` identifies Event Processor release 1 contract.
- The WebSocket Gateway can subscribe to all channels above and rebroadcast as JSON.

### 7.4 Common Envelope (all channels)

Every output message must include the same envelope fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `v` | int | yes | Schema version. Release 1 value: `1` |
| `type` | str | yes | Message type discriminator |
| `session_uid` | int | yes | Session identifier from telemetry |
| `overall_frame_identifier` | int | yes | Monotonic frame id for ordering |
| `ts_monotonic_ns` | int | yes | Local monotonic timestamp in nanoseconds |
| `player_car_index` | int | yes | Player car index copied from source events |
| `payload` | map | yes | Type-specific content |

Ordering and reset rules:
- Always order messages by `overall_frame_identifier`.
- Ignore out-of-order messages where `overall_frame_identifier` is older than the last processed frame.
- On `session_uid` change, clear all in-memory state and publish a `session_reset` meta event.

### 7.5 Derived Message Schemas

#### A) `lap_metrics` (`type = "lap_metrics"`)

`payload` fields:

| Field | Type | Description |
|---|---|---|
| `lap_number` | int | Current lap number |
| `current_lap_time_ms` | int | Elapsed time in current lap |
| `last_lap_time_ms` | int\|null | Completed last lap time |
| `best_lap_time_ms` | int\|null | Best lap in current session |
| `delta_to_best_ms` | int\|null | `current_lap_time_ms - best_reference_at_same_point` (or null if unavailable) |
| `delta_to_last_ms` | int\|null | Delta versus previous lap reference |
| `sector` | int | Current sector (1, 2, 3) |
| `sector1_time_ms` | int\|null | Sector 1 time when available |
| `sector2_time_ms` | int\|null | Sector 2 time when available |
| `pit_status` | str | `none`, `pitting`, `in_pit_area` |

#### B) `car_metrics` (`type = "car_metrics"`)

`payload` fields:

| Field | Type | Description |
|---|---|---|
| `speed_kph` | int | Vehicle speed |
| `throttle_pct` | float | `throttle * 100` |
| `brake_pct` | float | `brake * 100` |
| `steer_pct` | float | `steer * 100` (signed) |
| `gear` | int | Current gear |
| `engine_rpm` | int | Engine RPM |
| `drs_enabled` | bool | DRS currently active |
| `ers_store_energy_j` | float | ERS battery energy |
| `ers_deploy_mode` | int | Game ERS deploy mode enum |
| `ers_harvest_mguk_j` | float | Current MGU-K harvest |
| `ers_deployed_this_lap_j` | float | Total ERS deployed this lap |

#### C) `tyre_metrics` (`type = "tyre_metrics"`)

`payload` fields:

| Field | Type | Description |
|---|---|---|
| `surface_temp_c` | map | `{ "rl": int, "rr": int, "fl": int, "fr": int }` |
| `inner_temp_c` | map | `{ "rl": int, "rr": int, "fl": int, "fr": int }` |
| `wear_pct` | map | `{ "rl": int, "rr": int, "fl": int, "fr": int }` |
| `avg_surface_temp_c` | float | Mean of four corners |
| `avg_wear_pct` | float | Mean of four corners |
| `wear_rate_pct_per_min` | float\|null | Rolling rate-of-change over short window |

### 7.6 State Patch Schema (`ep.r1.player.state.patch`)

`type = "state_patch"`

`payload` fields:

| Field | Type | Description |
|---|---|---|
| `path` | str | Dot path in snapshot (example: `player.car.speed_kph`) |
| `value` | any | New value to set |
| `source_type` | str | Producer message type (`car_metrics`, `lap_metrics`, etc.) |

Patch semantics:
- Each message may include one patch only (simple and explicit for release 1).
- Consumers apply patches in message order.

### 7.7 Meta Schema (`ep.r1.player.meta`)

`payload` fields:

| Field | Type | Description |
|---|---|---|
| `event` | str | `session_started`, `session_reset`, `processor_started`, `processor_heartbeat` |
| `details` | map | Optional metadata for diagnostics |

### 7.8 In-Memory Snapshot Shape (served on WS connect)

Recommended snapshot structure:

```json
{
  "v": 1,
  "session_uid": 123456789,
  "player_car_index": 0,
  "updated_at_ns": 0,
  "player": {
    "car": {
      "speed_kph": 0,
      "throttle_pct": 0,
      "brake_pct": 0,
      "steer_pct": 0,
      "gear": 0,
      "engine_rpm": 0,
      "drs_enabled": false,
      "ers_store_energy_j": 0
    },
    "lap": {
      "lap_number": 0,
      "current_lap_time_ms": 0,
      "last_lap_time_ms": null,
      "best_lap_time_ms": null,
      "delta_to_best_ms": null,
      "delta_to_last_ms": null,
      "sector": 1
    },
    "tyres": {
      "surface_temp_c": { "rl": 0, "rr": 0, "fl": 0, "fr": 0 },
      "inner_temp_c": { "rl": 0, "rr": 0, "fl": 0, "fr": 0 },
      "wear_pct": { "rl": 0, "rr": 0, "fl": 0, "fr": 0 },
      "avg_surface_temp_c": 0,
      "avg_wear_pct": 0,
      "wear_rate_pct_per_min": null
    }
  }
}
```

### 7.9 WebSocket Mapping (for Gateway)

- On connect: emit `snapshot` using the full in-memory snapshot.
- During session: emit `update` per derived/state/meta message.
- Message envelope to browser can be:
  - `category`: `snapshot` | `update` | `meta`
  - `topic`: channel name
  - `data`: decoded output payload + envelope metadata

### 7.10 Release 1 Non-goals

- No multi-car standings model in Event Processor outputs.
- No historical persistence in Redis (Pub/Sub only).
- No replay API in this release.

---