"""Quick start example for controlling the SO-101 arm."""

from phosphobot_client import PhosphobotClient


def main() -> None:
    with PhosphobotClient() as client:
        init_response = client.move_init()
        print("Init response:", init_response)
        move_response = client.move_absolute(25.0, 0.0, 15.0, 0.0, -30.0, 0.0, 50)
        print("Move response:", move_response)


if __name__ == "__main__":
    main()
