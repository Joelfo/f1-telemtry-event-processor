# F1 Event Processor

Python service that consumes telemetry events from Redis and produces derived event streams for the F1 24 dashboard.

## Phase 0 status

- Project scaffold and package structure created.
- Runnable app entrypoint with startup health log.
- Configuration and logging baseline added.
- Tooling/test config initialized.

## Quick start

1. Create and activate a Python environment.
2. Install dependencies:

```bash
pip install -e .[dev]
```

3. Run the app:

```bash
python -m ep.app
```

For a one-shot startup check:

```bash
python -m ep.app --once
```

## Configuration

Copy `.env.example` to `.env` and adjust values as needed.
