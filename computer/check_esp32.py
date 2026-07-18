"""Quickly validate an attached ESP32 and its sensors without the server.

Close Thonny and gateway.py before running this tool because only one program
can own a Windows COM port at a time.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import serial
from serial.tools import list_ports


def choose_port(explicit: str | None) -> str:
    if explicit:
        return explicit
    ports = [port for port in list_ports.comports() if port.vid is not None]
    if not ports:
        raise SystemExit("ESP32 USB serial port was not found. Check the data cable and driver.")
    if len(ports) > 1:
        print("Several USB serial ports were found:")
        for port in ports:
            print(f"  {port.device}: {port.description}")
        raise SystemExit("Run again with --port COM3 (replace COM3 with the ESP32 port).")
    print(f"Auto-selected {ports[0].device}: {ports[0].description}")
    return ports[0].device


def read_messages(port_name: str, seconds: int) -> tuple[dict | None, list[dict]]:
    hello: dict | None = None
    telemetry: list[dict] = []
    with serial.Serial(port_name, 115200, timeout=0.5, write_timeout=1) as connection:
        connection.dtr = False
        connection.rts = False
        time.sleep(2)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            raw = connection.readline()
            if not raw:
                continue
            try:
                message = json.loads(raw.decode("utf-8").strip())
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if message.get("type") == "hello":
                hello = message
            elif message.get("type") == "telemetry":
                telemetry.append(message)
                if len(telemetry) >= 5:
                    break
    return hello, telemetry


def sensor(message: dict, sensor_id: str) -> dict:
    return next(
        (item for item in message.get("sensors", []) if item.get("sensorId") == sensor_id),
        {},
    )


def save_calibration(kind: str, distances: list[float]) -> None:
    if not distances:
        print(f"CALIBRATION NOT SAVED: no ultrasonic distance for {kind}.")
        return
    path = Path(__file__).with_name(f"ultrasonic_{kind}.json")
    median = round(statistics.median(distances), 2)
    path.write_text(json.dumps({"kind": kind, "medianDistanceCm": median}, indent=2), encoding="utf-8")
    print(f"Saved {kind} median distance: {median} cm")

    other_kind = "occupied" if kind == "empty" else "empty"
    other_path = Path(__file__).with_name(f"ultrasonic_{other_kind}.json")
    if other_path.exists():
        other = json.loads(other_path.read_text(encoding="utf-8"))["medianDistanceCm"]
        empty = median if kind == "empty" else float(other)
        occupied = median if kind == "occupied" else float(other)
        threshold = round((empty + occupied) / 2, 1)
        print(f"Recommended firmware setting: OCCUPIED_MAX_DISTANCE_CM = {threshold}")
        if occupied >= empty:
            print("WARNING: occupied distance should normally be shorter than empty distance.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="Windows COM port, for example COM3")
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--save-distance", choices=("empty", "occupied"))
    args = parser.parse_args()

    port_name = choose_port(args.port)
    print(f"Reading {port_name} for up to {args.seconds} seconds...")
    try:
        hello, readings = read_messages(port_name, args.seconds)
    except serial.SerialException as error:
        raise SystemExit(f"Could not open {port_name}: {error}. Close Thonny/gateway and retry.")

    if not readings:
        raise SystemExit("FAIL: no telemetry JSON received. Press ESP32 RESET once and retry.")

    latest = readings[-1]
    dht = sensor(latest, "dht22-inside")
    mlx = sensor(latest, "mlx90614-outside")
    ultrasonic = sensor(latest, "ultrasonic-parking")

    print("\n=== ESP32 QUICK RESULT ===")
    print("Firmware:", (hello or {}).get("firmwareVersion", "hello message not captured"))
    print("Device:", latest.get("deviceId"), "Spot:", latest.get("parkingSpotId"))
    print("DHT22:", "PASS" if dht.get("sensorOk") else "FAIL",
          dht.get("temperatureC"), "C", dht.get("humidityPct"), "%")
    print("MLX90614:", "PASS" if mlx.get("sensorOk") else "FAIL",
          mlx.get("temperatureC"), "C")
    print("Ultrasonic:", "PASS" if ultrasonic.get("sensorOk") else "FAIL",
          ultrasonic.get("distanceCm"), "cm", "occupied=", ultrasonic.get("occupied"))

    distances = [
        float(item["distanceCm"])
        for item in readings
        if item.get("distanceCm") is not None
    ]
    if args.save_distance:
        save_calibration(args.save_distance, distances)

    failed = [
        name
        for name, value in (
            ("DHT22", dht.get("sensorOk")),
            ("MLX90614", mlx.get("sensorOk")),
            ("Ultrasonic", ultrasonic.get("sensorOk")),
        )
        if not value
    ]
    if failed:
        raise SystemExit("SENSOR CHECK FAILED: " + ", ".join(failed))
    print("ALL ESP32 SENSORS PASSED")


if __name__ == "__main__":
    main()
