# Thonny용 ESP32 설치 및 안전 배선

## 업로드 전에 반드시 바꿀 배선

### RGB LED

| LED 선 | ESP32 |
|---|---|
| `-` | `GND` |
| `R` | `D12 / GPIO12` |
| `G` | `D13 / GPIO13` |
| `B` | `D14 / GPIO14` |

공통 음극 RGB LED를 기준으로 한다. 공통 양극이면 `main.py`의
`RGB_COMMON_CATHODE`를 `False`로 변경한다.

### DHT22 온습도 센서

| 센서 선 | ESP32 |
|---|---|
| `+` | `3V3` |
| `OUT` | `D15 / GPIO15` |
| `-` | `GND` |

### 초음파 센서

현재의 `GND -> D4`, `VCC -> D5` 연결을 제거해야 한다.

| 센서 선 | ESP32 |
|---|---|
| `GND` | `GND` |
| `VCC` | `5V / VIN` (센서 정격 확인) |
| `Trig` | `D17 / GPIO17` |
| `Echo` | 전압 분배 회로를 거쳐 `D16 / GPIO16` |

HC-SR04의 Echo는 5V이므로 ESP32 GPIO에 직접 연결하지 않는다. 예를 들어
Echo와 GPIO16 사이에 1kΩ, GPIO16과 GND 사이에 2kΩ을 연결해 약 3.3V로
낮춘다.

초음파 센서를 나중에 연결하려면 현재는 네 선을 모두 분리하고
`ULTRASONIC_ENABLED = False`를 유지한다. 안전 배선이 완료된 뒤에만
`ULTRASONIC_ENABLED = True`로 변경해 다시 업로드한다.

### GDA5010 팬

팬의 빨간 선과 검은 선을 GPIO23과 GPIO22 사이에 직접 연결하지 않는다.
GPIO는 팬 전원 공급용이 아니며 ESP32가 손상될 수 있다.

- 팬 빨간 선: 팬 라벨에 적힌 정격 외부 전원 `+`
- 팬 검은 선: N채널 MOSFET의 Drain
- MOSFET Source: `GND`
- MOSFET Gate: `D23 / GPIO23` (100Ω 정도 직렬 저항 권장)
- Gate와 GND 사이: 10kΩ 풀다운 저항
- 외부 전원 GND와 ESP32 GND를 공통 연결
- 필요한 역전압 보호 부품 사용
- `D22 / GPIO22`에는 팬을 연결하지 않음

안전한 구동 회로를 만든 뒤 `main.py`의 `FAN_ENABLED = False`를
`FAN_ENABLED = True`로 변경한다. 기본 속도는 35%이다.

## 차단막과 워터펌프

코드에는 다음 동작이 미리 포함되어 있다.

1. 서버의 `ACTIVATE_FIRE_RESPONSE` 수신
2. LED를 빨간색으로 변경
3. 차단막 릴레이를 즉시 켬
4. 5초 후 워터펌프 릴레이를 켬
5. `RESET_FIRE_RESPONSE` 수신 시 두 릴레이를 모두 끔

기본 설정은 `ACTUATORS_ENABLED = False`이므로 GPIO26과 GPIO27은 입력
상태이며 장치를 작동하지 않는다. 릴레이, 모터 드라이버, 외부 전원,
방수·절연 및 비상 정지 장치를 안전하게 구성한 뒤에만 `True`로 변경한다.

| 기능 | ESP32 제어 핀 |
|---|---|
| 차단막 릴레이/모터 드라이버 입력 | `D26 / GPIO26` |
| 워터펌프 릴레이/MOSFET 입력 | `D27 / GPIO27` |

차단막 모터와 펌프를 GPIO에 직접 연결하지 않는다. 장치 정격에 맞는 별도
전원과 드라이버를 사용하고, 저전압 제어부와 물이 닿는 부분을 물리적으로
분리한다. 실제 차단막에는 리미트 스위치와 수동 비상 정지 기능도 필요하다.

## Thonny 업로드

1. ESP32를 `COM3`으로 연결한다.
2. Thonny에서 `도구 > 옵션 > 인터프리터`를 연다.
3. 인터프리터를 `MicroPython (ESP32)`로 선택하고 포트를 `COM3`으로 정한다.
4. MicroPython이 설치되지 않았다면 같은 화면의 펌웨어 설치 기능으로
   ESP32용 MicroPython을 설치한다. 이 과정은 보드의 기존 프로그램을 지운다.
5. `micropython/main.py`를 Thonny에서 연다.
6. `파일 > 다른 이름으로 저장 > MicroPython 장치`를 선택한다.
7. 장치의 파일 이름을 반드시 `main.py`로 저장한다.
8. Thonny의 중지 버튼을 누른 뒤 ESP32의 EN/RESET 버튼을 누른다.
9. Shell에 JSON 한 줄이 2초마다 출력되는지 확인한다.
10. 시험이 끝나면 Thonny를 닫아 COM3을 해제하고 관리 컴퓨터에서
    `gateway.py`를 실행한다. Thonny와 gateway.py는 COM3을 동시에 사용할 수 없다.

## 주차 감지 거리 조정

`OCCUPIED_MAX_DISTANCE_CM = 100.0`은 예시값이다. 차가 없을 때와 있을 때의
`distanceCm` 값을 확인한 뒤 두 거리 사이의 값으로 변경한다.

예: 빈 주차면 220cm, 차량 지붕 70cm라면 120cm 정도로 설정할 수 있다.
