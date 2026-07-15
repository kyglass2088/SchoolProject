"""EV fire parking demo firmware for MicroPython on ESP32.

Data flow:
ESP32 -> USB serial -> computer/gateway.py -> Vercel
Vercel -> computer/gateway.py -> USB serial -> ESP32

Before enabling the fan, read README_THONNY.md and use a transistor/MOSFET.
Never power a fan or ultrasonic sensor from a GPIO pin.
"""

from machine import I2C, Pin, PWM, time_pulse_us, unique_id
import dht
import json
import select
import sys
import time
import ubinascii


DEVICE_ID = "esp32-bay-01"
PARKING_SPOT_ID = "A-01"

# Confirmed RGB LED wiring (common cathode: '-' -> GND)
LED_RED_PIN = 12
LED_GREEN_PIN = 14
LED_BLUE_PIN = 13
RGB_COMMON_CATHODE = True

# DHT22: + -> 3V3, OUT -> GPIO33, - -> GND
DHT_PIN = 33

# Outside MLX90614 I2C temperature sensor.
# VIN -> 3V3, GND -> GND, SDA -> GPIO2, SCL -> GPIO15.
I2C_SDA_PIN = 2
I2C_SCL_PIN = 15
MLX90614_ADDRESS = 0x5A
MLX90614_ENABLED = True

# Ultrasonic signal pins. VCC must use the sensor's rated power pin, not GPIO26.
ULTRASONIC_ECHO_PIN = 25
ULTRASONIC_TRIG_PIN = 27
# Enabled only after VCC is moved away from GPIO26 to the rated power pin.
ULTRASONIC_ENABLED = True

# Adjust this after measuring the empty-space distance from the ceiling.
# A measured distance at or below this value means that a car is present.
OCCUPIED_MAX_DISTANCE_CM = 100.0
OCCUPANCY_CONFIRM_SAMPLES = 3

# Local orange warning. The Vercel server makes the final fire decision.
LOCAL_WARNING_TEMP_C = 35.0
LOCAL_FAST_RISE_C_PER_MIN = 8.0
LOCAL_WARNING_DELTA_C = 8.0

# GPIO23 may drive only a transistor/MOSFET gate or a proper fan controller.
# Keep False while the fan is directly connected to GPIO23/GPIO22.
FAN_CONTROL_PIN = 23
FAN_ENABLED = False
FAN_DUTY_PERCENT = 35

# Fire-response outputs. Use only relay/MOSFET/motor-driver control inputs.
# Never connect a barrier motor or water pump directly to an ESP32 GPIO.
BARRIER_RELAY_PIN = 26
# GPIO27 is now used by the ultrasonic Trig wire.
PUMP_RELAY_PIN = 32
ACTUATORS_ENABLED = False
RELAY_ACTIVE_LOW = True
PUMP_DELAY_MS = 5000

SAMPLE_INTERVAL_MS = 2000
HELLO_INTERVAL_MS = 10000


def make_pwm(pin_number, frequency=1000):
    output = PWM(Pin(pin_number, Pin.OUT), freq=frequency)
    output.duty_u16(0)
    return output


red_pwm = make_pwm(LED_RED_PIN)
green_pwm = make_pwm(LED_GREEN_PIN)
blue_pwm = make_pwm(LED_BLUE_PIN)


def rgb_duty(value):
    value = max(0, min(255, int(value)))
    duty = value * 257
    return duty if RGB_COMMON_CATHODE else 65535 - duty


def set_rgb(red, green, blue):
    red_pwm.duty_u16(rgb_duty(red))
    green_pwm.duty_u16(rgb_duty(green))
    blue_pwm.duty_u16(rgb_duty(blue))


def show_state(state):
    if state == "EMPTY":
        set_rgb(0, 255, 0)       # green
    elif state == "PARKED":
        set_rgb(255, 200, 0)     # yellow
    elif state == "WARNING":
        set_rgb(255, 70, 0)      # orange
    elif state == "FIRE":
        set_rgb(255, 0, 0)       # red
    else:
        set_rgb(0, 0, 255)       # blue: startup/sensor error


fan_pwm = None
if FAN_ENABLED:
    fan_pwm = make_pwm(FAN_CONTROL_PIN, 25000)
    # Brief full-speed start helps a two-wire fan begin rotating.
    fan_pwm.duty_u16(65535)
    time.sleep_ms(700)
    fan_pwm.duty_u16(int(65535 * FAN_DUTY_PERCENT / 100))
else:
    # High-impedance input is safer while the fan wiring is not corrected.
    Pin(FAN_CONTROL_PIN, Pin.IN)
    Pin(22, Pin.IN)


def relay_level(active):
    if RELAY_ACTIVE_LOW:
        return 0 if active else 1
    return 1 if active else 0


if ACTUATORS_ENABLED:
    barrier_relay = Pin(
        BARRIER_RELAY_PIN, Pin.OUT, value=relay_level(False)
    )
    pump_relay = Pin(
        PUMP_RELAY_PIN, Pin.OUT, value=relay_level(False)
    )
else:
    # Inputs are high impedance while no safe driver circuit is connected.
    barrier_relay = Pin(BARRIER_RELAY_PIN, Pin.IN)
    pump_relay = Pin(PUMP_RELAY_PIN, Pin.IN)


indoor_dht = dht.DHT22(Pin(DHT_PIN))
ultrasonic_trig = Pin(ULTRASONIC_TRIG_PIN, Pin.OUT, value=0)
ultrasonic_echo = Pin(ULTRASONIC_ECHO_PIN, Pin.IN)
i2c = I2C(0, sda=Pin(I2C_SDA_PIN), scl=Pin(I2C_SCL_PIN), freq=100000)
try:
    mlx90614_available = (
        MLX90614_ENABLED and MLX90614_ADDRESS in i2c.scan()
    )
except Exception:
    mlx90614_available = False

boot_id = ubinascii.hexlify(unique_id()).decode()[-8:]
sequence_number = 0
emergency_active = False
barrier_active = False
pump_active = False
barrier_started_ms = None
occupied = False
occupancy_candidate = False
occupancy_candidate_count = 0
previous_temperature_c = None
previous_temperature_ms = None
last_sample_ms = time.ticks_ms()
last_hello_ms = time.ticks_ms()

serial_poll = select.poll()
serial_poll.register(sys.stdin, select.POLLIN)


def send_json(message):
    print(json.dumps(message))


def send_hello():
    send_json({
        "type": "hello",
        "deviceId": DEVICE_ID,
        "parkingSpotId": PARKING_SPOT_ID,
        "firmwareVersion": "4.1.0-micropython-dht-mlx-ultrasonic",
        "bootId": boot_id,
        "emergencyActive": emergency_active,
        "fanEnabled": FAN_ENABLED,
        "actuatorsEnabled": ACTUATORS_ENABLED,
        "barrierActive": barrier_active,
        "pumpActive": pump_active,
        "ultrasonicEnabled": ULTRASONIC_ENABLED,
        "mlx90614Available": mlx90614_available,
        "i2cSdaPin": I2C_SDA_PIN,
        "i2cSclPin": I2C_SCL_PIN,
        "sensorCount": 1 + int(mlx90614_available) + int(ULTRASONIC_ENABLED),
    })


def send_command_ack(command_id, status):
    send_json({
        "type": "commandAck",
        "deviceId": DEVICE_ID,
        "commandId": command_id,
        "status": status,
    })


def handle_command(line):
    global emergency_active, barrier_active, pump_active, barrier_started_ms

    try:
        message = json.loads(line)
    except Exception:
        return

    if message.get("type") != "command":
        return

    command_id = message.get("commandId", "unknown")
    action = message.get("action", "")

    if action == "ACTIVATE_FIRE_RESPONSE":
        emergency_active = True
        if ACTUATORS_ENABLED:
            barrier_active = True
            pump_active = False
            barrier_started_ms = time.ticks_ms()
            barrier_relay.value(relay_level(True))
            pump_relay.value(relay_level(False))
        show_state("FIRE")
        send_command_ack(command_id, "executed")
    elif action == "RESET_FIRE_RESPONSE":
        emergency_active = False
        barrier_active = False
        pump_active = False
        barrier_started_ms = None
        if ACTUATORS_ENABLED:
            barrier_relay.value(relay_level(False))
            pump_relay.value(relay_level(False))
        send_command_ack(command_id, "executed")
    else:
        send_command_ack(command_id, "rejected_unknown_action")


def read_serial_commands():
    while serial_poll.poll(0):
        line = sys.stdin.readline()
        if not line:
            return
        line = line.strip()
        if line:
            handle_command(line)


def read_distance_cm():
    if not ULTRASONIC_ENABLED:
        return None

    ultrasonic_trig.off()
    time.sleep_us(2)
    ultrasonic_trig.on()
    time.sleep_us(10)
    ultrasonic_trig.off()

    try:
        duration_us = time_pulse_us(ultrasonic_echo, 1, 30000)
    except OSError:
        return None

    if duration_us < 0:
        return None
    return duration_us / 58.0


def update_occupancy(distance_cm):
    global occupied, occupancy_candidate, occupancy_candidate_count

    if distance_cm is None:
        return occupied

    measured = distance_cm <= OCCUPIED_MAX_DISTANCE_CM
    if measured != occupancy_candidate:
        occupancy_candidate = measured
        occupancy_candidate_count = 1
    else:
        occupancy_candidate_count += 1

    if occupancy_candidate_count >= OCCUPANCY_CONFIRM_SAMPLES:
        occupied = occupancy_candidate
    return occupied


def read_dht():
    try:
        indoor_dht.measure()
        temperature_c = float(indoor_dht.temperature())
        humidity_pct = float(indoor_dht.humidity())
        if not (-50.0 < temperature_c < 200.0 and 0.0 <= humidity_pct <= 100.0):
            return None, None
        return temperature_c, humidity_pct
    except Exception:
        return None, None


def read_mlx90614_register(register):
    if not mlx90614_available:
        return None
    try:
        data = i2c.readfrom_mem(MLX90614_ADDRESS, register, 3)
        raw = data[0] | (data[1] << 8)
        if raw & 0x8000:
            return None
        temperature_c = raw * 0.02 - 273.15
        if not (-50.0 < temperature_c < 380.0):
            return None
        return temperature_c
    except Exception:
        return None


def read_mlx90614():
    # 0x06: ambient temperature, 0x07: object temperature.
    return read_mlx90614_register(0x06), read_mlx90614_register(0x07)


def rounded(value):
    return None if value is None else round(value, 1)


def send_telemetry():
    global sequence_number, previous_temperature_c, previous_temperature_ms

    now = time.ticks_ms()
    temperature_c, humidity_pct = read_dht()
    outside_temperature_c, outside_object_temperature_c = read_mlx90614()
    distance_cm = read_distance_cm()
    is_occupied = update_occupancy(distance_cm)

    rise_c_per_min = None
    if temperature_c is not None and previous_temperature_c is not None:
        elapsed_ms = time.ticks_diff(now, previous_temperature_ms)
        if elapsed_ms > 0:
            rise_c_per_min = (
                (temperature_c - previous_temperature_c) * 60000.0 / elapsed_ms
            )

    warning = False
    if temperature_c is not None:
        warning = temperature_c >= LOCAL_WARNING_TEMP_C
    if rise_c_per_min is not None:
        warning = warning or rise_c_per_min >= LOCAL_FAST_RISE_C_PER_MIN
    inside_outside_delta_c = None
    if temperature_c is not None and outside_temperature_c is not None:
        inside_outside_delta_c = temperature_c - outside_temperature_c
        warning = warning or inside_outside_delta_c >= LOCAL_WARNING_DELTA_C

    if emergency_active:
        local_state = "FIRE"
    elif warning:
        local_state = "WARNING"
    elif is_occupied:
        local_state = "PARKED"
    else:
        local_state = "EMPTY"
    show_state(local_state)

    sensor_ok = temperature_c is not None and humidity_pct is not None
    message = {
        "type": "telemetry",
        "deviceId": DEVICE_ID,
        "parkingSpotId": PARKING_SPOT_ID,
        "bootId": boot_id,
        "sequence": sequence_number,
        "sentAtMs": now,
        "sensorOk": sensor_ok,
        "emergencyActive": emergency_active,
        "actuatorsEnabled": ACTUATORS_ENABLED,
        "barrierActive": barrier_active,
        "pumpActive": pump_active,
        "localState": local_state,
        "occupied": is_occupied,
        "distanceCm": rounded(distance_cm),
        "sensors": [
            {
                "sensorId": "dht22-inside",
                "type": "DHT22",
                "location": "ceiling",
                "sensorOk": sensor_ok,
                "temperatureC": rounded(temperature_c),
                "humidityPct": rounded(humidity_pct),
            },
            {
                "sensorId": "ultrasonic-parking",
                "type": "ULTRASONIC",
                "location": "ceiling",
                "sensorOk": distance_cm is not None,
                "distanceCm": rounded(distance_cm),
                "occupied": is_occupied,
            },
            {
                "sensorId": "mlx90614-outside",
                "type": "MLX90614_I2C",
                "location": "ceiling_outside_reference",
                "sensorOk": outside_temperature_c is not None,
                "temperatureC": rounded(outside_temperature_c),
                "objectTemperatureC": rounded(outside_object_temperature_c),
            },
        ],
    }

    # These top-level values are used by the existing Vercel fire detector.
    if sensor_ok:
        message["temperatureC"] = rounded(temperature_c)
        message["humidityPct"] = rounded(humidity_pct)
    else:
        message["error"] = "INDOOR_DHT22_READ_FAILED"
    if rise_c_per_min is not None:
        message["riseCPerMin"] = rounded(rise_c_per_min)
    if outside_temperature_c is not None:
        message["outsideTemperatureC"] = rounded(outside_temperature_c)
    if outside_object_temperature_c is not None:
        message["outsideObjectTemperatureC"] = rounded(
            outside_object_temperature_c
        )
    if inside_outside_delta_c is not None:
        message["insideOutsideDeltaC"] = rounded(inside_outside_delta_c)

    send_json(message)
    sequence_number += 1

    if temperature_c is not None:
        previous_temperature_c = temperature_c
        previous_temperature_ms = now


show_state("STARTUP")
send_hello()

while True:
    if (
        ACTUATORS_ENABLED
        and emergency_active
        and barrier_active
        and not pump_active
        and barrier_started_ms is not None
        and time.ticks_diff(time.ticks_ms(), barrier_started_ms) >= PUMP_DELAY_MS
    ):
        pump_active = True
        pump_relay.value(relay_level(True))

    read_serial_commands()
    now = time.ticks_ms()

    if time.ticks_diff(now, last_sample_ms) >= SAMPLE_INTERVAL_MS:
        last_sample_ms = now
        send_telemetry()

    if time.ticks_diff(now, last_hello_ms) >= HELLO_INTERVAL_MS:
        last_hello_ms = now
        send_hello()

    time.sleep_ms(20)
