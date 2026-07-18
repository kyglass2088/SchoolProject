# 시스템 동작 요약

## 정상 측정

```text
1. ESP32가 2초마다 온도·습도 측정
2. USB Serial 한 줄 JSON으로 컴퓨터에 전송
3. Gateway가 deviceId별 데이터를 Vercel API에 HTTPS POST
4. 서버가 원본 데이터와 장치의 최근 상태를 PostgreSQL에 저장
5. 앱이 3초마다 소유 차량 구역의 최신 상태를 조회
```

## 화재 판정과 제어

```text
ESP32 → Gateway → POST /api/telemetry
                     │
                     ├─ 이전 측정값 조회
                     ├─ 임계 온도/상승률 판정
                     ├─ 활성 fire_event 생성 (구역당 1개)
                     ├─ 소유자와 Expo push token 조회 → 앱 긴급 알림
                     └─ ACTIVATE_FIRE_RESPONSE 명령 생성
                                  ↓
ESP32 ← USB Serial ← Gateway 명령 조회/응답
  │
  ├─ 차단막 릴레이 즉시 ON
  ├─ 5초 후 펌프 릴레이 ON
  └─ commandAck → Gateway → 서버 명령 상태 executed
```

## 여러 ESP32로 확장

각 ESP32는 서로 다른 `DEVICE_ID`와 `PARKING_SPOT_ID`를 사용합니다. 컴퓨터 Gateway는 연결된 시리얼 포트를 주기적으로 탐색하고 포트별 작업 스레드를 실행합니다. 서버 테이블과 API 모두 장치/주차면 ID를 키로 사용하므로 기본 구조를 바꾸지 않고 구역을 추가할 수 있습니다.

운영 단계에서는 다음 항목을 추가해야 합니다.

- USB 허브/RS-485/CAN 등 현장 거리와 노이즈에 맞는 유선 통신 및 장치 인증
- Gateway의 디스크 기반 오프라인 큐와 이중화
- 앱 사용자 인증, 운영자 권한, API rate limit, 감사 로그
- 독립적인 하드웨어 비상 정지와 통신 단절 시 안전 동작
- 다중 센서 교차 검증 및 인증된 소방 설비 연동

