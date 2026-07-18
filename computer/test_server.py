"""Send safe demo telemetry to the server without heating a real sensor.

Usage:
    python test_server.py normal
    python test_server.py fire
    python test_server.py reset
"""

from __future__ import annotations

import argparse
import os
import random
import time

import requests
from dotenv import load_dotenv

load_dotenv()

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:3000").rstrip("/")
API_KEY = os.getenv("GATEWAY_API_KEY", "")
DEVICE_ID = os.getenv("TEST_DEVICE_ID", "esp32-bay-01")
PARKING_SPOT_ID = os.getenv("TEST_PARKING_SPOT_ID", "A-01")
USER_ID = os.getenv("TEST_USER_ID", "11111111-1111-4111-8111-111111111111")


def gateway_headers() -> dict[str, str]:
    return {"content-type": "application/json", "x-gateway-key": API_KEY}


def send_telemetry(temperature_c: float, humidity_pct: float) -> None:
    payload = {
        "type": "telemetry",
        "deviceId": DEVICE_ID,
        "parkingSpotId": PARKING_SPOT_ID,
        "bootId": f"test{random.randrange(16**4):04x}",
        "sequence": int(time.time() * 1000) % 2_000_000_000,
        "sensorOk": True,
        "temperatureC": temperature_c,
        "humidityPct": humidity_pct,
        "emergencyActive": False,
    }
    response = requests.post(
        f"{SERVER_URL}/api/telemetry",
        headers=gateway_headers(),
        json=payload,
        timeout=10,
    )
    print("HTTP", response.status_code)
    print(response.text)
    response.raise_for_status()


def reset_active_events() -> None:
    dashboard = requests.get(
        f"{SERVER_URL}/api/users/{USER_ID}/dashboard",
        timeout=10,
    )
    dashboard.raise_for_status()
    alerts = dashboard.json().get("activeAlerts", [])
    if not alerts:
        print("No active fire event was found.")
        return

    for alert in alerts:
        response = requests.post(
            f"{SERVER_URL}/api/fire-events/{alert['id']}/resolve",
            headers=gateway_headers(),
            timeout=10,
        )
        print("HTTP", response.status_code, response.text)
        response.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("normal", "fire", "reset"))
    args = parser.parse_args()

    if not API_KEY:
        raise SystemExit("Set GATEWAY_API_KEY in computer/.env first.")

    if args.mode == "normal":
        send_telemetry(25.0, 45.0)
    elif args.mode == "fire":
        send_telemetry(75.0, 80.0)
    else:
        reset_active_events()


if __name__ == "__main__":
    main()
