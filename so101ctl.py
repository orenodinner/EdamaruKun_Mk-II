"""Command-line interface for the Phosphobot SO-101 controller."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from phosphobot_client import (
    HTTPError,
    MovementLimits,
    PhosphobotClient,
    PhosphobotError,
    ResponseDecodeError,
    TimeoutError,
    ValidationError,
)

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(verbose: bool) -> None:
    """Configure CLI logging verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Build and parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Operate the Phosphobot SO-101 robotic arm via the HTTP API.",
    )
    parser.add_argument("--base-url", help="Override the Phosphobot service URL.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Request timeout in seconds (default: 5.0).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Maximum number of retries for transient failures (default: 3).",
    )
    parser.add_argument(
        "--limits-file",
        type=str,
        help="Load movement limits from a JSON file (overrides defaults).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        dest="init_flag",
        help="Immediately drive the arm to its initialization pose.",
    )

    subparsers = parser.add_subparsers(dest="command", title="commands")

    subparsers.add_parser("init", help="Move the arm into the safe initialization pose.")

    move_parser = subparsers.add_parser(
        "move",
        help="Send an absolute TCP pose and gripper command.",
    )
    move_parser.add_argument("--x", dest="x_cm", type=float, required=True, help="Target X position in cm.")
    move_parser.add_argument("--y", dest="y_cm", type=float, required=True, help="Target Y position in cm.")
    move_parser.add_argument("--z", dest="z_cm", type=float, required=True, help="Target Z position in cm.")
    move_parser.add_argument("--roll", dest="roll_deg", type=float, required=True, help="Roll angle in degrees.")
    move_parser.add_argument("--pitch", dest="pitch_deg", type=float, required=True, help="Pitch angle in degrees.")
    move_parser.add_argument("--yaw", dest="yaw_deg", type=float, required=True, help="Yaw angle in degrees.")
    move_parser.add_argument(
        "--grip",
        dest="grip",
        type=int,
        required=True,
        help="Gripper opening percentage (0-100).",
    )

    parsed = parser.parse_args(argv)
    if not parsed.command and not parsed.init_flag:
        parser.print_help()
        parser.exit(1)
    return parsed


def load_limits(path: str) -> MovementLimits:
    """Load movement limits from a JSON document."""
    raw_path = Path(path)
    if not raw_path.exists():
        raise FileNotFoundError(f"Limits file not found: {raw_path}")
    with raw_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    def parse_range(key: str) -> Optional[tuple[float, float]]:
        if key not in data or data[key] is None:
            return None
        entry = data[key]
        if not isinstance(entry, dict):
            raise ValueError(f"Limits for '{key}' must be an object with 'min' and 'max'.")
        try:
            minimum = float(entry["min"])
            maximum = float(entry["max"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Limits for '{key}' require numeric 'min' and 'max' values.") from exc
        if minimum > maximum:
            raise ValueError(f"Limits for '{key}' have min greater than max.")
        return (minimum, maximum)

    def parse_grip() -> tuple[int, int]:
        if "grip" not in data or data["grip"] is None:
            return MovementLimits().grip
        entry = data["grip"]
        if not isinstance(entry, dict):
            raise ValueError("Limits for 'grip' must be an object with 'min' and 'max'.")
        try:
            minimum = int(entry["min"])
            maximum = int(entry["max"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Limits for 'grip' require integer 'min' and 'max' values.") from exc
        if minimum > maximum:
            raise ValueError("Limits for 'grip' have min greater than max.")
        return (minimum, maximum)

    return MovementLimits(
        x_cm=parse_range("x_cm"),
        y_cm=parse_range("y_cm"),
        z_cm=parse_range("z_cm"),
        roll_deg=parse_range("roll_deg"),
        pitch_deg=parse_range("pitch_deg"),
        yaw_deg=parse_range("yaw_deg"),
        grip=parse_grip(),
    )


def output_success(summary: str, payload: Dict[str, Any]) -> None:
    """Print a success summary and pretty-printed payload."""
    print(f"OK: {summary}")
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point for the CLI."""
    args = parse_args(argv)
    configure_logging(args.verbose)

    limits = MovementLimits()
    if args.limits_file:
        try:
            limits = load_limits(args.limits_file)
            logging.getLogger(__name__).info("Loaded limits from %s.", args.limits_file)
        except (OSError, ValueError) as exc:
            logging.getLogger(__name__).error("Failed to load limits: %s", exc)
            return 1

    try:
        with PhosphobotClient(
            base_url=args.base_url,
            timeout_sec=args.timeout,
            max_retries=args.retries,
            limits=limits,
        ) as client:
            if args.init_flag or args.command == "init":
                response = client.move_init()
                output_success("moved to initialization pose", response)
                return 0
            if args.command == "move":
                response = client.move_absolute(
                    x_cm=args.x_cm,
                    y_cm=args.y_cm,
                    z_cm=args.z_cm,
                    roll_deg=args.roll_deg,
                    pitch_deg=args.pitch_deg,
                    yaw_deg=args.yaw_deg,
                    grip=args.grip,
                )
                summary = (
                    f"moved to (x={args.x_cm:.2f}cm, y={args.y_cm:.2f}cm, "
                    f"z={args.z_cm:.2f}cm, roll={args.roll_deg:.2f}deg, "
                    f"pitch={args.pitch_deg:.2f}deg, yaw={args.yaw_deg:.2f}deg, grip={args.grip}%)"
                )
                output_success(summary, response)
                return 0
    except ValidationError as exc:
        logging.getLogger(__name__).error("Validation error: %s", exc)
    except TimeoutError as exc:
        logging.getLogger(__name__).error("Timeout: %s", exc)
    except HTTPError as exc:
        logging.getLogger(__name__).error("HTTP error: %s", exc)
    except ResponseDecodeError as exc:
        logging.getLogger(__name__).error("Response decoding error: %s", exc)
    except PhosphobotError as exc:
        logging.getLogger(__name__).error("Unexpected Phosphobot error: %s", exc)
    except Exception as exc:  # pragma: no cover
        logging.getLogger(__name__).exception("Unexpected failure: %s", exc)

    return 1


if __name__ == "__main__":
    sys.exit(main())
