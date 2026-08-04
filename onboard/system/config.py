# onboard/system/config.py

# ===== 실행 모드 =====
MOCK_MODE = False
COMM_MOCK = False  # 로컬 테스트: True / Pi4 실제 실행: False
GIMBAL_MOCK = False   # True면 서보(GPIO/lgpio) 제어를 건너뛰고 로그만 출력. IMU 읽기는 이 값과 무관하게 항상 실제 센서에서 함

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
IMAGE_SEND_INTERVAL_S = 90

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
GIMBAL_SLEW        = 5.0    # 최대 각속도 (deg/tick) — 데드밴드 밖에서는 이 속도로 확 움직임

# BNO055 fused roll/pitch에 거는 저역통과(EMA) 필터 계수. 데드밴드는
# "언제 멈출지"만 다루는 반면, 이건 target 자체가 센서 노이즈로 흔들리는 걸
# 애초에 줄인다 — 값이 클수록(1에 가까울수록) 더 부드럽지만 반응이 느려짐.
# filtered = ALPHA * filtered_prev + (1-ALPHA) * raw
GIMBAL_FILTER_ALPHA = 0.8

# 재조준 판단 주기(초). IMU 읽기/필터링/서보 신호(PWM) 유지는 계속 50Hz로
# 돌지만, "새 목표로 움직일지" 판단은 이 주기로만 한다 — CAMERA_FPS=1이라
# 카메라가 초당 1장만 찍으므로, 그보다 빠르게 재조준해봐야 그 사이엔 찍히는
# 프레임이 없어 의미가 없다. MG90 같은 저가 서보를 "계속 미세 추적"이 아니라
# "필요할 때만 굵직하게 재조준"하는 용도로 쓰기 위한 조치.
GIMBAL_REPOSITION_INTERVAL_S = 1.0

# 서보 각도 제한 (deg, 중립 기준) — roll+pitch 2축을 동시에 구동한 상태로 실측.
# 각 축을 독립적으로 최대까지 밀면(roll +50.5, pitch +45) 조합에서 구조체에 부딪혀
# 안전하지 않음이 확인됨 — 대신 두 축을 동시에 극단으로 밀어도 안전하다고 검증된
# 조합(roll +45.0 / pitch +16.5)을 각 축의 독립 리밋으로 보수적으로 사용한다.
# 즉 roll이 neutral 근처일 때 pitch가 실제로는 +45까지 더 갈 여지가 있지만,
# 두 축을 함께 구동하는 이 짐벌 구조상 그 여유를 조합 리밋으로 깎아서 안전 마진을 둠.
# 음수 방향 조합은 아직 전부 검증되지 않았으니 롤/피치 값을 더 조합해서 재검증 필요.
GIMBAL_ROLL_LIM_POS  = 45.0   # 롤 + 리밋 (조합 검증됨)
GIMBAL_ROLL_LIM_NEG  = 29.0   # 롤 - 리밋 (기계적 한계 아님 — 이 이상 기울면 카메라가 지면 대신 구조체를 찍음)
GIMBAL_PITCH_LIM_POS = 16.5   # 피치 + 리밋 (roll +45와 동시 구동 시 검증됨 — 단독 최대인 +45는 조합 시 충돌)
GIMBAL_PITCH_LIM_NEG = 10.0   # 피치 - 리밋

GIMBAL_PIN_ROLL    = 18     # 롤 서보 GPIO 핀
GIMBAL_PIN_PITCH   = 13     # 피치 서보 GPIO 핀

# 축별 데드밴드 (deg) — 이 이하 오차는 무시하고 아예 멈춰서, "확확 바뀌었다가
# 딱 정지"를 의도대로 만든다. pitch는 가동범위(26.5도)가 roll(74도)보다 훨씬
# 좁아서 같은 5도를 그대로 쓰면 범위의 20%가 죽어버리므로 축별로 분리.
GIMBAL_ROLL_DEADBAND  = 5.0
GIMBAL_PITCH_DEADBAND = 2.5

GIMBAL_NEUTRAL_ROLL  = 1545  # 롤 서보 중립 펄스 (μs)
GIMBAL_NEUTRAL_PITCH = 1370  # 피치 서보 중립 펄스 (μs)

GIMBAL_DT           = 0.02   # 루프 주기 (초) = 50Hz