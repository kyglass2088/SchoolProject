"""Hardware-free unit tests for the computer gateway."""

from __future__ import annotations

import json
import threading
import unittest

from gateway import DeviceWorker


class FakeResponse:
    def __init__(self, body: dict | None = None) -> None:
        self._body = body or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


class FakeSession:
    def __init__(self, telemetry_body: dict | None = None) -> None:
        self.telemetry_body = telemetry_body or {}
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[str] = []

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.posts.append((url, kwargs.get("json", {})))
        return FakeResponse(self.telemetry_body)

    def get(self, url: str, **_kwargs: object) -> FakeResponse:
        self.gets.append(url)
        return FakeResponse({"commands": []})


class FakeSerial:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def flush(self) -> None:
        return None


class GatewayTests(unittest.TestCase):
    def make_worker(self) -> DeviceWorker:
        return DeviceWorker(port="VIRTUAL", stop_event=threading.Event())

    def test_hello_identifies_device(self) -> None:
        worker = self.make_worker()
        worker.handle_serial_line(
            b'{"type":"hello","deviceId":"esp32-bay-01","parkingSpotId":"A-01"}\n'
        )
        self.assertEqual(worker.device_id, "esp32-bay-01")
        self.assertEqual(worker.parking_spot_id, "A-01")

    def test_telemetry_forwards_command_to_serial(self) -> None:
        worker = self.make_worker()
        worker.session = FakeSession({
            "fireDecision": {"fire": True},
            "commands": [{
                "commandId": "command-1",
                "action": "ACTIVATE_FIRE_RESPONSE",
                "reason": "critical_temperature",
            }],
        })
        worker.serial_connection = FakeSerial()
        message = {
            "type": "telemetry",
            "deviceId": "esp32-bay-01",
            "parkingSpotId": "A-01",
            "temperatureC": 75,
        }
        worker.forward_telemetry(message)
        self.assertEqual(len(worker.session.posts), 1)
        wire = json.loads(worker.serial_connection.writes[0].decode("utf-8"))
        self.assertEqual(wire["action"], "ACTIVATE_FIRE_RESPONSE")

    def test_command_ack_is_forwarded(self) -> None:
        worker = self.make_worker()
        worker.device_id = "esp32-bay-01"
        worker.session = FakeSession()
        worker.forward_ack({"commandId": "command-1", "status": "executed"})
        self.assertEqual(len(worker.session.posts), 1)
        self.assertTrue(worker.session.posts[0][0].endswith("/api/commands/command-1/ack"))


if __name__ == "__main__":
    unittest.main()
