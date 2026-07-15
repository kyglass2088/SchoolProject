# 현재 ESP32 배선표

전원을 끈 상태에서 배선한다. 모든 GND 단자는 ESP32 내부에서 연결되어 있으므로
서로 다른 GND 핀 또는 같은 브레드보드 GND 레일을 사용해도 된다.

| 부품 | 부품 단자 | ESP32 단자 |
|---|---|---|
| RGB LED | R | D12 / GPIO12 |
| RGB LED | B | D13 / GPIO13 |
| RGB LED | G | D14 / GPIO14 |
| RGB LED | - | GND |
| DHT22 | + | 3V3 |
| DHT22 | OUT | D33 / GPIO33 |
| DHT22 | - | GND |
| MLX90614 | VIN | 3V3 |
| MLX90614 | GND | GND |
| MLX90614 | SCL | D15 / GPIO15 |
| MLX90614 | SDA | D2 / GPIO2 |
| 초음파 센서 | TRIG | D27 / GPIO27 |
| 초음파 센서 | ECHO | D25 / GPIO25 |
| 초음파 센서 | GND | GND |
| 초음파 센서 | VCC | 센서 정격에 맞는 5V/VIN 또는 3V3 |

초음파 센서 VCC는 GPIO26에 연결하지 않는다. GPIO는 센서 전원 공급 단자가 아니다.
표준 HC-SR04의 5V ECHO는 분압이 필요하고, 3.3V ECHO 호환 모델만 GPIO25에
직접 연결할 수 있다.

GPIO27을 초음파 TRIG로 사용하므로 향후 워터 펌프 드라이버 제어핀은 GPIO32로
변경했다. 차단막 드라이버 제어핀은 GPIO26이다. 모터와 펌프는 GPIO에 직접
연결하지 않는다.

GPIO2와 GPIO15는 ESP32 부팅 설정에도 사용되는 핀이다. MLX90614 모듈의 I2C
풀업 때문에 부팅이 불안정하면 SDA/SCL을 GPIO21/GPIO22로 옮기는 것이 권장된다.
