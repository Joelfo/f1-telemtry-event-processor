# F1 24 Event Processor — Implementation Plan (Release 1)

**Date:** 2026-04-19  
**Scope:** Build the Event Processor as a Python service for **main player car only**, consuming Redis pub/sub telemetry and producing the Release 1 output contract.

---

## 1) Objectives

- Implement a reliable, low-latency Event Processor service in Python.
- Consume raw telemetry channels from Redis and validate input schema (`v=1`).
- Consume and validate the full telemetry envelope fields required by the spec:
  - `v`, `packet_type`, `session_uid`, `session_time`, `frame_identifier`, `overall_frame_identifier`, `player_car_index`, `car_idx`, `ingested_at`, `payload`.
- Produce Release 1 outputs defined in `docs_component-architecture.md` section 7:
  - `ep.r1.player.derived.lap_metrics`
  - `ep.r1.player.derived.car_metrics`
  - `ep.r1.player.derived.tyre_metrics`
  - `ep.r1.player.state.patch`
  - `ep.r1.player.meta`
- Maintain in-memory snapshot for WebSocket bootstrap use.

---

## 2) Release 1 Boundaries

### In scope

- Main player car outputs only.
- Processing of these input topics: `car_telemetry` (packet 6), `lap_data` (packet 2), `car_status` (packet 7), `motion_ex` (packet 13).
- Envelope enforcement, ordering by `overall_frame_identifier`, session reset by `session_uid`.
- MessagePack decode/encode with strict validation and defensive failure handling.
- Correct handling of spec enums and indexes:
  - `lap_data.sector`: 0=S1, 1=S2, 2=S3.
  - `lap_data.pit_status`: 0=none, 1=pitting, 2=in pit area.
  - Wheel array order is RL, RR, FL, FR.

### Out of scope

- Multi-car standings and opponent analytics.
- Persistent storage/replay API.
- WebSocket server implementation (this processor only publishes and holds snapshot).

---

## 3) Proposed Project Structure

```text
f1_event_processor/
  src/
    ep/
      app.py
      config.py
      logging.py
      contracts/
        envelope.py
        outputs.py
      bus/
        redis_subscriber.py
        redis_publisher.py
        codec_msgpack.py
      state/
        snapshot_store.py
        session_guard.py
      processors/
        car_metrics_processor.py
        lap_metrics_processor.py
        tyre_metrics_processor.py
        patch_emitter.py
      pipeline/
        router.py
        orchestrator.py
      diagnostics/
        heartbeat.py
        counters.py
  tests/
    unit/
    integration/
  pyproject.toml
  README.md
```

---

## 4) Implementation Phases

### Input Contract Notes (must drive implementation)

- Redis topic identifies stream; topic is **not** part of the unpacked event envelope.
- Validate that topic and envelope `packet_type` are consistent:
  - `lap_data` ↔ `packet_type=2`
  - `car_telemetry` ↔ `packet_type=6`
  - `car_status` ↔ `packet_type=7`
  - `motion_ex` ↔ `packet_type=13`
- For Tier-1 inputs, `car_idx` is expected to be `null`.
- Use `overall_frame_identifier` for ordering; do not order by `frame_identifier` due to flashbacks.

## Phase 0 — Bootstrap (Project + Tooling)

**Goal:** Create runnable Python service skeleton with quality gates.

### Tasks

- Initialize Python project (`pyproject.toml`) and package layout.
- Add dependencies:
  - runtime: `redis`, `msgpack`, `pydantic` (or dataclasses + validators), `structlog`/`logging`.
  - test: `pytest`, `pytest-asyncio`, `fakeredis` (or test redis), `coverage`.
- Add lint/format/type tooling (e.g., `ruff`, `black`, optional `mypy`).
- Add `.env.example` and config loading for Redis and log settings.

### Deliverables

- Service starts and idles with no subscriptions active.
- CI/local checks pass (`lint`, `test` placeholder).

### Exit criteria

- `python -m ep.app` starts cleanly.
- Basic health log line on startup.

---

## Phase 1 — Core Bus and Contracts

**Goal:** Implement transport and schema primitives used by all processors.

### Tasks

- Implement MessagePack codec for decode/encode with clear error types.
- Implement input envelope validator:
  - require spec fields (`v`, `packet_type`, `session_uid`, `session_time`, `frame_identifier`, `overall_frame_identifier`, `player_car_index`, `car_idx`, `ingested_at`, `payload`).
  - validate Redis topic ↔ `packet_type` mapping.
  - validate `car_idx is null` for Tier-1 topics.
  - reject unsupported schema versions.
- Implement output envelope builder with mandatory fields:
  - `v`, `type`, `session_uid`, `overall_frame_identifier`, `ts_monotonic_ns`, `player_car_index`, `payload`.
- Implement async Redis subscriber/publisher wrappers.

### Deliverables

- Reusable contract layer and Redis IO layer.

### Exit criteria

- Unit tests for encode/decode and schema validation pass.
- Corrupt payloads are dropped with diagnostic logs (no crash).

---

## Phase 2 — Session Guard + State Store

**Goal:** Add ordering and session lifecycle correctness.

### Tasks

- Implement `session_guard`:
  - tracks latest `overall_frame_identifier`.
  - ignores out-of-order frames.
  - detects `session_uid` change and triggers full reset event.
- Keep `session_time` in state for diagnostics and timeline context, but do not use it as the primary ordering key.
- Implement in-memory snapshot store matching section 7.8 structure.
- Implement state patch application helper for `path` + `value` updates.

### Deliverables

- Stable, queryable snapshot state.
- Session reset behavior publishing `ep.r1.player.meta` with `session_reset`.

### Exit criteria

- Unit tests cover reset and out-of-order scenarios.
- Snapshot returns defaults after reset.

---

## Phase 3 — Derived Processors (Player Car)

**Goal:** Produce all Release 1 derived channels.

### Tasks

- `car_metrics_processor`
  - derive `speed_kph`, controls %, gear, rpm, drs/ers fields from `car_telemetry` + `car_status` payload names in spec.
  - map source fields explicitly (examples):
    - `drs` → output `drs_enabled`
    - `ers_store_energy` → output `ers_store_energy_j`
    - `ers_harvested_this_lap_mguk` → output `ers_harvest_mguk_j`
    - `ers_deployed_this_lap` → output `ers_deployed_this_lap_j`
  - publish `ep.r1.player.derived.car_metrics` at up to 20 Hz.
- `lap_metrics_processor`
  - derive lap timing fields and convert enum values to output representation:
    - sector 0/1/2 → 1/2/3
    - pit_status 0/1/2 → `none`/`pitting`/`in_pit_area`
  - publish `ep.r1.player.derived.lap_metrics` at up to 10 Hz.
- `tyre_metrics_processor`
  - derive per-corner temperatures from `tyres_surface_temp` and `tyres_inner_temp` (RL, RR, FL, FR).
  - set wear-related output fields to `null`/default in R1 because Tier-1 input does not include tyre wear percentage.
  - optionally keep internal placeholder hook for future `car_damage` integration.
  - publish `ep.r1.player.derived.tyre_metrics` at up to 5 Hz.
- `patch_emitter`
  - emit incremental state patches to `ep.r1.player.state.patch`.

### Deliverables

- Functional processors with deterministic outputs from sample inputs.

### Exit criteria

- Golden tests validate generated payload fields and types.
- Golden tests validate field-name mapping between input spec payloads and output contract payloads.
- No output emitted for invalid/unsupported inputs.

---

## Phase 4 — Orchestration and Runtime Behavior

**Goal:** Wire pipeline end-to-end for continuous operation.

### Tasks

- Implement router from input topic to relevant processors.
- Implement orchestrator event loop:
  - subscribe to input channels.
  - decode + validate + session guard.
  - run processor chain.
  - publish derived/state/meta outputs.
- Add periodic heartbeat to `ep.r1.player.meta` (`processor_heartbeat`).
- Add graceful shutdown and reconnect strategy for Redis interruptions.

### Deliverables

- Long-running service processing live telemetry.

### Exit criteria

- Manual run demonstrates outputs on all Release 1 channels.
- Service survives transient Redis disconnect and recovers.

---

## Phase 5 — Verification and Hardening

**Goal:** Validate correctness, latency, and operational safety.

### Tasks

- Integration tests using recorded telemetry sample stream.
- Load test at expected local rates (up to 60 Hz source topics).
- Validate throttling caps on derived channels.
- Validate topic↔packet_type mismatch handling (drop + log).
- Validate flashback behavior (`frame_identifier` rewind with monotonic `overall_frame_identifier`).
- Validate wheel-order mapping correctness (RL, RR, FL, FR) for tyre fields.
- Add structured logs and counters:
  - `messages_in`, `messages_out`, `dropped_invalid`, `dropped_out_of_order`, `session_resets`.
- Document failure modes and operator runbook.

### Deliverables

- Test report + known limitations list.

### Exit criteria

- Processor runs continuously for 30+ minutes without crash.
- Output schema remains contract-compliant.

---

## 5) Milestones and Sequence

1. **M1:** Bootstrap complete (Phase 0)  
2. **M2:** Contracts + Redis IO stable (Phase 1)  
3. **M3:** Session/state correctness (Phase 2)  
4. **M4:** All derived outputs shipped (Phase 3)  
5. **M5:** End-to-end runtime validated (Phase 4)  
6. **M6:** Hardening sign-off (Phase 5)

Recommended execution order is strict (M1 → M6).

---

## 6) Testing Strategy

- **Unit tests**
  - contract validators, envelope builder, patch apply logic, per-processor math.
- **Integration tests**
  - in-process Redis pub/sub pipeline from raw input to emitted outputs.
- **Replay tests**
  - feed deterministic telemetry capture and snapshot expected outputs.
- **Contract tests**
  - assert all outbound messages match section 7 schemas exactly.

Minimum quality gate before release:
- Unit + integration tests passing.
- No unhandled exceptions in steady-state run.

---

## 7) Observability and Operations

- Structured logs with `session_uid`, `overall_frame_identifier`, `type`, `topic`.
- Startup meta event: `processor_started`.
- Heartbeat meta event every fixed interval (e.g., 5s).
- Optional simple `/health` endpoint can be added later by gateway process (not required in R1).

---

## 8) Risks and Mitigations

- **Out-of-order/duplicate packets:** enforce frame ordering and drop stale messages.
- **Schema drift:** hard-check input `v`; fail closed for unknown versions.
- **Topic/schema mismatch:** validate topic against `packet_type`; drop mismatched events.
- **Noisy high-frequency topics:** throttle per output channel to contract rates.
- **Session transitions:** immediate reset and meta signaling on `session_uid` change.
- **Tyre wear unavailability in Tier-1:** keep wear outputs nullable/default and document limitation until Tier-3 `car_damage` support.

---

## 9) Definition of Done (Release 1)

Release 1 is done when:

- All five output channels publish contract-compliant messages.
- Outputs represent **player car only**.
- Ordering/reset rules are enforced and tested.
- Snapshot model is maintained and queryable for gateway bootstrap.
- Documentation covers configuration, run steps, and troubleshooting.
