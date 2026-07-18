"""컴퓨터 Gateway 코드: 여러 ESP32의 USB Serial과 Vercel API를 중계한다."""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import requests
import serial
from dotenv import load_dotenv
from serial.tools import list_ports

load_dotenv()

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:3000").rstrip("/")
API_KEY = os.getenv("GATEWAY_API_KEY", "")
SERIAL_BAUD = int(os.getenv("SERIAL_BAUD", "115200"))
FIXED_PORTS = [p.strip() for p in os.getenv("SERIAL_PORTS", "").split(",") if p.strip()]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(threadName)s] %(message)s",
)
log = logging.getLogger("ev-fire-gateway")


def api_headers() -> dict[str, str]:
    return {"content-type": "application/json", "x-gateway-key": API_KEY}


@dataclass
class DeviceWorker:
    port: str
    stop_event: threading.Event
    device_id: str | None = None
    parking_spot_id: str | None = None
    serial_connection: serial.Serial | None = field(default=None, init=False)
    last_command_poll: float = field(default=0.0, init=False)
    session: requests.Session = field(default_factory=requests.Session, init=False)

    def run(self) -> None:
        try:
            self.serial_connection = serial.Serial(
                self.port, SERIAL_BAUD, timeout=0.5, write_timeout=1
            )
            time.sleep(2)  # ESP32가 포트 open으로 재시작될 시간
            log.info("시리얼 연결: %s", self.port)

            while not self.stop_event.is_set():
                raw = self.serial_connection.readline()
                if raw:
                    self.handle_serial_line(raw)
                if self.device_id and time.monotonic() - self.last_command_poll >= 1.0:
                    self.poll_commands()
                    self.last_command_poll = time.monotonic()
        except (serial.SerialException, OSError) as exc:
            log.warning("%s 연결 종료: %s", self.port, exc)
        finally:
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()

    def handle_serial_line(self, raw: bytes) -> None:
        try:
            message = json.loads(raw.decode("utf-8").strip())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            log.warning("%s 잘못된 메시지: %s", self.port, exc)
            return

        message_type = message.get("type")
        if message_type == "hello":
            self.device_id = message.get("deviceId")
            self.parking_spot_id = message.get("parkingSpotId")
            log.info("장치 확인: %s (%s, %s)", self.device_id, self.parking_spot_id, self.port)
        elif message_type == "telemetry":
            self.device_id = message.get("deviceId", self.device_id)
            self.parking_spot_id = message.get("parkingSpotId", self.parking_spot_id)
            self.forward_telemetry(message)
        elif message_type == "commandAck":
            self.forward_ack(message)

    def forward_telemetry(self, message: dict[str, Any]) -> None:
        try:
            response = self.session.post(
                f"{SERVER_URL}/api/telemetry",
                headers=api_headers(),
                json=message,
                timeout=5,
            )
            response.raise_for_status()
            body = response.json()
            for command in body.get("commands", []):
                self.send_command(command)
            log.info(
                "%s 온도=%s°C 판정=%s",
                self.device_id,
                message.get("temperatureC", "N/A"),
                body.get("fireDecision", {}).get("fire", False),
            )
        except requests.RequestException as exc:
            # 다음 센서 데이터에서 다시 연결한다. 서버는 sequence 중복을 허용하지 않는다.
            log.error("서버 전송 실패 (%s): %s", self.device_id, exc)

    def poll_commands(self) -> None:
        try:
            response = self.session.get(
                f"{SERVER_URL}/api/devices/{self.device_id}/commands",
                headers=api_headers(),
                timeout=3,
            )
            response.raise_for_status()
            for command in response.json().get("commands", []):
                self.send_command(command)
        except requests.RequestException as exc:
            log.debug("명령 조회 실패 (%s): %s", self.device_id, exc)

    def send_command(self, command: dict[str, Any]) -> None:
        if not self.serial_connection:
            return
        wire_message = {
            "type": "command",
            "commandId": command["commandId"],
            "action": command["action"],
            "reason": command.get("reason"),
            "issuedAt": command.get("issuedAt"),
        }
        self.serial_connection.write((json.dumps(wire_message) + "\n").encode("utf-8"))
        self.serial_connection.flush()
        log.warning("명령 전달 → %s: %s", self.device_id, command["action"])

    def forward_ack(self, message: dict[str, Any]) -> None:
        command_id = message.get("commandId")
        if not command_id:
            return
        try:
            response = self.session.post(
                f"{SERVER_URL}/api/commands/{command_id}/ack",
                headers=api_headers(),
                json={"deviceId": self.device_id, "status": message.get("status")},
                timeout=3,
            )
            response.raise_for_status()
            log.info("명령 실행 확인: %s", command_id)
        except requests.RequestException as exc:
            log.error("명령 ACK 전송 실패: %s", exc)


class GatewayManager:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.workers: dict[str, threading.Thread] = {}

    def available_ports(self) -> list[str]:
        if FIXED_PORTS:
            return FIXED_PORTS
        # USB serial 포트를 모두 후보로 사용. 운영 환경에서는 VID/PID allow-list 권장.
        return [port.device for port in list_ports.comports() if port.vid is not None]

    def run(self) -> None:
        log.info("Gateway 시작: server=%s", SERVER_URL)
        if not API_KEY:
            raise SystemExit("GATEWAY_API_KEY가 비어 있습니다. computer/.env를 먼저 설정하세요.")

        while not self.stop_event.is_set():
            for port in self.available_ports():
                thread = self.workers.get(port)
                if thread is None or not thread.is_alive():
                    worker = DeviceWorker(port=port, stop_event=self.stop_event)
                    thread = threading.Thread(target=worker.run, name=port, daemon=True)
                    self.workers[port] = thread
                    thread.start()
            self.stop_event.wait(3)

        for thread in self.workers.values():
            thread.join(timeout=2)

    def stop(self, *_: object) -> None:
        log.info("Gateway 종료 중...")
        self.stop_event.set()


if __name__ == "__main__":
    manager = GatewayManager()
    signal.signal(signal.SIGINT, manager.stop)
    signal.signal(signal.SIGTERM, manager.stop)
    manager.run()
