# Phosphobot SO-101 Python SDK & CLI

## Overview

This repository ships a robust Python 3.10+ client SDK and command-line interface for driving the Phosphobot SO-101 robotic arm via its HTTP API. The tools are designed for day-to-day operations by robotics engineers, emphasising safety-first defaults, observability, and a structure that can be ported to TypeScript/Node.js with minimal friction.

### Prerequisites

- Phosphobot controller running locally and reachable at `http://localhost` (override with `PHOSPHOBOT_BASE_URL` or CLI flag).
- Python 3.10 or newer.

## Installation

```bash
python -m venv .venv
. .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt
```

Development dependencies are limited to `requests`; standard library modules cover logging, retries, and testing.

## Quick Start

### SDK Example

```bash
python examples/quick_start.py
```

The script connects to the controller, executes a safety `move_init()`, then performs a sample `move_absolute()` command:

```python
from phosphobot_client import PhosphobotClient

with PhosphobotClient() as client:
    client.move_init()
    client.move_absolute(25.0, 0.0, 15.0, 0.0, -30.0, 0.0, 50)
```

### CLI Usage

```bash
# Move to initialization pose (recommended before any motion)
python so101ctl.py init

# Absolute move with explicit pose (units: cm / deg / grip %)
python so101ctl.py move \
  --x 25 --y 0 --z 15 \
  --roll 0 --pitch -30 --yaw 0 \
  --grip 50

# Run init using only flags (useful for scripts)
python so101ctl.py --init
```

Add `--verbose` for debug logs and `--limits-file limits.json` to load per-site safety envelopes.

## API

### Module `phosphobot_client.py`

- `PhosphobotClient(base_url=None, timeout_sec=5.0, max_retries=3, limits=None)`
  - Auto-discovers `PHOSPHOBOT_BASE_URL` when `base_url` is omitted.
  - Provides safe defaults for timeouts, retries (exponential backoff), and motion limits.
  - Usable as a context manager to ensure HTTP resources are released.
- `move_init() -> dict`
  - Issues `POST /move/init`. Always call before workspace operations.
- `move_absolute(x_cm, y_cm, z_cm, roll_deg, pitch_deg, yaw_deg, grip, *, limits=None) -> dict`
  - Validates units (cm/deg/%), rejects non-finite values, and checks configured ranges.
  - Accepts an optional `MovementLimits` override per call.
- Exceptions
  - `ValidationError`: Bad client-side input.
  - `TimeoutError`: Exhausted all retries after repeated timeouts.
  - `HTTPError`: Non-2xx responses or transport failures.
  - `ResponseDecodeError`: Malformed server payload, prompting inspection or upgrade.

### CLI `so101ctl.py`

- Global options: `--base-url`, `--timeout`, `--retries`, `--verbose`, `--limits-file`, `--init`.
- Commands:
- `init` - Moves to the safe starting pose.
- `move` - Sends a single absolute pose (all parameters required).
- Output: One-line human summary followed by pretty-printed JSON from the controller.

## Safety Guide

- Always execute `move_init()` (or `so101ctl.py init`) after powering the arm or restarting software.
- Keep the robot workspace clear before commanding motion; verify fixtures and humans are out of range.
- Confirm limits: load a site-specific `limits.json` describing safe bounds for each axis and gripper, especially when tooling changes.
- Prepare an emergency stop: know where the hardware E-stop or power disconnect is located.
- Investigate unexpected responses immediately - logs include actionable hints for phasing issues, timeouts, or invalid inputs.

## Troubleshooting

- **Connection refused / timeouts**: Ensure Phosphobot is up (`curl http://localhost/status`), then re-run with a larger `--timeout` or additional retries. The client prints hints when retries are exhausted.
- **HTTP 4xx/5xx**: The CLI surfaces the API error message. Inspect controller logs; retry only after correcting the root cause.
- **Validation failures**: Check units (cm/deg/%) and configured limits. CLI echoes failing values to help tune `limits.json`.
- **Malformed JSON**: Update the client to match any API schema changes, or verify the controller firmware integrity.

## Future Extensions

- API surface ready for upcoming endpoints (`/status`, `/torque_off`, `/record/start|stop`) by adding thin wrappers in the client and wiring new CLI subcommands.
- The code structure mirrors Node.js conventions (single client class, typed limits container, thin CLI entry point), easing a future TypeScript port.
- Extend `so101ctl.py --plan` to stream a JSON motion plan, or integrate torque-off and logging utilities as new subcommands.

## Testing

Run the automated tests with either toolchain:

```bash
pytest -q
# or
python -m unittest
```

Tests rely on `unittest.mock` to isolate the HTTP layer, so no live robot is needed.
