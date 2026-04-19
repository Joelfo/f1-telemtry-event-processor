# Telemetry Event Object Specification

**Version:** 1.0  
**Source:** `f1-telemetry-ingestor` repository  
**Audience:** Event Processor consumers reading from Redis  

---

## Overview

Every UDP packet received from F1 24 is parsed and published to Redis as a
MessagePack blob (schema version `v=1`).  After unpacking, the message
represents a **Telemetry Event** — an envelope of metadata plus a
packet-specific payload dict.

This document defines what every field means, its type, valid range, and how
to use it correctly in an Event Processor.

---

## How to receive an event

```python
import msgpack
import redis

r = redis.Redis()
pubsub = r.pubsub()
pubsub.subscribe("car_telemetry", "lap_data", "car_status", "motion_ex")

for message in pubsub.listen():
    if message["type"] != "message":
        continue
    event = msgpack.unpackb(message["data"], raw=False)
    # event is a plain dict — see envelope spec below
```

---

## Envelope fields

Present on **every** event regardless of topic.

| Field | Python type | Description |
|---|---|---|
| `v` | `int` | Schema version. **Must equal `1`** — reject and log if not. |
| `packet_type` | `int` | Numeric packet ID (0–14). See [Packet type values](#packet-type-values). |
| `session_uid` | `int` | Unique session identifier (uint64). Changes each time a new session starts. Use this to correlate events across topics and to detect session changes. |
| `session_time` | `float` | Game clock in **seconds** from session start. Taken directly from the UDP header. |
| `frame_identifier` | `int` | Monotonic game frame counter. **Resets after a flashback** — see [Flashback handling](#flashback-handling). |
| `overall_frame_identifier` | `int` | Like `frame_identifier` but **never rolls back** after a flashback. Prefer this for event ordering. |
| `player_car_index` | `int` | Index (0–21) of the primary player's car in the 22-car arrays. Constant within a session. |
| `car_idx` | `int` or `null` | Set only for per-car cycling packets (`session_history`, `tyre_sets`). For all Tier-1 topics this is always `null`. |
| `ingested_at` | `float` | `time.monotonic()` on the ingestor host at the moment the datagram arrived. **Not a wall-clock time** — use only for latency diagnostics, not game-time comparisons. |
| `payload` | `dict` | Topic-specific fields. See payload sections below. |

---

## Packet type values

| `packet_type` | Topic (Redis channel) | Implemented |
|---|---|---|
| 0 | `motion` | No (Tier 3 stub) |
| 1 | `session` | No (Tier 2 stub) |
| 2 | `lap_data` | **Yes — Tier 1** |
| 3 | `event` | No (Tier 2 stub) |
| 4 | `participants` | No |
| 5 | `car_setups` | No |
| 6 | `car_telemetry` | **Yes — Tier 1** |
| 7 | `car_status` | **Yes — Tier 1** |
| 8 | `final_classification` | No |
| 9 | `lobby_info` | No |
| 10 | `car_damage` | No (Tier 3 stub) |
| 11 | `session_history` | No (Tier 3 stub) |
| 12 | `tyre_sets` | No (Tier 3 stub) |
| 13 | `motion_ex` | **Yes — Tier 1** |
| 14 | `time_trial` | No |

---

## Session handling

- A new session starts when `session_uid` changes.
- On receipt of a new `session_uid`, reset all accumulated state (lap times,
  stint history, damage totals, etc.).
- `session_time` is the authoritative in-session clock. It resets to 0 at
  the start of each session.
- `player_car_index` is stable within a session but **may change** between
  sessions (e.g. practice → qualifying → race). Always read it from the
  envelope, never cache it across a session boundary.

---

## Flashback handling

When the driver uses a flashback, the game rewinds time:

- `frame_identifier` drops back to the frame before the incident — events
  from the rewound segment will be re-sent with **smaller** frame numbers.
- `overall_frame_identifier` **never decreases** — it is safe to use as a
  monotonic ordering key across flashbacks.
- `session_time` also rewinds — if your state store relies on session time
  for ordering, re-check against `overall_frame_identifier`.

---

## Payload: `car_telemetry` (Packet ID 6)

Rate: up to 60 Hz.  
Data for **the player's car only**.

| Field | Type | Range / Unit | Notes |
|---|---|---|---|
| `speed_kph` | `int` | 0–400 km/h | |
| `throttle` | `float` | 0.0–1.0 | 0 = no input, 1 = full |
| `steer` | `float` | -1.0–1.0 | -1 = full lock left, +1 = full lock right |
| `brake` | `float` | 0.0–1.0 | 0 = no braking, 1 = full |
| `clutch` | `int` | 0–100 | Percentage |
| `gear` | `int` | -1–8 | -1 = Reverse, 0 = Neutral, 1–8 = forward gears |
| `engine_rpm` | `int` | 0–20000 | |
| `drs` | `bool` | | `true` = DRS flap is open |
| `rev_lights_percent` | `int` | 0–100 | MFD rev bar fill |
| `rev_lights_bit_value` | `int` | 0–0x7FFF | Bitmask; bit 0 = leftmost LED, bit 14 = rightmost |
| `brakes_temperature` | `int[4]` | 0–1500 °C | Order: RL, RR, FL, FR |
| `tyres_surface_temp` | `int[4]` | 0–150 °C | Order: RL, RR, FL, FR |
| `tyres_inner_temp` | `int[4]` | 0–150 °C | Order: RL, RR, FL, FR |
| `engine_temperature` | `int` | 0–200 °C | Coolant temperature |
| `tyres_pressure` | `float[4]` | 0–40 PSI | Order: RL, RR, FL, FR |
| `surface_type` | `int[4]` | See note | Driving surface enum per wheel (RL, RR, FL, FR) |
| `suggested_gear` | `int` | 0–8 | Game assist suggestion; 0 = no suggestion |

**Surface type values:** 0=Tarmac, 1=Rumble strip, 2=Concrete, 3=Rock,
4=Gravel, 5=Mud, 6=Sand, 7=Water, 8=Cobblestone, 9=Metal, 10=Ridged.

---

## Payload: `lap_data` (Packet ID 2)

Rate: up to 60 Hz.  
Data for **the player's car only**.  
All times are in **milliseconds** unless otherwise noted.

| Field | Type | Unit | Notes |
|---|---|---|---|
| `last_lap_time_ms` | `int` | ms | 0 at session start or before first completed lap |
| `current_lap_time_ms` | `int` | ms | Time elapsed in the current lap |
| `sector1_time_ms` | `int` | ms | 0 during S1 (not yet completed) |
| `sector2_time_ms` | `int` | ms | 0 during S1/S2 (not yet completed) |
| `delta_to_car_in_front_ms` | `int` | ms | Gap to the car ahead |
| `delta_to_race_leader_ms` | `int` | ms | Gap to race leader |
| `lap_distance` | `float` | metres | Distance from start line this lap; can be negative before crossing the line |
| `total_distance` | `float` | metres | Total distance covered in the session |
| `safety_car_delta` | `float` | seconds | Gap to safety car |
| `car_position` | `int` | 1-based | Current race position |
| `current_lap_num` | `int` | 1-based | |
| `pit_status` | `int` | | 0=none, 1=pitting, 2=in pit area |
| `num_pit_stops` | `int` | | Pit stops completed this race |
| `sector` | `int` | | Current sector: 0=S1, 1=S2, 2=S3 |
| `current_lap_invalid` | `bool` | | `true` if the lap has been invalidated |
| `penalties_seconds` | `int` | seconds | Accumulated time penalties |
| `total_warnings` | `int` | | |
| `corner_cutting_warnings` | `int` | | |
| `unserved_drive_through_pens` | `int` | | |
| `unserved_stop_go_pens` | `int` | | |
| `grid_position` | `int` | 1-based | Starting grid position |
| `driver_status` | `int` | | See note |
| `result_status` | `int` | | See note |
| `pit_lane_timer_active` | `bool` | | |
| `pit_lane_time_ms` | `int` | ms | Time in pit lane (only meaningful when timer active) |
| `pit_stop_timer_ms` | `int` | ms | Duration of the pit stop itself |
| `speed_trap_fastest_speed` | `float` | km/h | Player's fastest speed trap reading this session |
| `speed_trap_fastest_lap` | `int` | | Lap number for the fastest speed trap; 255 = not set |

**`driver_status` values:** 0=in garage, 1=flying lap, 2=in lap, 3=out lap, 4=on track.

**`result_status` values:** 0=invalid, 1=inactive, 2=active, 3=finished, 4=DNF, 5=DSQ, 6=not classified, 7=retired.

---

## Payload: `car_status` (Packet ID 7)

Rate: up to 60 Hz.  
Data for **the player's car only**.

| Field | Type | Range / Unit | Notes |
|---|---|---|---|
| `traction_control` | `int` | 0–2 | 0=off, 1=medium, 2=full |
| `anti_lock_brakes` | `bool` | | |
| `fuel_mix` | `int` | 0–3 | 0=lean, 1=standard, 2=rich, 3=max |
| `front_brake_bias` | `int` | % | |
| `pit_limiter_status` | `bool` | | `true` = pit lane speed limiter active |
| `fuel_in_tank` | `float` | kg | |
| `fuel_capacity` | `float` | kg | Maximum tank capacity |
| `fuel_remaining_laps` | `float` | laps | Estimated laps remaining on current fuel |
| `max_rpm` | `int` | RPM | Rated engine limit |
| `idle_rpm` | `int` | RPM | |
| `max_gears` | `int` | | Number of forward gears |
| `drs_allowed` | `bool` | | `true` = race control has enabled DRS for this car |
| `drs_activation_distance` | `int` | metres | Metres until DRS zone; 0 = not applicable |
| `actual_tyre_compound` | `int` | | Physical compound fitted — see note |
| `visual_tyre_compound` | `int` | | Displayed compound — see note |
| `tyres_age_laps` | `int` | laps | |
| `vehicle_fia_flags` | `int` | | **Signed:** -1=unknown, 0=none, 1=green, 2=blue, 3=yellow |
| `engine_power_ice` | `float` | Watts | ICE power output |
| `engine_power_mguk` | `float` | Watts | MGU-K power output |
| `ers_store_energy` | `float` | Joules | ERS battery charge |
| `ers_deploy_mode` | `int` | 0–3 | 0=none, 1=medium, 2=hotlap, 3=overtake |
| `ers_harvested_this_lap_mguk` | `float` | Joules | |
| `ers_harvested_this_lap_mguh` | `float` | Joules | |
| `ers_deployed_this_lap` | `float` | Joules | |
| `network_paused` | `bool` | | `true` = car paused in a network game |

**`actual_tyre_compound` values (F1 Modern):** 16=C5, 17=C4, 18=C3, 19=C2,
20=C1, 21=C0, 7=Intermediate, 8=Wet.

**`visual_tyre_compound` values:** 16=Soft, 17=Medium, 18=Hard,
7=Intermediate, 8=Wet.

> **Note on `vehicle_fia_flags`:** This is a **signed integer**. Always
> treat -1 as "unknown / no data". Do not compare with `>= 0` checks alone.

---

## Payload: `motion_ex` (Packet ID 13)

Rate: up to 60 Hz.  
Player car only (no 22-car array — this packet carries only the primary
player's data).

All wheel arrays follow **RL, RR, FL, FR** order.

| Field | Type | Unit | Notes |
|---|---|---|---|
| `suspension_position` | `float[4]` | | |
| `suspension_velocity` | `float[4]` | | |
| `suspension_acceleration` | `float[4]` | | |
| `wheel_speed` | `float[4]` | m/s | Rotational wheel speed |
| `wheel_slip_ratio` | `float[4]` | | |
| `wheel_slip_angle` | `float[4]` | | |
| `wheel_lat_force` | `float[4]` | N | Lateral force per wheel |
| `wheel_long_force` | `float[4]` | N | Longitudinal force per wheel |
| `height_of_cog_above_ground` | `float` | metres | Centre-of-gravity height |
| `local_velocity_x` | `float` | m/s | Velocity in car's local X axis (lateral) |
| `local_velocity_y` | `float` | m/s | Velocity in car's local Y axis (vertical) |
| `local_velocity_z` | `float` | m/s | Velocity in car's local Z axis (longitudinal) |
| `angular_velocity_x` | `float` | rad/s | |
| `angular_velocity_y` | `float` | rad/s | |
| `angular_velocity_z` | `float` | rad/s | |
| `angular_acceleration_x` | `float` | rad/s² | |
| `angular_acceleration_y` | `float` | rad/s² | |
| `angular_acceleration_z` | `float` | rad/s² | |
| `front_wheels_angle` | `float` | radians | Front wheel steer angle |
| `wheel_vert_force` | `float[4]` | N | Vertical load per wheel (RL, RR, FL, FR) |
| `front_aero_height` | `float` | metres | Front plank ride height |
| `rear_aero_height` | `float` | metres | Rear plank ride height |
| `front_roll_angle` | `float` | radians | Front suspension roll |
| `rear_roll_angle` | `float` | radians | Rear suspension roll |
| `chassis_yaw` | `float` | radians | Yaw relative to direction of motion |

---

## Recommended event processor patterns

**Session boundary detection:**
```python
current_session = None

def process(event: dict) -> None:
    if event["session_uid"] != current_session:
        on_new_session(event["session_uid"])
        current_session = event["session_uid"]
```

**Monotonic ordering across flashbacks:**
```python
# Use overall_frame_identifier, not frame_identifier
if event["overall_frame_identifier"] <= last_frame:
    return  # duplicate or already-seen frame
last_frame = event["overall_frame_identifier"]
```

**ERS percentage (useful for display):**
```python
ERS_MAX_JOULES = 4_000_000  # F1 regulation maximum

def ers_percent(payload: dict) -> float:
    return payload["ers_store_energy"] / ERS_MAX_JOULES * 100
```

**Speed in m/s from motion_ex:**
```python
import math

def speed_ms(payload: dict) -> float:
    vx = payload["local_velocity_x"]
    vy = payload["local_velocity_y"]
    vz = payload["local_velocity_z"]
    return math.sqrt(vx**2 + vy**2 + vz**2)
```

**Tyre temperature average (all 4 wheels):**
```python
def avg_tyre_surface_temp(payload: dict) -> float:
    return sum(payload["tyres_surface_temp"]) / 4
```
