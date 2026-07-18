# EV 화재 격리 주차장 프로토타입 시험 안내서

이 ZIP에는 네 부분의 코드가 들어 있습니다.

| 구분 | 폴더 | 시작 파일 |
|---|---|---|
| 휴대전화 앱 | `app/` | `App.tsx` |
| 관리 컴퓨터 | `computer/` | `gateway.py` |
| Vercel 서버 | `server/` | `app/api/...` |
| ESP32 | `esp32/` | `src/main.cpp` |

> 이 장치는 교육·시연용 프로토타입입니다. 실제 배터리 화재를 만들지 마세요. 펌프와 모터를 ESP32 핀에 직접 연결하지 말고 릴레이/MOSFET 드라이버와 별도 전원을 사용하세요. 물, 고전류 장치, 실제 차량을 이용한 시험은 하지 않습니다.

## 0. 전체 흐름

```text
ESP32(센서/LED/차단막/펌프)
  <-> USB Serial
관리 컴퓨터(Python gateway.py)
  <-> HTTPS
서버(Next.js + PostgreSQL)
  <-> HTTPS / Expo Push
휴대전화 앱(Expo React Native)
```

다음 식별자는 서로 일치해야 합니다.

- ESP32 `DEVICE_ID`: `esp32-bay-01`
- ESP32 `PARKING_SPOT_ID`: `A-01`
- DB 주차 구역 ID: `A-01`
- 시험 사용자 ID: `11111111-1111-4111-8111-111111111111`

## 1. 서버 준비

### 필요한 프로그램

- Node.js LTS
- PostgreSQL 데이터베이스(Neon 또는 Supabase 사용 가능)

### DB와 환경변수

1. PostgreSQL SQL 편집기에서 `server/db/schema.sql`을 실행합니다.
2. `server/.env.example`을 복사해 `server/.env.local`을 만듭니다.
3. `DATABASE_URL`을 실제 PostgreSQL 주소로 바꿉니다.
4. `GATEWAY_API_KEY`에 길고 임의적인 값을 넣습니다.
5. 이 API 키는 관리 컴퓨터의 값과 반드시 같아야 합니다.

로컬 서버 실행:

```powershell
cd server
npm.cmd install
npm.cmd run dev
```

다른 PowerShell에서 확인:

```powershell
Invoke-RestMethod http://localhost:3000/api/health
```

`ok: true`가 나오면 정상입니다.

Vercel을 사용할 때는 프로젝트 환경변수에 다음을 등록하고 다시 배포합니다.

- `DATABASE_URL`
- `GATEWAY_API_KEY`
- `FIRE_CRITICAL_TEMP_C=70`
- `FIRE_HIGH_TEMP_C=55`
- `FIRE_RISE_C_PER_MIN=8`

배포 주소의 `/api/health`가 HTTP 200과 `ok: true`를 반환해야 다음 단계로 갑니다.

## 2. ESP32 준비

VS Code와 PlatformIO를 설치하고 `esp32/` 폴더를 연 뒤 Upload를 실행합니다. 라이브러리는 `platformio.ini`에 지정되어 자동 설치됩니다.

### 배선

| 부품 | ESP32 핀 | 비고 |
|---|---:|---|
| 내부 DHT22 DATA | GPIO 33 | DATA-VCC 사이 10kΩ 풀업 권장 |
| 외부 MLX90614 SDA | GPIO 2 | I2C, 부팅 불안정 시 GPIO21 권장 |
| 외부 MLX90614 SCL | GPIO 15 | I2C, 부팅 불안정 시 GPIO22 권장 |
| RGB 빨강 | GPIO 12 | 저항 사용 |
| RGB 초록 | GPIO 14 | 저항 사용 |
| RGB 파랑 | GPIO 13 | 저항 사용 |
| 초음파 TRIG | GPIO 27 | VCC를 GPIO에 연결하지 않음 |
| 초음파 ECHO | GPIO 25 | 5V ECHO 모델은 분압 필요 |
| 차단막 릴레이 제어 | GPIO 26 | 드라이버/별도 전원 필수 |
| 펌프 릴레이 제어 | GPIO 32 | 드라이버/별도 전원 필수 |

릴레이가 active-high라면 `main.cpp`의 `RELAY_ON/RELAY_OFF` 값을 반대로 바꿉니다. RGB 모듈이 공통 양극이면 `RGB_ACTIVE_HIGH=false`로 바꿉니다.

LED 의미:

- 초록: 차량 없음
- 노랑: 차량 주차
- 주황: 현장 경고
- 빨강: 서버가 화재 대응 명령을 보냄
- 파랑: 센서 오류

## 3. 관리 컴퓨터 준비

Python 3.11 이상을 설치합니다. ESP32를 USB로 연결하고 장치 관리자에서 COM 포트를 확인합니다.

```powershell
cd computer
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`computer/.env`를 수정합니다.

```env
SERVER_URL=http://localhost:3000
GATEWAY_API_KEY=서버와_동일한_키
SERIAL_BAUD=115200
SERIAL_PORTS=COM3
```

Vercel을 사용하면 `SERVER_URL`을 실제 공개 배포 주소로 바꿉니다. `COM3`도 실제 ESP32 포트로 바꿉니다.

실행:

```powershell
.\.venv\Scripts\python.exe gateway.py
```

정상이면 로그에 `장치 확인: esp32-bay-01`과 주기적인 온도가 표시됩니다.

## 4. 안전한 단계별 시험

### ESP32 없이 소프트웨어만 시험

다음 명령은 기본적으로 네트워크 요청도 보내지 않는 dry-run이다.

```powershell
cd computer
.\.venv\Scripts\python.exe -m unittest -v test_gateway.py
.\.venv\Scripts\python.exe simulate_without_esp32.py normal
.\.venv\Scripts\python.exe simulate_without_esp32.py warning
.\.venv\Scripts\python.exe simulate_without_esp32.py delta-fire
```

실제 서버에 정상값을 보낼 때만 `--live`를 붙인다. 화재 모의값은 실제 DB 이벤트와
앱 알림을 만들 수 있으므로 대상 서버를 확인한 후 `--live --confirm-fire`를 함께 붙인다.

### A. ESP32 출력만 시험

펌프 대신 작은 LED 또는 릴레이 표시등을 연결한 상태에서 시험합니다. Gateway가 실행 중이면 먼저 종료하여 시리얼 포트를 비웁니다.

PlatformIO Serial Monitor를 115200 baud, newline 전송으로 열고 다음 한 줄을 보냅니다.

```json
{"type":"command","commandId":"manual-fire-1","action":"ACTIVATE_FIRE_RESPONSE"}
```

예상 결과:

1. RGB LED가 빨강으로 바뀝니다.
2. 차단막 릴레이가 즉시 켜집니다.
3. 5초 뒤 펌프 릴레이가 켜집니다.
4. `commandAck` JSON이 출력됩니다.

복구 명령:

```json
{"type":"command","commandId":"manual-reset-1","action":"RESET_FIRE_RESPONSE"}
```

### B. 서버 정상 데이터 시험

서버와 Gateway, ESP32를 모두 실행한 상태에서 별도 PowerShell을 열어 실행합니다.

```powershell
cd computer
.\.venv\Scripts\python.exe test_server.py normal
```

예상 결과는 HTTP 200과 `fire: false`입니다.

### C. 전체 화재 흐름 시험

실제 센서를 가열하지 않고 다음 모의 명령을 실행합니다.

```powershell
.\.venv\Scripts\python.exe test_server.py fire
```

이 스크립트는 서버에 75°C를 전송합니다. 예상 흐름:

1. 서버가 화재 이벤트와 `ACTIVATE_FIRE_RESPONSE` 명령을 생성합니다.
2. Gateway가 명령을 조회해 ESP32로 전달합니다.
3. ESP32가 차단막 릴레이를 켭니다.
4. 5초 뒤 펌프 릴레이를 켭니다.
5. RGB LED가 빨강으로 바뀝니다.
6. Gateway가 명령 실행 ACK를 서버로 보냅니다.

복구:

```powershell
.\.venv\Scripts\python.exe test_server.py reset
```

현장이 안전하다고 확인한 뒤에만 reset을 실행합니다.

## 5. 앱 시험

`app/.env.example`을 복사해 `app/.env`를 만들고 값을 수정합니다.

```env
EXPO_PUBLIC_SERVER_URL=http://컴퓨터의_LAN_IP:3000
EXPO_PUBLIC_USER_ID=11111111-1111-4111-8111-111111111111
```

휴대전화와 로컬 서버 컴퓨터가 같은 네트워크여야 합니다. Vercel을 사용하면 공개 HTTPS 주소를 사용합니다.

```powershell
cd app
npm.cmd install
npx.cmd expo start
```

설치형 APK 빌드:

```powershell
$env:EAS_NO_VCS="1"
npx.cmd eas-cli@latest build --platform android --profile preview --clear-cache
```

앱에서 알림 권한을 허용합니다. 앱 환경변수의 사용자 ID와 DB 사용자가 같아야 대시보드와 알림이 연결됩니다.

## 6. 실패 판정과 점검 순서

1. `/api/health`가 실패하면 DB와 서버 환경변수부터 고칩니다.
2. Gateway에 장치 로그가 없으면 USB 케이블, 드라이버, COM 포트, 115200 baud를 확인합니다.
3. 서버가 401을 반환하면 양쪽 `GATEWAY_API_KEY`가 다른 것입니다.
4. 서버가 404 `unknown_parking_spot`을 반환하면 `schema.sql`과 `A-01` 등록을 확인합니다.
5. 화재 명령은 오지만 릴레이가 움직이지 않으면 active-low/high 설정과 별도 전원을 확인합니다.
6. 앱 화면은 나오지만 알림이 없으면 사용자 ID, 푸시 토큰 등록, Android 알림 권한을 확인합니다.
