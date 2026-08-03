```markdown
# CANSAT - Canvas Team Onboard Software

## 프로젝트 개요
2026 캔위성 체험·경연대회 창작부 **캔버스 팀** 온보드 SW.

- **임무**: 온보드 AI 토지피복분류(농경지/건물) + 선별적 데이터 송신
- **하드웨어**: Raspberry Pi 4, Pi Camera V2, BNO055, BMP388, u-blox NEO-M8N, XBee3

---

## 폴더 구조

```
CANSAT/
├── shared/                          # 온보드·지상국 공용 모듈
│   ├── protocol.py                  # 패킷 구조, CRC-16, PacketParser
│   ├── telemetry.py                 # SensorData, YoloDetection 직렬화
│   ├── image_chunker.py             # 이미지 청크 분할/재조립
│   └── serial_wrapper.py            # XBee 시리얼 래퍼
├── onboard/
│   ├── config.py                    # 전체 설정값 중앙화
│   ├── input/
│   │   ├── camera.py                # 카메라 캡처
│   │   ├── sensor.py                # GPS/IMU/Barometer 수집
│   │   ├── timestamp_manager.py     # 타임스탬프 생성
│   │   └── id_manager.py            # 이미지/센서 ID 관리
│   ├── preprocess/
│   │   ├── image_validator.py       # 손상 이미지 필터링
│   │   ├── image_quality.py         #블러/노출/자세각/IMU calib 품질 판별
│   │   ├── image_preprocess.py      # 640×640 letterbox 전처리
│   │   ├── sensor_preprocess.py     # 센서 이상치 제거, low-pass filter
│   │   └── sensor_logger.py         # 전처리 센서 CSV 저장
│   ├── detection/
│   │   ├── detector.py              # YOLOv8n ONNX 탐지
│   │   ├── detection_logger.py      # 탐지 결과 CSV + bbox 이미지 저장
│   │   ├── metadata_builder.py      # 탐지 메타데이터 생성
│   │   └── representative_selector.py # 대표 이미지 선별
│   └── system/
│       ├── main.py                  # 전체 실행 제어
│       └── logger.py                # 시스템 로그
├── models/
│   └── yolov8n.onnx                 # INT8 양자화 모델
├── data/
│   ├── images/                      # 캡처 이미지 저장
│   ├── sensors/                     # 센서 CSV 저장
│   └── logs/                        # 시스템 로그
├── test/
│   ├── test_timestamp_manager.py
│   ├── test_id_manager.py
│   ├── test_camera.py
│   ├── test_sensor.py
│   ├── test_image_validator.py
│   ├── test_image_quality.py
│   ├── test_image_preprocess.py
│   ├── test_sensor_preprocess.py
│   ├── test_sensor_logger.py
│   ├── test_detector.py
│   ├── test_detection_logger.py
│   ├── test_metadata_builder.py
│   └── test_representative_selector.py
└── requirements.txt
```

---

## 설치

```bash
pip install -r requirements.txt
```

Pi4에서:
```bash
pip install -r requirements.txt --break-system-packages
```

---

## 실행

### 로컬 테스트 (Mock 모드)
```bash
# config.py에서 MOCK_MODE = True 확인
python onboard/system/main.py
```

### Pi4 실제 실행
```bash
# config.py에서 MOCK_MODE = False로 변경
python onboard/system/main.py
```

---

## 데이터 흐름

```
[이미지]
camera.py → image_validator.py → image_quality.py → image_preprocess.py
→ detector.py → detection_logger.py → representative_selector.py
→ 고도 150m 도달 시 대표 이미지 선별 → image_chunker.py → XBee 송신

[센서]
sensor.py → sensor_preprocess.py → sensor_logger.py → XBee 송신
```

---

## 패킷 구조

```
HEADER(2) | TYPE(1) | SEQ(2) | LENGTH(2) | PAYLOAD(n) | CRC16(2)
고정 오버헤드: 9 bytes, little-endian
```

| 타입 | 값 | 설명 |
|---|---|---|
| SENSOR | 0x01 | GPS/IMU/기압계 (10Hz) |
| YOLO_META | 0x02 | 탐지 메타데이터 |
| IMG | 0x03 | 이미지 청크 |
| HEARTBEAT | 0x20 | 생존 신호 (5초) |
| NACK | 0x11 | 청크 재전송 요청 |

---

## Pi4 이식 시 수정사항

1. `onboard/system/config.py`에서 `MOCK_MODE = False`
2. **`/boot/firmware/config.txt`에 UART 오버레이 추가** (SD카드를 새로 구우면 이 설정이
   기본값으로 초기화되면서 사라진다 — `/dev/ttyS0` 등이 없다는 `FileNotFoundError`가
   나면 이게 원인이니 제일 먼저 확인할 것):
   ```
   dtoverlay=uart2
   dtoverlay=disable-bt
   ```
   추가 후:
   ```bash
   sudo systemctl disable hciuart
   sudo reboot
   ```
   (`disable-bt`로 블루투스가 GPIO14/15를 안 쓰게 해야 `/dev/serial0`가 항상
   같은 UART를 안정적으로 가리킨다. 이거 없이 `/dev/serial0`만 쓰면 블루투스
   활성화 여부에 따라 실제 가리키는 장치가 바뀔 수 있다.)
3. 재부팅 후 실제 장치 확인 및 `onboard/system/config.py` 포트 검증:
   ```bash
   ls -l /dev/ttyAMA* /dev/serial* /dev/ttyS0 2>/dev/null
   stty -F /dev/ttyAMA1 9600   # 에러 안 나는 쪽이 XBee 포트
   stty -F /dev/ttyAMA2 9600
   ```
   - `GPS_PORT = "/dev/serial0"` (기본 UART, GPIO14/15, 8/10번 핀)
   - `XBEE_PORT`는 `dtoverlay=uart2`(GPIO0/1, 27/28번 핀)가 실제로 어느
     `/dev/ttyAMAx`로 잡히는지 위 `stty` 검증 결과에 맞춰 설정 — 지금
     코드엔 `/dev/ttyAMA2`로 넣어뒀지만 **미검증 상태**이니 재부팅 후 꼭 확인할 것
4. `models/yolov8n.onnx` 추가
5. SD카드 마운트 경로로 IMAGE_SAVE_DIR, SENSOR_SAVE_DIR, LOG_SAVE_DIR 수정
6. BNO055 gyro 단위 확인 (rad/s vs °/s)
7. LAPLACIAN_THRESHOLD 실제 이미지로 조정
8. systemd 부팅 자동 실행 등록

### config.py 편집 시 주의사항

- `nano`로 열 때 현재 위치가 저장소 루트(`~/canverse` 등)가 아니면, 상대경로로 열고
  저장(Ctrl+O)할 때 `Error writing ...: No such file or directory`와 함께 파일
  내용이 거의 다 날아갈 수 있다. 항상 저장소 루트에서 `nano onboard/system/config.py`로 열 것.
- 포트 값처럼 한 줄짜리 수정은 `nano`보다 `sed`가 안전하다:
  ```bash
  sed -i 's|^GPS_PORT = .*|GPS_PORT = "/dev/serial0"|' onboard/system/config.py
  grep -E "GPS_PORT|XBEE_PORT|MOCK_MODE" onboard/system/config.py  # 무결성 확인
  ```
- 파일이 손상됐다면 git으로 즉시 복구 가능:
  ```bash
  git checkout -- onboard/system/config.py
  ```

---

## 테스트

```bash
# 개별 모듈 테스트
python test/test_camera.py
python test/test_sensor.py
# ... 등

# 전체 파이프라인 테스트
python onboard/system/main.py
```
```
