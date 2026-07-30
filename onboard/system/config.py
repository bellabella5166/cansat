# onboard/system/config.py

# ===== 실행 모드 =====
MOCK_MODE = False
COMM_MOCK = False  # 로컬 테스트: True / Pi4 실제 실행: False

# ===== 저장 경로 =====
import time
DATA_DIR = f"data/{time.strftime('%Y%m%d_%H%M%S')}"
IMAGE_SAVE_DIR = f"{DATA_DIR}/images"
QUALITY_SAVE_DIR = f"{DATA_DIR}/images_quality_pass"
SENSOR_SAVE_DIR = f"{DATA_DIR}/sensors"
LOG_SAVE_DIR = f"{DATA_DIR}/logs"

# ===== 카메라 설정 =====
CAMERA_RESOLUTION = (1920, 1080)  #굳이 최대 해상도로 안찍어도 됨.
CAMERA_FPS = 1  # 1fps

# ===== 이미지 전처리 설정 =====
PREPROCESS_SIZE = 640  # letterbox 리사이징 크기

# ===== 품질 판별 임계값 =====
LAPLACIAN_THRESHOLD = 30   # 블러 감지 임계값 (낮을수록 흐림)
EXPOSURE_LOW = 30             # 노출 부족 임계값 (0~255)
EXPOSURE_HIGH = 220           # 노출 과다 임계값 (0~255)

# ===== YOLO 설정 =====
MODEL_PATH = "models/yolov8n.onnx"
CONFIDENCE_THRESHOLD = 0.5    # 신뢰도 임계값

# ===== 통신 설정 =====
XBEE_PORT = "/dev/ttyUSB0"    # XBee 포트 (Pi4 기준)
XBEE_BAUDRATE = 9600          # XBee 보드레이트
MAX_RETRY = 5                 # 최대 재전송 횟수

# ===== 대표 이미지 설정 =====
REPRESENTATIVE_SIZE = (320, 240)  # 대표 이미지 축소 크기

# ===== 다중 고도 체크포인트 트리거 설정 =====
# 300m/150m 두 지점에서 각각 대표 이미지 1장씩 전송 (단일 실패 지점 리스크 제거).
# 간격 산정: 200m 이상 구간 이미지 전송 소요 23초 + 지연 5초 = 28초,
# 목표 하강속도 2.5m/s 기준 필요 간격 약 90~100m(여유 포함) → 150m 간격이면 충분한 마진.
# 반드시 고도 내림차순으로 나열해야 한다.
ALTITUDE_CHECKPOINTS = [300, 150]
ALTITUDE_DEBOUNCE_COUNT = 3   # 체크포인트 확정에 필요한 연속 샘플 수 (1fps 이미지 루프 기준 ≈3초, 노이즈 오탐 방지)

# ===== 체크포인트 시간 기반 백업 트리거 설정 =====
# baro/gps 다중화(AltitudeArbiter)마저 둘 다 SENSOR_FAILURE_TIMEOUT_S 이상 무응답이면
# "센서 실패"로 보고, 마지막 유효 고도/시각(anchor) 기준 목표 하강속도로 체크포인트
# 도달 예상 시각을 계산해 시간만으로 발동한다.
DESCENT_RATE_MPS = 2.9          # 목표 하강 속도 (m/s)
SENSOR_FAILURE_TIMEOUT_S = 5.0  # baro, gps 각각 이 시간 이상 무응답이면 실패로 판정

# ===== 고도 이중화 트리거 설정 (기압계 우선, 이상 시 GPS로 자동 전환) =====
BARO_SENTINEL = 9999.0        # 기압계 미보정 상태를 나타내는 sentinel 값
BARO_FREEZE_WINDOW = 10       # 정지(freeze) 판단 샘플 수 (10Hz 기준 1초)
BARO_FREEZE_EPS = 0.05        # 이 값(m) 이하 변화가 WINDOW 동안 지속되면 정지로 판단
BARO_MAX_JUMP = 50.0          # 연속 샘플 간 허용 최대 고도 변화(m), 초과 시 이상치

# config.py에 추가
GPS_PORT = "/dev/ttyS0"   # GPS 포트 (Pi4 기준)
GPS_BAUDRATE = 9600          # GPS 보드레이트

# ===== I2C 버스 공유(IMU/Baro) 소프트웨어 완화 설정 =====
# MPU6050(IMU)과 BMP388(Baro)가 같은 물리 I2C 버스(bus 1)를 공유해 가끔
# 읽기 실패가 발생 — 부품 고장이 아니라 버스 공유 구조상 특성(버스 락업,
# 접촉 불량, 클럭 스트레칭 충돌)으로 판단. 아래 값은 임의값이며 추후
# 실측(실패 빈도/지속시간) 기반으로 조정 예정.
I2C_RETRY_COUNT = 3         # 읽기 실패 시 재시도 횟수
I2C_RETRY_DELAY_S = 0.01    # 재시도 사이 delay (초)
I2C_LOCKUP_THRESHOLD = 10   # 연속 실패가 이 횟수 넘으면 버스 락업으로 판단, SCL 비트뱅잉 소프트 리셋 수행
# fallback 유지 시간은 고도 트리거 판정 기준과 동일하게 SENSOR_FAILURE_TIMEOUT_S를 재사용

# ===== 센서 전처리 설정 =====
SENSOR_LOWPASS_ALPHA = 0.2    # low-pass filter 계수 (0~1)
# ===== GPS 필터링 설정 =====
GPS_MAX_SPEED = 3.0   # Maximum GPS speed (m/s)
GPS_MAX_HDOP = 3.0    # Maximum HDOP threshold

# ===== XBee 전력 설정 =====
XBEE_VOLTAGE_V  = 3.6    # XBee 공급 전압 (V)
XBEE_CURRENT_MA = 55.6   # XBee 송신 전류 (mA) = 0.2W / 3.6V
POWER_REPORT_INTERVAL = 10.0  # POWER 패킷 송신 주기 (초)

# ===== 자세 제어 설정 =====
GIMBAL_ALPHA       = 0.96   # 상보필터 상수
GIMBAL_SLEW        = 8.0    # 최대 각속도 (deg/tick)
GIMBAL_LIM         = 20.0   # 서보 각도 제한 (deg)
GIMBAL_PIN_ROLL    = 18     # 롤 서보 GPIO 핀
GIMBAL_PIN_PITCH   = 13     # 피치 서보 GPIO 핀

GIMBAL_NEUTRAL_ROLL  = 1500  # 롤 서보 중립 펄스 (μs)
GIMBAL_NEUTRAL_PITCH = 1500  # 피치 서보 중립 펄스 (μs)

GIMBAL_DT           = 0.02   # 루프 주기 (초) = 50Hz
GIMBAL_BIAS_SAMPLES = 150    # 자이로 바이어스 측정 샘플 수 (GIMBAL_DT 기준 3초)