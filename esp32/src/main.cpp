#include <Arduino.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Wire.h>
#include <Adafruit_MLX90614.h>

// Wi-Fi를 사용하지 않고 USB Serial로 컴퓨터 Gateway와 통신합니다.
constexpr char DEVICE_ID[] = "esp32-bay-01";
constexpr char PARKING_SPOT_ID[] = "A-01";

// 모든 온도 센서는 천장에 설치합니다.
constexpr uint8_t DHT_PIN = 15;       // 천장 주변 공기/습도
constexpr uint8_t DS18B20_PIN = 18;   // 천장 여러 구역의 DS18B20 공통 1-Wire
constexpr uint8_t I2C_SDA_PIN = 21;   // 천장 MLX90614 SDA
constexpr uint8_t I2C_SCL_PIN = 22;   // 천장 MLX90614 SCL

constexpr uint8_t LED_RED_PIN = 12;
constexpr uint8_t LED_GREEN_PIN = 13;
constexpr uint8_t LED_BLUE_PIN = 14;
constexpr uint8_t FAN_CONTROL_PIN = 23; // MOSFET/트랜지스터 제어
constexpr uint8_t BUZZER_PIN = 25;
constexpr uint8_t BARRIER_RELAY_PIN = 26;
constexpr uint8_t PUMP_RELAY_PIN = 27;
constexpr uint8_t STATUS_LED_PIN = 2;

constexpr uint8_t RELAY_ON = LOW;
constexpr uint8_t RELAY_OFF = HIGH;
constexpr bool RGB_ACTIVE_HIGH = true;    // 공통 양극 RGB면 false
constexpr bool ENABLE_WATER_PUMP = false; // 학교 모형은 팬만 사용

constexpr unsigned long SAMPLE_INTERVAL_MS = 2000;
constexpr unsigned long HELLO_INTERVAL_MS = 10000;
constexpr unsigned long PUMP_DELAY_MS = 5000;
constexpr float WARNING_TEMP_C = 35.0f;
constexpr float DANGER_TEMP_C = 45.0f;
constexpr float FAST_RISE_C_PER_MIN = 8.0f;
constexpr uint8_t MAX_DS18B20_SENSORS = 6;

DHT dht(DHT_PIN, DHT22);
OneWire oneWire(DS18B20_PIN);
DallasTemperature ds18b20(&oneWire);
Adafruit_MLX90614 mlx90614;

unsigned long lastSampleMs = 0;
unsigned long lastHelloMs = 0;
unsigned long barrierActivatedMs = 0;
unsigned long previousTemperatureMs = 0;
uint32_t sequenceNumber = 0;
char bootId[9];
bool mlxAvailable = false;
bool emergencyActive = false;
bool pumpActive = false;
float previousMaxTemperatureC = NAN;

enum class LocalState { NORMAL, WARNING, DANGER, FAST_RISE, SENSOR_ERROR };

void sendJson(const JsonDocument &doc) {
  serializeJson(doc, Serial);
  Serial.println();
}

void setRgb(bool red, bool green, bool blue) {
  digitalWrite(LED_RED_PIN, RGB_ACTIVE_HIGH ? red : !red);
  digitalWrite(LED_GREEN_PIN, RGB_ACTIVE_HIGH ? green : !green);
  digitalWrite(LED_BLUE_PIN, RGB_ACTIVE_HIGH ? blue : !blue);
}

void fanOn() { digitalWrite(FAN_CONTROL_PIN, HIGH); }
void fanOff() { digitalWrite(FAN_CONTROL_PIN, LOW); }
void buzzerOn() { digitalWrite(BUZZER_PIN, HIGH); }
void buzzerOff() { digitalWrite(BUZZER_PIN, LOW); }

const char *stateName(LocalState state) {
  switch (state) {
    case LocalState::NORMAL: return "NORMAL";
    case LocalState::WARNING: return "WARNING";
    case LocalState::DANGER: return "DANGER";
    case LocalState::FAST_RISE: return "DANGER_FAST_RISE";
    default: return "SENSOR_ERROR";
  }
}

void applyOutputs(LocalState state) {
  if (emergencyActive) {
    setRgb(true, false, false);
    fanOn();
    buzzerOn();
    return;
  }

  switch (state) {
    case LocalState::NORMAL:
      setRgb(false, true, false);
      fanOff();
      buzzerOff();
      break;
    case LocalState::WARNING:
      setRgb(true, true, false);
      fanOff();
      buzzerOff();
      break;
    case LocalState::DANGER:
      setRgb(true, false, false);
      fanOn();
      buzzerOn();
      break;
    case LocalState::FAST_RISE:
      setRgb(true, false, true);
      fanOn();
      buzzerOn();
      break;
    case LocalState::SENSOR_ERROR:
      setRgb(false, false, true);
      fanOff();
      buzzerOff();
      break;
  }
}

bool validTemperature(float value) {
  return isfinite(value) && value > -55.0f && value < 200.0f;
}

void addSensor(JsonArray sensors, const char *sensorId, const char *type,
               const char *ceilingZone, float temperatureC) {
  JsonObject sensor = sensors.add<JsonObject>();
  sensor["sensorId"] = sensorId;
  sensor["type"] = type;
  sensor["location"] = "ceiling";
  sensor["ceilingZone"] = ceilingZone;
  sensor["sensorOk"] = validTemperature(temperatureC);
  if (validTemperature(temperatureC)) {
    sensor["temperatureC"] = roundf(temperatureC * 10.0f) / 10.0f;
  }
}

void sendHello() {
  uint8_t dsCount = ds18b20.getDeviceCount();
  if (dsCount > MAX_DS18B20_SENSORS) dsCount = MAX_DS18B20_SENSORS;

  JsonDocument doc;
  doc["type"] = "hello";
  doc["deviceId"] = DEVICE_ID;
  doc["parkingSpotId"] = PARKING_SPOT_ID;
  doc["firmwareVersion"] = "2.1.0-ceiling-multi-sensor";
  doc["bootId"] = bootId;
  doc["emergencyActive"] = emergencyActive;
  doc["ds18b20Count"] = dsCount;
  doc["mlx90614Available"] = mlxAvailable;
  doc["sensorPlacement"] = "ceiling";
  sendJson(doc);
}

void sendCommandAck(const char *commandId, const char *status) {
  JsonDocument doc;
  doc["type"] = "commandAck";
  doc["deviceId"] = DEVICE_ID;
  doc["commandId"] = commandId;
  doc["status"] = status;
  sendJson(doc);
}

void activateFireResponse() {
  if (emergencyActive) return;
  emergencyActive = true;
  digitalWrite(BARRIER_RELAY_PIN, RELAY_ON);
  digitalWrite(STATUS_LED_PIN, HIGH);
  fanOn();
  buzzerOn();
  barrierActivatedMs = millis();
}

void resetFireResponse() {
  emergencyActive = false;
  pumpActive = false;
  digitalWrite(BARRIER_RELAY_PIN, RELAY_OFF);
  digitalWrite(PUMP_RELAY_PIN, RELAY_OFF);
  digitalWrite(STATUS_LED_PIN, LOW);
  fanOff();
  buzzerOff();
}

void handleCommand(const String &line) {
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, line);
  if (error || doc["type"] != "command") return;

  const char *commandId = doc["commandId"] | "unknown";
  const char *action = doc["action"] | "";

  if (strcmp(action, "ACTIVATE_FIRE_RESPONSE") == 0) {
    activateFireResponse();
    sendCommandAck(commandId, "executed");
  } else if (strcmp(action, "RESET_FIRE_RESPONSE") == 0) {
    resetFireResponse();
    sendCommandAck(commandId, "executed");
  } else {
    sendCommandAck(commandId, "rejected_unknown_action");
  }
}

void sendTelemetry() {
  const unsigned long now = millis();
  JsonDocument doc;
  doc["type"] = "telemetry";
  doc["deviceId"] = DEVICE_ID;
  doc["parkingSpotId"] = PARKING_SPOT_ID;
  doc["sequence"] = sequenceNumber++;
  doc["bootId"] = bootId;
  doc["sentAtMs"] = now;
  doc["emergencyActive"] = emergencyActive;
  doc["sensorPlacement"] = "ceiling";

  JsonArray sensors = doc["sensors"].to<JsonArray>();
  float maxTemperatureC = -1000.0f;
  uint8_t validCount = 0;

  const float humidity = dht.readHumidity();
  const float dhtTemperature = dht.readTemperature();
  addSensor(sensors, "dht22-ceiling", "DHT22", "ceiling_center", dhtTemperature);
  if (validTemperature(dhtTemperature)) {
    maxTemperatureC = max(maxTemperatureC, dhtTemperature);
    validCount++;
  }

  ds18b20.requestTemperatures();
  uint8_t dsCount = ds18b20.getDeviceCount();
  if (dsCount > MAX_DS18B20_SENSORS) dsCount = MAX_DS18B20_SENSORS;

  for (uint8_t index = 0; index < dsCount; index++) {
    const float temperature = ds18b20.getTempCByIndex(index);
    char sensorId[24];
    char ceilingZone[24];
    snprintf(sensorId, sizeof(sensorId), "ds18b20-ceiling-%u", index);
    snprintf(ceilingZone, sizeof(ceilingZone), "ceiling_zone_%u", index);
    addSensor(sensors, sensorId, "DS18B20", ceilingZone, temperature);
    if (validTemperature(temperature)) {
      maxTemperatureC = max(maxTemperatureC, temperature);
      validCount++;
    }
  }

  if (mlxAvailable) {
    const float objectTemperature = mlx90614.readObjectTempC();
    const float ambientTemperature = mlx90614.readAmbientTempC();
    addSensor(sensors, "mlx90614-ceiling", "MLX90614_I2C",
              "ceiling_above_vehicle", objectTemperature);
    if (validTemperature(ambientTemperature)) {
      doc["mlxAmbientC"] = roundf(ambientTemperature * 10.0f) / 10.0f;
    }
    if (validTemperature(objectTemperature)) {
      maxTemperatureC = max(maxTemperatureC, objectTemperature);
      validCount++;
    }
  } else {
    addSensor(sensors, "mlx90614-ceiling", "MLX90614_I2C",
              "ceiling_above_vehicle", NAN);
  }

  doc["sensorOk"] = validCount > 0;
  doc["validTemperatureCount"] = validCount;
  if (validCount > 0) {
    // 기존 서버는 temperatureC 하나를 사용하므로 가장 높은 값을 대표값으로 보냅니다.
    doc["temperatureC"] = roundf(maxTemperatureC * 10.0f) / 10.0f;
  } else {
    doc["error"] = "ALL_TEMPERATURE_SENSORS_FAILED";
  }
  if (isfinite(humidity) && humidity >= 0.0f && humidity <= 100.0f) {
    doc["humidityPct"] = roundf(humidity * 10.0f) / 10.0f;
  }

  float riseCPerMin = NAN;
  if (validCount > 0 && isfinite(previousMaxTemperatureC) && previousTemperatureMs != 0) {
    const float elapsedMinutes = (now - previousTemperatureMs) / 60000.0f;
    if (elapsedMinutes > 0.0f) {
      riseCPerMin = (maxTemperatureC - previousMaxTemperatureC) / elapsedMinutes;
    }
  }
  if (isfinite(riseCPerMin)) {
    doc["riseCPerMin"] = roundf(riseCPerMin * 10.0f) / 10.0f;
  }

  LocalState state = LocalState::SENSOR_ERROR;
  if (validCount > 0) {
    if (isfinite(riseCPerMin) && riseCPerMin >= FAST_RISE_C_PER_MIN) {
      state = LocalState::FAST_RISE;
    } else if (maxTemperatureC >= DANGER_TEMP_C) {
      state = LocalState::DANGER;
    } else if (maxTemperatureC >= WARNING_TEMP_C) {
      state = LocalState::WARNING;
    } else {
      state = LocalState::NORMAL;
    }
    previousMaxTemperatureC = maxTemperatureC;
    previousTemperatureMs = now;
  }

  doc["localState"] = stateName(state);
  applyOutputs(state);
  sendJson(doc);
}

void setup() {
  pinMode(LED_RED_PIN, OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_BLUE_PIN, OUTPUT);
  pinMode(FAN_CONTROL_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(BARRIER_RELAY_PIN, OUTPUT);
  pinMode(PUMP_RELAY_PIN, OUTPUT);
  pinMode(STATUS_LED_PIN, OUTPUT);

  resetFireResponse();
  setRgb(false, false, true);

  Serial.begin(115200);
  Serial.setTimeout(50);
  snprintf(bootId, sizeof(bootId), "%08lx",
           static_cast<unsigned long>(esp_random()));

  dht.begin();
  ds18b20.begin();
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  mlxAvailable = mlx90614.begin(); // 기본 주소 0x5A
  delay(1000);
  sendHello();
}

void loop() {
  const unsigned long now = millis();

  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) handleCommand(line);
  }

  if (now - lastSampleMs >= SAMPLE_INTERVAL_MS) {
    lastSampleMs = now;
    sendTelemetry();
  }

  if (now - lastHelloMs >= HELLO_INTERVAL_MS) {
    lastHelloMs = now;
    sendHello();
  }

  if (ENABLE_WATER_PUMP && emergencyActive && !pumpActive &&
      now - barrierActivatedMs >= PUMP_DELAY_MS) {
    pumpActive = true;
    digitalWrite(PUMP_RELAY_PIN, RELAY_ON);
  }
}
