#include <Arduino.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <Wire.h>
#include <Adafruit_MLX90614.h>

// Wi-Fi를 사용하지 않습니다.
// ESP32 -> USB Serial -> 컴퓨터 Gateway -> Vercel 서버 -> 컴퓨터 -> ESP32
constexpr char DEVICE_ID[] = "esp32-bay-01";
constexpr char PARKING_SPOT_ID[] = "A-01";

// ===== 천장 센서 2개 =====
// 안쪽: 물 분사 뒤의 습도 변화까지 확인하는 DHT22
constexpr uint8_t DHT_PIN = 15;
// 바깥쪽: I2C 통신 MLX90614
constexpr uint8_t I2C_SDA_PIN = 21;
constexpr uint8_t I2C_SCL_PIN = 22;

// ===== RGB LED =====
constexpr uint8_t LED_RED_PIN = 12;
constexpr uint8_t LED_GREEN_PIN = 13;
constexpr uint8_t LED_BLUE_PIN = 14;
constexpr bool RGB_ACTIVE_HIGH = true; // 공통 양극 모듈이면 false

// ===== 화재 대응 장치 =====
constexpr uint8_t BARRIER_RELAY_PIN = 26;
constexpr uint8_t PUMP_RELAY_PIN = 27;
constexpr uint8_t STATUS_LED_PIN = 2;
constexpr uint8_t RELAY_ON = LOW;     // active-high 릴레이면 HIGH
constexpr uint8_t RELAY_OFF = HIGH;   // active-high 릴레이면 LOW

constexpr unsigned long SAMPLE_INTERVAL_MS = 2000;
constexpr unsigned long HELLO_INTERVAL_MS = 10000;
constexpr unsigned long PUMP_DELAY_MS = 5000;

// ESP32의 주황색 사전 경고 기준.
// 실제 화재 확정과 펌프 명령은 Vercel 서버가 판단합니다.
constexpr float LOCAL_WARNING_TEMP_C = 35.0f;
constexpr float LOCAL_WARNING_DELTA_C = 8.0f;
constexpr float LOCAL_FAST_RISE_C_PER_MIN = 8.0f;

DHT indoorDht(DHT_PIN, DHT22);
Adafruit_MLX90614 outdoorMlx;

unsigned long lastSampleMs = 0;
unsigned long lastHelloMs = 0;
unsigned long barrierActivatedMs = 0;
unsigned long previousIndoorTemperatureMs = 0;
uint32_t sequenceNumber = 0;
char bootId[9];

bool mlxAvailable = false;
bool emergencyActive = false;
bool pumpActive = false;
float previousIndoorTemperatureC = NAN;

enum class DisplayState {
  NORMAL,
  WARNING,
  FIRE,
  SENSOR_ERROR,
};

void sendJson(const JsonDocument &doc) {
  serializeJson(doc, Serial);
  Serial.println();
}

uint8_t rgbLevel(uint8_t value) {
  return RGB_ACTIVE_HIGH ? value : 255 - value;
}

void setRgb(uint8_t red, uint8_t green, uint8_t blue) {
  analogWrite(LED_RED_PIN, rgbLevel(red));
  analogWrite(LED_GREEN_PIN, rgbLevel(green));
  analogWrite(LED_BLUE_PIN, rgbLevel(blue));
}

void showState(DisplayState state) {
  switch (state) {
    case DisplayState::NORMAL:
      // 평상시: 노란색
      setRgb(255, 200, 0);
      break;
    case DisplayState::WARNING:
      // 주의: 주황색
      setRgb(255, 70, 0);
      break;
    case DisplayState::FIRE:
      // 서버가 화재를 확정한 상태: 빨간색
      setRgb(255, 0, 0);
      break;
    case DisplayState::SENSOR_ERROR:
      // 배선/센서 오류를 알아보기 위한 파란색
      setRgb(0, 0, 255);
      break;
  }
}

bool validTemperature(float value) {
  return isfinite(value) && value > -50.0f && value < 200.0f;
}

bool validHumidity(float value) {
  return isfinite(value) && value >= 0.0f && value <= 100.0f;
}

const char *stateName(DisplayState state) {
  switch (state) {
    case DisplayState::NORMAL: return "NORMAL";
    case DisplayState::WARNING: return "WARNING";
    case DisplayState::FIRE: return "FIRE";
    default: return "SENSOR_ERROR";
  }
}

void sendHello() {
  JsonDocument doc;
  doc["type"] = "hello";
  doc["deviceId"] = DEVICE_ID;
  doc["parkingSpotId"] = PARKING_SPOT_ID;
  doc["firmwareVersion"] = "3.0.0-two-ceiling-sensors-water-pump";
  doc["bootId"] = bootId;
  doc["emergencyActive"] = emergencyActive;
  doc["pumpActive"] = pumpActive;
  doc["mlx90614Available"] = mlxAvailable;
  doc["sensorCount"] = 2;
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
  pumpActive = false;
  digitalWrite(BARRIER_RELAY_PIN, RELAY_ON);
  digitalWrite(PUMP_RELAY_PIN, RELAY_OFF);
  digitalWrite(STATUS_LED_PIN, HIGH);
  showState(DisplayState::FIRE);
  barrierActivatedMs = millis();
}

void resetFireResponse() {
  emergencyActive = false;
  pumpActive = false;
  digitalWrite(BARRIER_RELAY_PIN, RELAY_OFF);
  digitalWrite(PUMP_RELAY_PIN, RELAY_OFF);
  digitalWrite(STATUS_LED_PIN, LOW);
  showState(DisplayState::NORMAL);
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

void addSensor(JsonArray sensors, const char *sensorId, const char *type,
               const char *zone, float temperatureC, float humidityPct = NAN) {
  JsonObject sensor = sensors.add<JsonObject>();
  sensor["sensorId"] = sensorId;
  sensor["type"] = type;
  sensor["location"] = "ceiling";
  sensor["zone"] = zone;
  sensor["sensorOk"] = validTemperature(temperatureC);

  if (validTemperature(temperatureC)) {
    sensor["temperatureC"] = roundf(temperatureC * 10.0f) / 10.0f;
  }
  if (validHumidity(humidityPct)) {
    sensor["humidityPct"] = roundf(humidityPct * 10.0f) / 10.0f;
  }
}

void sendTelemetry() {
  const unsigned long now = millis();

  // 안쪽 센서: 화재 구역의 온도와 물 분사 후 습도
  const float indoorHumidity = indoorDht.readHumidity();
  const float indoorTemperature = indoorDht.readTemperature();

  // 바깥쪽 I2C 센서: 외부 천장 주변의 온도
  float outdoorTemperature = NAN;
  float outdoorObjectTemperature = NAN;
  if (mlxAvailable) {
    outdoorTemperature = outdoorMlx.readAmbientTempC();
    outdoorObjectTemperature = outdoorMlx.readObjectTempC();
  }

  float riseCPerMin = NAN;
  if (validTemperature(indoorTemperature) &&
      validTemperature(previousIndoorTemperatureC) &&
      previousIndoorTemperatureMs != 0) {
    const float elapsedMinutes = (now - previousIndoorTemperatureMs) / 60000.0f;
    if (elapsedMinutes > 0.0f) {
      riseCPerMin =
          (indoorTemperature - previousIndoorTemperatureC) / elapsedMinutes;
    }
  }

  float insideOutsideDeltaC = NAN;
  if (validTemperature(indoorTemperature) &&
      validTemperature(outdoorTemperature)) {
    insideOutsideDeltaC = indoorTemperature - outdoorTemperature;
  }

  DisplayState displayState = DisplayState::SENSOR_ERROR;
  if (emergencyActive) {
    displayState = DisplayState::FIRE;
  } else if (validTemperature(indoorTemperature)) {
    const bool hotWarning = indoorTemperature >= LOCAL_WARNING_TEMP_C;
    const bool deltaWarning =
        isfinite(insideOutsideDeltaC) &&
        insideOutsideDeltaC >= LOCAL_WARNING_DELTA_C;
    const bool fastRiseWarning =
        isfinite(riseCPerMin) &&
        riseCPerMin >= LOCAL_FAST_RISE_C_PER_MIN;

    displayState = (hotWarning || deltaWarning || fastRiseWarning)
                       ? DisplayState::WARNING
                       : DisplayState::NORMAL;
  }
  showState(displayState);

  JsonDocument doc;
  doc["type"] = "telemetry";
  doc["deviceId"] = DEVICE_ID;
  doc["parkingSpotId"] = PARKING_SPOT_ID;
  doc["sequence"] = sequenceNumber++;
  doc["bootId"] = bootId;
  doc["sentAtMs"] = now;
  doc["emergencyActive"] = emergencyActive;
  doc["pumpActive"] = pumpActive;
  doc["localState"] = stateName(displayState);

  JsonArray sensors = doc["sensors"].to<JsonArray>();
  addSensor(sensors, "dht22-inside", "DHT22",
            "ceiling_inside_water_zone",
            indoorTemperature, indoorHumidity);
  addSensor(sensors, "mlx90614-outside", "MLX90614_I2C",
            "ceiling_outside_reference",
            outdoorTemperature);

  // 기존 Vercel 화재 판단 서버는 temperatureC와 humidityPct를 사용합니다.
  // 안쪽 DHT22 값을 대표값으로 보내 화재 구역을 기준으로 판단합니다.
  const bool indoorSensorOk =
      validTemperature(indoorTemperature) &&
      validHumidity(indoorHumidity);
  doc["sensorOk"] = indoorSensorOk;

  if (indoorSensorOk) {
    doc["temperatureC"] =
        roundf(indoorTemperature * 10.0f) / 10.0f;
    doc["humidityPct"] =
        roundf(indoorHumidity * 10.0f) / 10.0f;
  } else {
    doc["error"] = "INDOOR_DHT22_READ_FAILED";
  }

  if (validTemperature(outdoorTemperature)) {
    doc["outsideTemperatureC"] =
        roundf(outdoorTemperature * 10.0f) / 10.0f;
  }
  if (validTemperature(outdoorObjectTemperature)) {
    doc["outsideObjectTemperatureC"] =
        roundf(outdoorObjectTemperature * 10.0f) / 10.0f;
  }
  if (isfinite(insideOutsideDeltaC)) {
    doc["insideOutsideDeltaC"] =
        roundf(insideOutsideDeltaC * 10.0f) / 10.0f;
  }
  if (isfinite(riseCPerMin)) {
    doc["riseCPerMin"] =
        roundf(riseCPerMin * 10.0f) / 10.0f;
  }

  if (validTemperature(indoorTemperature)) {
    previousIndoorTemperatureC = indoorTemperature;
    previousIndoorTemperatureMs = now;
  }

  sendJson(doc);
}

void setup() {
  pinMode(LED_RED_PIN, OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_BLUE_PIN, OUTPUT);
  pinMode(BARRIER_RELAY_PIN, OUTPUT);
  pinMode(PUMP_RELAY_PIN, OUTPUT);
  pinMode(STATUS_LED_PIN, OUTPUT);

  Serial.begin(115200);
  Serial.setTimeout(50);
  snprintf(bootId, sizeof(bootId), "%08lx",
           static_cast<unsigned long>(esp_random()));

  indoorDht.begin();
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  mlxAvailable = outdoorMlx.begin(); // MLX90614 기본 주소: 0x5A

  resetFireResponse();
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

  // 화재 확정 명령 후 차단막이 내려갈 시간을 준 다음 물 펌프를 켭니다.
  if (emergencyActive && !pumpActive &&
      now - barrierActivatedMs >= PUMP_DELAY_MS) {
    pumpActive = true;
    digitalWrite(PUMP_RELAY_PIN, RELAY_ON);
  }
}
