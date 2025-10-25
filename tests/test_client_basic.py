import unittest
from unittest.mock import MagicMock, patch

import requests

from phosphobot_client import (
    HTTPError,
    PhosphobotClient,
    ResponseDecodeError,
    TimeoutError,
    ValidationError,
)


class PhosphobotClientTests(unittest.TestCase):
    @patch("phosphobot_client.requests.Session.request")
    def test_move_init_success(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_request.return_value = mock_response

        client = PhosphobotClient()
        result = client.move_init()

        self.assertEqual(result, {"status": "ok"})
        mock_request.assert_called_once()

    @patch("phosphobot_client.requests.Session.request")
    def test_move_absolute_success(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "moved"}
        mock_request.return_value = mock_response

        client = PhosphobotClient()
        result = client.move_absolute(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 50)

        self.assertEqual(result, {"status": "moved"})
        mock_request.assert_called_once()
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs["json"]["grip"], 50)

    @patch("phosphobot_client.requests.Session.request")
    def test_http_error(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "internal"}
        mock_response.text = "internal"
        mock_request.return_value = mock_response

        client = PhosphobotClient()
        with self.assertRaises(HTTPError):
            client.move_init()

    @patch("phosphobot_client.time.sleep", return_value=None)
    @patch("phosphobot_client.requests.Session.request", side_effect=requests.Timeout("timeout"))
    def test_timeout_retry(self, mock_request: MagicMock, mock_sleep: MagicMock) -> None:
        client = PhosphobotClient(timeout_sec=0.01, max_retries=2)

        with self.assertRaises(TimeoutError):
            client.move_init()

        self.assertEqual(mock_request.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    @patch("phosphobot_client.requests.Session.request")
    def test_invalid_json(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("no json")
        mock_request.return_value = mock_response

        client = PhosphobotClient()
        with self.assertRaises(ResponseDecodeError):
            client.move_init()

    def test_validation_error(self) -> None:
        client = PhosphobotClient()
        with self.assertRaises(ValidationError):
            client.move_absolute(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 150)


if __name__ == "__main__":
    unittest.main()
