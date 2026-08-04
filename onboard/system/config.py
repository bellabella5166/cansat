# onboard/system/config.py

# ===== 실행 모드 =====
MOCK_MODE = False
COMM_MOCK = False  # 로컬 테스트: True / Pi4 실제 실행: False
GIMBAL_MOCK = True   # True면 서보(GPIO/lgpio) 제어를 건너뛰고 로그만 출력. IMU 읽기는 이 값과 무관하게 항상 실제 센서에서 함

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
CONFIDENCE_THRESHOLD = 0.5    # 신뢰도 임계값 — 이 이상은 전부 저장/전송(실격 방지, 데이터 손실 없음)
BBOX_DRAW_THRESHOLD = 0.8     # 시각화 이미지에 bbox를 "그리는" 최소 신뢰도 — 바닥 등 오탐 표시만 줄임, 데이터 자체는 그대로 저장

# ===== 통신 설정 =====
XBEE_PORT = "/dev/ttyAMA2"    # XBee 포트 (Pi4 기준, dtoverlay=uart2 → GPIO0/1(27/28번 핀)) — 재부팅 후 stty로 실제 값 검증 필요
XBEE_BAUDRATE = 9600          # XBee 보드레이트
MAX_RETRY = 5                 # 최대 재전송 횟수

# ===== 대표 이미지 설정 =====
REPRESENTATIVE_SIZE = (320, 240)  # 대표 이미지 축소 크기

# ===== 시간 기반 대표 이미지 트리거 설정 =====
# 전원 인가(프로그램 시작) 시점부터 IMAGE_SEND_INTERVAL_S 간격으로 무한 반복해서
# 대표 이미지 1장씩 전송한다. 고도값을 신뢰하기 어려워 고도 체크포인트 대신
# 순수 시간 기반으로 전환.
IMAGE_SEND_INTERVAL_S = 60

# ===== 고도 이중화 트리거 설정 (기압계 우선, 이상 시 GPS로 자동 전환) =====
BARO_SENTINEL = 9999.0        # 기압계 미보정 상태를 나타내는 sentinel 값
BARO_FREEZE_WINDOW = 10       # 정지(freeze) 판단 샘플 수 (10Hz 기준 1초)
BARO_FREEZE_EPS = 0.05        # 이 값(m) 이하 변화가 WINDOW 동안 지속되면 정지로 판단
BARO_MAX_JUMP = 50.0          # 연속 샘플 간 허용 최대 고도 변화(m), 초과 시 이상치

# GPS 포트 (Pi4 기준). /dev/serial0는 블루투스 활성화 여부에 따라 가리키는
# 대상이 바뀌는 심볼릭 링크라, /boot/firmware/config.txt에 dtoverlay=disable-bt
# + sudo systemctl disable hciuart 가 반드시 같이 적용돼 있어야 한다
# (README "Pi4 이식 시 수정사항" 참고).
GPS_PORT = "/dev/serial0"    # 기본 UART (GPIO14/15)
GPS_BAUDRATE = 9600          # GPS 보드레이트

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