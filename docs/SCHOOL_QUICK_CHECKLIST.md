# 학교 ESP32 빠른 점검표

목표는 실제 불이나 실제 차량 없이 센서·통신·LED·제어 명령까지만 확인하는 것이다.
펌프에 물을 넣거나 모터를 직접 연결한 시험은 마지막 안전 점검 전에는 하지 않는다.

## 전날 준비

- 노트북 충전, 인터넷 연결, 휴대전화 APK와 알림 권한 확인
- USB **데이터** 케이블, 브레드보드, 점퍼선, LED 저항 준비
- 초음파 센서가 5V ECHO를 출력하는 모델이면 ECHO 분압 저항 준비
- 차단막 모터·펌프용 릴레이/MOSFET 드라이버, 역기전력 보호, 별도 전원 준비
- ESP32·센서·드라이버의 GND는 공통으로 연결하되 모터/펌프를 GPIO에서 직접 공급하지 않음

## 0~5분: 전원을 끈 상태에서 배선 확인

| 부품 | ESP32 |
|---|---|
| RGB R / B / G / - | GPIO12 / GPIO13 / GPIO14 / GND |
| DHT22 + / OUT / - | 3V3 / GPIO33 / GND |
| MLX90614 VIN / GND / SDA / SCL | 3V3 / GND / GPIO2 / GPIO15 |
| 초음파 GND / TRIG / ECHO / VCC | GND / GPIO27 / GPIO25 / 센서 정격 전원 |
| 차단막 드라이버 입력 | GPIO26 |
| 펌프 드라이버 입력 | GPIO32 |

GPIO2·GPIO15 때문에 부팅이 불안정할 때만 MLX90614를 SDA=GPIO21, SCL=GPIO22로
옮기고 펌웨어 핀 번호도 함께 바꾼다.

## 5~10분: 센서 자동검사

Thonny와 `gateway.py`를 모두 닫고 다음 파일을 실행한다.

```text
C:\Users\김병욱\Documents\Codex\2026-07-14\new-chat-2\school_esp32_check.cmd
```

정상 결과는 `ALL ESP32 SENSORS PASSED`이다. 실패별 우선 점검:

- COM 없음: 데이터 케이블, CH340 드라이버, 장치 관리자
- DHT22 실패: +/OUT/- 방향, GPIO33, 3V3/GND
- MLX90614 실패: VIN/GND, SDA/SCL 뒤바뀜, I2C 주소 0x5A
- 초음파 실패: VCC를 GPIO에 연결하지 않았는지, TRIG27/ECHO25/GND

## 10~15분: 초음파 거리 보정

차량 모형이 없을 때와 있을 때 각각 PowerShell에서 실행한다.

```powershell
cd C:\Users\김병욱\Documents\Codex\2026-07-14\new-chat-2\outputs\ev-fire-parking\computer
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" check_esp32.py --save-distance empty
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" check_esp32.py --save-distance occupied
```

출력되는 `OCCUPIED_MAX_DISTANCE_CM` 권장값을 `esp32/micropython/main.py`에 반영한 뒤
업로드한다.

## 15~20분: 관리 컴퓨터와 서버

1. `computer/.env`에서 Vercel 주소, API 키, COM 포트를 확인한다.
2. `gateway.py`를 실행한다.
3. `장치 확인: esp32-bay-01`과 `판정=False` 로그를 확인한다.
4. 앱에서 A-01의 온도·습도·외부 온도가 갱신되는지 확인한다.

## 20~30분: 안전한 명령 시험

1. 펌프와 모터 대신 드라이버 출력 표시 LED로 먼저 시험한다.
2. `ACTUATORS_ENABLED = False` 상태에서 서버 명령과 빨간 LED/ACK 흐름을 확인한다.
3. 배선·릴레이 활성 레벨·별도 전원을 확인한 뒤에만 `True`로 바꾼다.
4. 실제 불을 만들지 말고 `simulate_without_esp32.py critical-fire --live --confirm-fire`로
   서버 화재 명령과 앱 알림을 시험한다.
5. 시험 후 `test_server.py reset`으로 활성 이벤트를 복구한다.

## 학교에서 기록할 값

- 실제 COM 포트:
- MLX90614 감지 여부/주소:
- 빈 공간 거리(cm):
- 차량 모형 거리(cm):
- 최종 점유 기준(cm):
- 릴레이 active-low/active-high:
- 차단막 작동 시간:
- 차단막 후 펌프 지연 시간:
