"""Quick start example for controlling the SO-101 arm."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from phosphobot_client import PhosphobotClient


def main() -> None:
    with PhosphobotClient() as client:
        init_response = client.move_init()
        print("Init response:", init_response)
        move_response = client.move_absolute(25.0, 0.0, 15.0, 0.0, -30.0, 0.0, 50)
        print("Move response:", move_response)


if __name__ == "__main__":
    main()
