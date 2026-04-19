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

## 1. System Context (What runs where)

- **F1 24 Game** runs locally and emits telemetry via **UDP**.
- **Backend service** runs locally:
  - Listens to UDP packets
  - Parses packets into typed events
  - Publishes events to an internal event bus
  - Maintains a session state snapshot
  - Streams events/state to browser clients over WebSockets
- **Frontend dashboard** runs in a browser and connects to the backend over **WebSocket** (and optionally HTTP for initial assets/config).

---

## 2. High-Level Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│                        F1 24 GAME (UDP)                          │
└─────────────────────┬───────────────────────────────────────────┘
                      │ UDP packets (binary)
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│  [1] TELEMETRY INGESTOR                                          │
│  ┌─────────────────┐    ┌──────────────────────────────────┐    │
│  │  UDP Listener   │───▶│  Packet Parser / Deserializer    │    │
│  │  (raw bytes)    │    │  (typed structs per packet type) │    │
│  └─────────────────┘    └──────────────────────────────────┘    │
└─────────────────────────────────┬──���────────────────────────────┘
                                  │ Typed telemetry events
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  [2] IN-PROCESS EVENT BUS (Pub/Sub)                              │
│      Topics: session, lap_data, car_telemetry, car_status,       │
│              motion, participants, final_classification, ...     │
└────────────────┬────────────────────────────────────────────────┘
                 │ Subscriptions
        ┌────────┴──────────┐
        ▼                   ▼
┌───────────────┐   ┌────────────────────┐
│  [3a] Event   │   │  [3b] State Store  │
│  Processors   │   │  (current snapshot │
│  /Aggregators │   │   of session data) │
└───────┬───────┘   └────────┬───────────┘
        └─────────┬──────────┘
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  [4] WEBSOCKET GATEWAY                                           │
│  - Manages browser connections                                   │
│  - Sends initial snapshot on connect                             │
│  - Broadcasts updates (optionally throttled)                     │
└──────────────────────────────┬──────────────────────────────────┘
                               │ WebSocket (ws://)
                               ▼
┌─────────────────���───────────────────────────────────────────────┐
│  [5] FRONTEND DASHBOARD (Browser)                                │
│  - Real-time UI: gauges, charts, track map, timing, standings    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Components and Responsibilities

### [1] Telemetry Ingestor

**Responsibility:** Turn raw UDP packets into typed domain events.

**Subcomponents:**
- **UDP Listener**
  - Binds to the configured UDP port (commonly `20777`)
  - Receives datagrams (binary payloads)
  - Passes raw bytes to parser
- **Packet Parser / Deserializer**
  - Reads the packet header first to determine packet type (`packetId`)
  - Decodes the payload into a typed structure for that packet type
  - Emits a normalized internal event object

**Inputs:**
- UDP datagrams (binary)

**Outputs:**
- `TelemetryEvent` objects published to the Event Bus (topic-based)

**Notes:**
- Parsing must match the F1 24 UDP spec.
- Include enough metadata in events to correlate:
  - timestamp (local monotonic time and/or game session time if available)
  - packet type
  - player car index (when relevant)
  - session identifier fields (when relevant)

---

### [2] In-Process Event Bus (Pub/Sub)

**Responsibility:** Decouple producers (ingestor/parser) from consumers (processors, state store, websocket gateway).

**Key properties:**
- In-memory, single-process pub/sub
- Topic-based routing, typically aligning with packet types:
  - `session`
  - `lap_data`
  - `car_telemetry`
  - `car_status`
  - `motion`
  - `participants`
  - `final_classification`
  - etc.

**Inputs:**
- Typed telemetry events

**Outputs:**
- Delivered events to all subscribers of a topic

**Non-goals:**
- Durable storage (not a persistent queue)
- Cross-machine distribution

---

### [3a] Event Processors / Aggregators

**Responsibility:** Compute derived metrics and higher-level events from raw telemetry.

**Examples of derived outputs:**
- Lap delta vs. best lap / previous lap
- Sector time history and trends
- Tyre temperature/wear trends (rate-of-change)
- DRS usage timeline
- Speed trace over last N seconds

**Inputs:**
- Raw telemetry events from the Event Bus

**Outputs:**
- Derived events published back to the Event Bus (recommended) and/or updates to State Store

**Design guidance:**
- Prefer small, composable processors.
- Each processor should be testable with recorded telemetry replays.

---

### [3b] State Store (Session Snapshot Cache)

**Responsibility:** Maintain the latest known values needed to render the dashboard immediately.

**Why this exists:**
- New browser clients may connect mid-session.
- They need an initial snapshot instantly (not “wait until the next packet arrives”).

**Inputs:**
- Subscribes to relevant topics on the Event Bus (raw + derived)

**Outputs:**
- Read access for the WebSocket Gateway (initial snapshot and/or periodic full sync)

**Data model shape:**
- A hierarchical object keyed by:
  - session id / session UID (if available)
  - packet/topic name
  - car index / participant id (where applicable)
- Stores “latest value” + timestamp for each tracked field.

---

### [4] WebSocket Gateway

**Responsibility:** Bridge backend events to frontend clients in real time.

**Core behaviors:**
- Accept WebSocket connections from browsers
- On client connect:
  - Send current State Store snapshot (or a subset relevant to the UI)
- Stream updates:
  - Subscribe to Event Bus topics and broadcast events to clients
  - Optionally throttle high-frequency streams (e.g., motion at 60Hz)

**Inputs:**
- Event Bus subscriptions
- State Store snapshot reads

**Outputs:**
- WebSocket messages to connected clients (JSON-serialized)

**Recommended message categories:**
- `snapshot` (initial full state)
- `update` (incremental events)
- `meta` (connection status, version, config)

---

### [5] Frontend Dashboard (Browser)

**Responsibility:** Render real-time telemetry and derived insights.

**Core UI panels (suggested):**
- Car telemetry: speed, throttle, brake, gear, RPM, DRS, ERS
- Timing: current lap, best lap, delta, sector splits
- Tyres: temps, wear per corner
- Track map: car position and trajectory (from motion data)
- Standings / participants: positions and gaps

**Inputs:**
- WebSocket messages from the backend

**Outputs:**
- Interactive dashboard UI in the browser

**Frontend guidance:**
- Prefer state normalization on the client:
  - apply `snapshot` then incremental `update` messages
- Smooth animations and decimation for high-frequency charts.

---

## 4. Data Flow (Sequence)

1. Game emits UDP telemetry packet.
2. UDP Listener receives packet bytes.
3. Parser decodes header → identifies type → deserializes payload into typed object.
4. Ingestor publishes `TelemetryEvent` to Event Bus topic (e.g., `car_telemetry`).
5. Event Bus delivers event to:
   - State Store (update latest snapshot)
   - Event Processors (derive metrics, publish derived events)
   - WebSocket Gateway (broadcast incremental updates)
6. WebSocket Gateway sends:
   - `snapshot` on new connection
   - `update` messages continuously
7. Frontend renders dashboard, updating panels in real time.

---

## 5. Technology Notes (Non-binding)

This architecture works with multiple stacks; choose one and stay consistent.

**Common backend options:**
- Node.js + TypeScript: UDP (`dgram`), pub/sub (`EventEmitter`), WebSocket (`ws` or Socket.IO)
- Python: UDP (`socket`), events (lightweight pub/sub), WebSocket (FastAPI + websockets)

**Common frontend options:**
- React or Svelte + Vite
- Charts: uPlot (high-performance) or Chart.js
- Track map: Canvas or D3

---

## 6. Extensions / Future Enhancements (Optional)

- **Telemetry recording and replay**
  - Store raw UDP packets or parsed events to disk
  - Replay sessions for UI development and regression tests
- **Config UI**
  - Toggle topics, sampling rate, and panel visibility
- **Multi-client support**
  - Multiple dashboards connected simultaneously
- **Profiles**
  - Race vs. Time Trial presets (different panels and update rates)