"""Phosphobot HTTP client for controlling SO-101 robotic arms."""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost"


class PhosphobotError(Exception):
    """Base exception for all Phosphobot client errors."""


class ValidationError(PhosphobotError):
    """Raised when input validation fails."""


class HTTPError(PhosphobotError):
    """Raised when the Phosphobot API returns an HTTP error."""

    def __init__(self, status_code: int, message: str, response_body: str | None = None) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.response_body = response_body


class TimeoutError(PhosphobotError):
    """Raised when a request repeatedly times out."""


class ResponseDecodeError(PhosphobotError):
    """Raised when a response cannot be decoded as JSON."""


@dataclass(frozen=True)
class MovementLimits:
    """Allowed ranges for TCP positions, orientation, and gripper."""

    x_cm: Optional[Tuple[float, float]] = (-80.0, 80.0)
    y_cm: Optional[Tuple[float, float]] = (-80.0, 80.0)
    z_cm: Optional[Tuple[float, float]] = (0.0, 90.0)
    roll_deg: Optional[Tuple[float, float]] = (-180.0, 180.0)
    pitch_deg: Optional[Tuple[float, float]] = (-180.0, 180.0)
    yaw_deg: Optional[Tuple[float, float]] = (-180.0, 180.0)
    grip: Tuple[int, int] = (0, 100)

    def get_range(self, axis: str) -> Optional[Tuple[float, float]]:
        """Return the allowed range for the requested axis."""
        return getattr(self, axis)


class PhosphobotClient:
    """Synchronous HTTP client for the Phosphobot SO-101 controller."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout_sec: float = 5.0,
        max_retries: int = 3,
        limits: MovementLimits | None = None,
    ) -> None:
        """Configure a new client instance.

        Args:
            base_url: Base URL for the Phosphobot service. Defaults to the
                ``PHOSPHOBOT_BASE_URL`` environment variable or ``http://localhost``.
            timeout_sec: Request timeout in seconds for each HTTP call.
            max_retries: Maximum number of attempts per request. Retries use
                exponential backoff for transient transport errors.
            limits: Optional safety envelope for TCP pose and gripper commands.
        """
        self.base_url = (base_url or os.getenv("PHOSPHOBOT_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries if max_retries >= 1 else 1
        self._limits = limits or MovementLimits()
        self._session = requests.Session()

    def __enter__(self) -> "PhosphobotClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """Release the underlying HTTP session."""
        self._session.close()

    def move_init(self) -> Dict[str, Any]:
        """Command the robot to move into its safe initialization pose.

        Returns:
            Parsed JSON body returned by the Phosphobot API.

        Raises:
            HTTPError: The API returned a non-successful HTTP status.
            TimeoutError: The request timed out after all retry attempts.
            ResponseDecodeError: The response body was not valid JSON.
        """
        logger.info("Requesting SO-101 to move into the initialization pose.")
        return self._request("POST", "/move/init")

    def move_absolute(
        self,
        x_cm: float,
        y_cm: float,
        z_cm: float,
        roll_deg: float,
        pitch_deg: float,
        yaw_deg: float,
        grip: int,
        *,
        limits: MovementLimits | None = None,
    ) -> Dict[str, Any]:
        """Command the robot to an absolute TCP pose and gripper opening.

        Args:
            x_cm: X position of the tool center point in centimetres.
            y_cm: Y position of the tool center point in centimetres.
            z_cm: Z position of the tool center point in centimetres.
            roll_deg: Roll angle in degrees.
            pitch_deg: Pitch angle in degrees.
            yaw_deg: Yaw angle in degrees.
            grip: Gripper opening percentage (0-100%).
            limits: Optional override for the current command's safety envelope.

        Returns:
            Parsed JSON body returned by the Phosphobot API.

        Raises:
            ValidationError: One or more parameters violate the configured limits.
            HTTPError: The API returned a non-successful HTTP status.
            TimeoutError: The request timed out after all retry attempts.
            ResponseDecodeError: The response body was not valid JSON.
        """
        active_limits = limits or self._limits
        payload = self._validate_move(
            x_cm=x_cm,
            y_cm=y_cm,
            z_cm=z_cm,
            roll_deg=roll_deg,
            pitch_deg=pitch_deg,
            yaw_deg=yaw_deg,
            grip=grip,
            limits=active_limits,
        )
        logger.info(
            "Sending absolute move command to (x=%.2fcm, y=%.2fcm, z=%.2fcm, roll=%.2fdeg, pitch=%.2fdeg, yaw=%.2fdeg, grip=%d%%)",
            payload["x_cm"],
            payload["y_cm"],
            payload["z_cm"],
            payload["roll_deg"],
            payload["pitch_deg"],
            payload["yaw_deg"],
            payload["grip"],
        )
        return self._request("POST", "/move/absolute", json=payload)

    def _validate_move(
        self,
        *,
        x_cm: float,
        y_cm: float,
        z_cm: float,
        roll_deg: float,
        pitch_deg: float,
        yaw_deg: float,
        grip: int,
        limits: MovementLimits,
    ) -> Dict[str, Any]:
        """Validate and normalize movement parameters before transmission."""
        payload: Dict[str, Any] = {}
        payload["x_cm"] = self._validate_numeric("x_cm", x_cm, limits.get_range("x_cm"))
        payload["y_cm"] = self._validate_numeric("y_cm", y_cm, limits.get_range("y_cm"))
        payload["z_cm"] = self._validate_numeric("z_cm", z_cm, limits.get_range("z_cm"))
        payload["roll_deg"] = self._validate_numeric("roll_deg", roll_deg, limits.get_range("roll_deg"))
        payload["pitch_deg"] = self._validate_numeric("pitch_deg", pitch_deg, limits.get_range("pitch_deg"))
        payload["yaw_deg"] = self._validate_numeric("yaw_deg", yaw_deg, limits.get_range("yaw_deg"))
        payload["grip"] = self._validate_grip(grip, limits.grip)
        return payload

    def _validate_numeric(self, name: str, value: Any, value_range: Optional[Tuple[float, float]]) -> float:
        """Ensure that a numeric value is finite and within the allowed range."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(f"{name} must be a number expressed in centimetres or degrees.")
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            raise ValidationError(f"{name} must be a finite number.")
        if value_range is not None:
            lower, upper = value_range
            if numeric_value < lower or numeric_value > upper:
                raise ValidationError(
                    f"{name}={numeric_value:.2f} is outside the safe range [{lower:.2f}, {upper:.2f}]. "
                    "Adjust your command or update the configured limits."
                )
        return numeric_value

    def _validate_grip(self, grip: Any, grip_range: Tuple[int, int]) -> int:
        """Ensure that the gripper command is an integer percentage within range."""
        if isinstance(grip, bool) or not isinstance(grip, int):
            raise ValidationError("grip must be an integer percentage between 0 and 100.")
        lower, upper = grip_range
        if grip < lower or grip > upper:
            raise ValidationError(
                f"grip={grip} is outside the safe range [{lower}, {upper}]. "
                "Adjust your command or update the configured limits."
            )
        return grip

    def _request(self, method: str, path: str, json: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Send an HTTP request with retry, timeout, and response handling."""
        url = self._build_url(path)
        attempt = 0
        while attempt < self.max_retries:
            attempt += 1
            try:
                logger.debug("HTTP %s %s payload=%s attempt=%d", method, url, json, attempt)
                response = self._session.request(
                    method=method.upper(),
                    url=url,
                    json=json,
                    timeout=self.timeout_sec,
                )
                if response.status_code >= 400:
                    message = self._extract_error_message(response)
                    raise HTTPError(response.status_code, message, response.text)
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ResponseDecodeError(
                        "API returned JSON that is not an object. "
                        "Update your client if the API contract has changed."
                    )
                logger.debug("Received response status=%d payload=%s", response.status_code, payload)
                return payload
            except requests.Timeout as exc:
                logger.warning(
                    "Request to %s timed out after %.2fs (attempt %d/%d).",
                    url,
                    self.timeout_sec,
                    attempt,
                    self.max_retries,
                )
                if attempt >= self.max_retries:
                    raise TimeoutError(
                        "Request timed out repeatedly. Check that Phosphobot is reachable "
                        "and consider increasing the timeout."
                    ) from exc
            except HTTPError:
                raise
            except ResponseDecodeError:
                raise
            except requests.RequestException as exc:
                logger.error("Transport error while talking to Phosphobot: %s", exc)
                raise HTTPError(-1, "Transport error talking to Phosphobot API.") from exc
            except ValueError as exc:
                # Raised by response.json()
                logger.error("Failed to decode JSON response: %s", exc)
                raise ResponseDecodeError(
                    "Phosphobot returned a response that is not valid JSON. "
                    "Check the controller logs or update the client."
                ) from exc

            if attempt < self.max_retries:
                delay = self._backoff_delay(attempt)
                logger.debug("Retrying in %.2fs.", delay)
                time.sleep(delay)
        raise TimeoutError("Request failed after maximum retries without a valid response.")

    def _build_url(self, path: str) -> str:
        """Build a full URL from the configured base URL and relative path."""
        trimmed_path = path.lstrip("/")
        return f"{self.base_url}/{trimmed_path}"

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        """Return the exponential backoff delay for the given attempt."""
        base_delay = 0.25
        delay = base_delay * (2 ** (attempt - 1))
        return min(delay, 5.0)

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        """Extract a helpful error message from an HTTP error response."""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                for key in ("message", "error", "detail", "reason"):
                    if key in payload and isinstance(payload[key], str):
                        return payload[key]
        except ValueError:
            pass
        text = response.text.strip()
        if text:
            return text[:200]
        return "Phosphobot API returned an error."


__all__ = [
    "MovementLimits",
    "PhosphobotClient",
    "PhosphobotError",
    "ValidationError",
    "HTTPError",
    "TimeoutError",
    "ResponseDecodeError",
]
