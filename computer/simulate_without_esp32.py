"""Safely generate ESP32-shaped telemetry without physical hardware.

Dry-run is the default. Add --live to contact the configured server. A fire
scenario additionally requires --confirm-fire because it may create an event
and send a real app notification to a registered phone.
"""

from __future__ import annotations

import argparse
import json
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

SCENARIOS = {
    "normal": (25.0, 45.0, 24.0),
    "warning": (40.0, 55.0, 25.0),
    "delta-fire": (56.0, 60.0, 25.0),
    "critical-fire": (75.0, 80.0, 27.0),
}


def make_payload(name: str) -> dict:
    inside, humidity, outside = SCENARIOS[name]
    return {
        "type": "telemetry",
        "deviceId": DEVICE_ID,
        "parkingSpotId": PARKING_SPOT_ID,
        "bootId": f"virtual-{random.randrange(16**8):08x}",
        "sequence": int(time.time() * 1000) % 2_000_000_000,
        "sensorOk": True,
        "temperatureC": inside,
        "humidityPct": humidity,
        "outsideTemperatureC": outside,
        "outsideObjectTemperatureC": outside,
        "insideOutsideDeltaC": round(inside - outside, 2),
        "emergencyActive": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=tuple(SCENARIOS))
    parser.add_argument("--live", action="store_true", help="send to SERVER_URL")
    parser.add_argument(
        "--confirm-fire",
        action="store_true",
        help="allow a fire scenario to create DB commands and push alerts",
    )
    args = parser.parse_args()

    payload = make_payload(args.scenario)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.live:
        print("DRY RUN: no network request was sent.")
        return
    if not API_KEY:
        raise SystemExit("Set GATEWAY_API_KEY in computer/.env first.")
    if args.scenario.endswith("fire") and not args.confirm_fire:
        raise SystemExit("Fire simulation blocked. Add --confirm-fire after checking the target server.")

    response = requests.post(
        f"{SERVER_URL}/api/telemetry",
        headers={"content-type": "application/json", "x-gateway-key": API_KEY},
        json=payload,
        timeout=10,
    )
    print("HTTP", response.status_code)
    print(response.text)
    response.raise_for_status()


if __name__ == "__main__":
    main()
