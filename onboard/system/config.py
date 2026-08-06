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

# ===== 시간 기반 대표 이미지 트리거 설정 =====
# 전원 인가(프로그램 시작) 시점부터 IMAGE_SEND_INTERVAL_S 간격으로 무한 반복해서
# 대표 이미지 1장씩 전송한다. 고도값을 신뢰하기 어려워 고도 체크포인트 대신
# 순수 시간 기반으로 전환.
IMAGE_SEND_INTERVAL_S = 60

# ===== 대표 이미지 전송/재전송 설정 =====
# 대표 이미지 한 장을 다 보내는 데(NACK 재전송 포함) 온보드가 스스로 기다리는
# 최대 시간. 지상국이 NACK을 그만 보내야(5회 요청/15초 무응답 등) 온보드도
# 따라서 멈추는 구조면, 지상국↔온보드 중 한쪽 방향 통신만 막혀도 온보드가
# 무한정 대기하며 SENSOR/YOLO_META를 0.5Hz에 계속 묶어두게 된다 — 그걸 막기
# 위한 온보드 자체 상한. 지상국의 절대 포기 시점(300초)보다는 짧게 잡아서,
# 지상국이 포기하기 전에 온보드가 먼저 자기 몫을 정리하고 다음 이미지로 넘어간다.
IMAGE_SEND_TIMEOUT_S = 60

# NACK 재전송에 응답하기 위해 온보드가 최근 전송한 이미지의 청크를 RAM에
# 보관하는 범위. 지상국도 이미지당 재요청 5회・무응답 300초가 지나면 포기하므로,
# 그 이상 오래/많이 들고 있을 이유가 없다.
CHUNK_CACHE_MAX_IMAGES = 5
CHUNK_CACHE_TTL_S = 300.0

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
# IMUPLUS 모드(자이로+가속도 융합만 사용, 지자기 융합 끔) — 서보 근처 자성 간섭이
# NDOF 모드의 지자기 융합을 흔들어 짐벌 진동으로 이어지는 문제를 근본적으로 제거.
# 같은 BNO055 인스턴스를 sensor_thread(텔레메트리 roll/pitch/yaw)와 공유하므로,
# 이 모드 전환은 텔레메트리의 yaw(heading)에도 적용돼 지자기 기준 대신 자이로
# 적분값이 되어 시간이 지나면 서서히 드리프트한다 (합의된 트레이드오프).
GIMBAL_USE_IMU_MODE = True

GIMBAL_SLEW        = 2.0    # 최대 각속도 (deg/tick) — 진동 억제를 위해 8.0에서 하향

# 서보 각도 제한 (deg, 중립 기준). 원래는 실측된 축별 비대칭 리밋(roll -10/+16.5,
# pitch -29/+45, 구 dev-time2 GIMBAL_ROLL/PITCH_LIM_*)을 썼는데, 그 좁아진
# 리밋(특히 롤 40°->26.5°) 근처에서 클램프에 계속 부딪히며 지지직거리는 진동이
# 재발해 — 원인 확인을 위해 gimbal_test.py와 동일한 대칭 ±20도로 임시 원복.
# 진동이 사라지면 리밋 폭 자체가 원인으로 확정되고, 구조체 충돌 안전은 소프트웨어
# 리밋이 아닌 다른 방식(기구적 스톱 등)으로 별도 해결 필요.
GIMBAL_ROLL_LIM_POS  = 20.0   # 롤 + 리밋
GIMBAL_ROLL_LIM_NEG  = 20.0   # 롤 - 리밋
GIMBAL_PITCH_LIM_POS = 20.0   # 피치 + 리밋
GIMBAL_PITCH_LIM_NEG = 20.0   # 피치 - 리밋

GIMBAL_DEADBAND_DEG = 1.0   # 이 각도(deg) 미만 오차는 무시 (자잘한 흔들림 억제)
GIMBAL_ANGLE_SMOOTH_ALPHA = 0.85  # roll/pitch EMA 스무딩 계수 (0~1, 클수록 더 부드럽고 느림)
GIMBAL_US_PER_DEG  = 10.0   # 각도(deg) -> 서보 펄스(μs) 변환 계수

GIMBAL_PIN_ROLL    = 13     # 롤 서보 GPIO 핀
GIMBAL_PIN_PITCH   = 18     # 피치 서보 GPIO 핀

GIMBAL_NEUTRAL_ROLL  = 1545  # 롤 서보 중립 펄스 (μs)
GIMBAL_NEUTRAL_PITCH = 1370  # 피치 서보 중립 펄스 (μs)

GIMBAL_DT           = 0.02   # 루프 주기 (초) = 50Hz