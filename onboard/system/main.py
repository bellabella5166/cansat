# onboard/system/main.py

from __future__ import annotations

import time
import logging
import os
import queue
import signal
import sys
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# ── 경로 설정 ──────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent.parent
SHARED_DIR = BASE_DIR / "shared"
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(BASE_DIR))

# ── shared 모듈 ────────────────────────────────────────────────────────────────
from protocol      import Packet, PacketType, encode_packet
from serial_wrapper import XBeeSerial
from telemetry     import SensorData, YoloDetection, decode_nack, CommPowerData

# ── onboard 모듈 ───────────────────────────────────────────────────────────────
from onboard.input.camera                      import Camera
from onboard.input.sensor                      import Sensor
from onboard.input.id_manager                  import IDManager
from onboard.preprocess.image_validator        import ImageValidator
from onboard.preprocess.image_quality          import ImageQuality
from onboard.preprocess.image_preprocess       import ImagePreprocess
from onboard.preprocess.sensor_preprocess      import SensorPreprocess
from onboard.preprocess.sensor_logger          import SensorLogger
from onboard.detection.detector                import Detector
from onboard.detection.detection_logger        import DetectionLogger
from onboard.detection.representative_selector import RepresentativeSelector
from onboard.detection.time_trigger            import TimeTrigger
from onboard.detection.chunk_cache             import ChunkCache
from onboard.system.threads.sensor_thread      import sensor_loop
from onboard.system.threads.image_thread       import image_loop
from onboard.system.threads.chunk_thread       import image_chunk_loop
from onboard.system.threads.heartbeat_thread   import heartbeat_loop
from onboard.system.threads.nack_thread        import nack_loop
from onboard.system.threads.gimbal_thread      import gimbal_loop

# ── 설정 ──────────────────────────────────────────────────────────────────────
from onboard.system.config import (
    MOCK_MODE, COMM_MOCK,
    IMAGE_SAVE_DIR, SENSOR_SAVE_DIR, LOG_SAVE_DIR,
    XBEE_PORT, XBEE_BAUDRATE, QUALITY_SAVE_DIR,
    CAMERA_FPS,
    IMAGE_SEND_INTERVAL_S, IMAGE_SEND_TIMEOUT_S,
    CHUNK_CACHE_MAX_IMAGES, CHUNK_CACHE_TTL_S,
    XBEE_VOLTAGE_V, XBEE_CURRENT_MA, POWER_REPORT_INTERVAL,
    GIMBAL_USE_IMU_MODE,
)

# ── 로깅 ──────────────────────────────────────────────────────────────────────
os.makedirs(LOG_SAVE_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            Path(LOG_SAVE_DIR) / "onboard.log", encoding="utf-8"
        ),
    ]
)
logger = logging.getLogger("onboard")

# ── 우선순위 (낮은 숫자 = 높은 우선순위) ──────────────────────────────────────
_PRIORITY = {
    PacketType.HEARTBEAT: 0,
    PacketType.ACK:       0,
    PacketType.NACK:      1,
    PacketType.SENSOR:    2,
    PacketType.YOLO_META: 3,
    PacketType.IMG:       4,
    PacketType.POWER:     2,
}
# NACK으로 재요청된 청크는 신규 이미지 청크(IMG=4)보다 먼저 나가게 한다 —
# 이미 절반쯤 도착한 이미지를 완성시키는 게, 새 이미지를 처음부터 또 보내는
# 것보다 대역폭 대비 효율이 좋다. YOLO_META(3)과 동률이라 SENSOR/POWER(2)
# 같은 하우스키핑 트래픽은 여전히 항상 먼저 나간다.
IMG_RETRANSMIT_PRIORITY = 3

# ── 큐 최대 크기 ──────────────────────────────────────────────────────────────
SENSOR_Q_MAX = 20
YOLO_Q_MAX   = 50
IMG_Q_MAX    = 200
HB_INTERVAL  = 5.0

# ── TX 큐 아이템 ──────────────────────────────────────────────────────────────
@dataclass(order=True)
class TxItem:
    priority: int
    ptype: PacketType = field(compare=False)
    raw: bytes = field(compare=False)
    # 이 아이템이 tx_q에서 빠져나갈 때(전송 성공 여부와 무관하게) 호출되는 콜백.
    # chunk_thread가 "내가 보낸 이미지 자신의 청크가 다 빠졌는지"를 전역
    # _type_counts(다른 이미지의 재전송 청크까지 섞여 있음)가 아니라 이미지별로
    # 독립적으로 추적하기 위해 사용한다.
    on_dequeue: object = field(default=None, compare=False)


# ── 시퀀스 카운터 (thread-safe) ───────────────────────────────────────────────
class SeqCounter:
    def __init__(self):
        self._v, self._lock = 0, threading.Lock()

    def next(self) -> int:
        with self._lock:
            self._v = (self._v + 1) & 0xFFFF
            return self._v


# ── 타입별 tx_q 대기 개수 (qsize()는 전체 큐 크기라 타입별 가득참 판단에 못 씀) ──
_type_counts = defaultdict(int)
_type_counts_lock = threading.Lock()


# ── 큐 enqueue 헬퍼 ───────────────────────────────────────────────────────────
def enqueue(q: queue.PriorityQueue, ptype: PacketType,
            payload: bytes, seq: SeqCounter, max_size: int,
            priority: int | None = None, on_dequeue=None) -> bool:
    """성공하면 True, 큐가 가득 찼거나 인코딩에 실패해 등록 못 하면 False를 반환한다.

    호출부(chunk_thread/nack_thread)가 이 반환값 없이는 "몇 개나 실제로 큐에
    들어갔는지"를 알 수 없어, 등록 실패한 청크까지 "보냈다"고 잘못 기록하거나
    (chunk_thread의 경우) on_dequeue가 영영 안 불려서 완료 판정이 불필요하게
    타임아웃까지 미뤄질 수 있다.
    """
    with _type_counts_lock:
        if _type_counts[ptype] >= max_size:
            logger.warning("Queue full (%s, %d/%d), packet dropped",
                            ptype.name, _type_counts[ptype], max_size)
            return False
        _type_counts[ptype] += 1
    try:
        raw = encode_packet(Packet(ptype=ptype, seq=seq.next(), payload=payload))
        p = priority if priority is not None else _PRIORITY.get(ptype, 99)
        q.put_nowait(TxItem(p, ptype, raw, on_dequeue))
        return True
    except queue.Full:
        with _type_counts_lock:
            _type_counts[ptype] -= 1
        logger.warning("TX queue full: %s dropped", ptype.name)
        return False
    except Exception as e:
        # encode_packet()이 실패하는 경우까지 포함 — 여기서 카운터를 안 내리면
        # _type_counts가 실제보다 영원히 높게 남아서 큐가 가득 찬 것처럼 보이는
        # 상태가 영구화될 수 있다.
        with _type_counts_lock:
            _type_counts[ptype] -= 1
        logger.error("Encode/enqueue error (%s): %s", ptype.name, e)
        return False

# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    running = [True]

    def _stop(sig, frame):
        running[0] = False
        logger.info("Stop signal received")

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    os.makedirs(IMAGE_SAVE_DIR,  exist_ok=True)
    os.makedirs(QUALITY_SAVE_DIR, exist_ok=True)
    os.makedirs(SENSOR_SAVE_DIR, exist_ok=True)
    os.makedirs(LOG_SAVE_DIR,    exist_ok=True)

    # calibrate_ground_altitude()가 별도 스레드에서 self.baro를 직접 읽는 동안
    # sensor_thread도 동시에 같은 I2C 버스를 읽지 않도록 공유 Lock 사용.
    i2c_lock = threading.Lock()

    # 모듈 초기화
    id_mgr       = IDManager()
    camera       = Camera(mock=MOCK_MODE)
    sensor       = Sensor(mock=MOCK_MODE, i2c_lock=i2c_lock)

    # IMUPLUS 모드(자이로+가속도 융합만 사용, 지자기 융합 끔) — 서보 근처 자성
    # 간섭이 NDOF 모드의 지자기 융합을 흔들어 짐벌 진동으로 이어지던 문제의
    # 근본 원인이었다. sensor_thread/gimbal_thread가 시작되어 동시에 이 IMU를
    # 건드리기 전, 스레드가 하나도 뜨지 않은 이 시점에 한 번만 전환해 경쟁
    # 상태 없이 결정적으로 적용한다. 같은 인스턴스를 공유하는 sensor_thread의
    # 텔레메트리 yaw(heading)도 이 모드를 따르게 되어, 지자기 기준 대신 자이로
    # 적분값이 되고 시간이 지나면 서서히 드리프트한다 (진동 제거를 위해
    # 감수하기로 한 트레이드오프).
    if GIMBAL_USE_IMU_MODE and sensor.imu is not None:
        try:
            import adafruit_bno055
            sensor.imu.mode = adafruit_bno055.IMUPLUS_MODE
            logger.info("IMU mode -> IMUPLUS (지자기 융합 끔)")
        except Exception as e:
            logger.error("IMU mode switch failed: %s", e)

    validator    = ImageValidator()
    quality      = ImageQuality()
    preprocessor = ImagePreprocess()
    sen_pre      = SensorPreprocess()
    sen_log      = SensorLogger()
    detector     = Detector(mock=MOCK_MODE)
    det_log      = DetectionLogger()
    selector     = RepresentativeSelector()
    time_trigger = TimeTrigger(IMAGE_SEND_INTERVAL_S)
    chunk_cache  = ChunkCache(CHUNK_CACHE_MAX_IMAGES, CHUNK_CACHE_TTL_S)

    tx_q    = queue.PriorityQueue()
    sensor_q = queue.Queue(maxsize=5)
    img_q   = queue.Queue(maxsize=3)
    img_sending = threading.Event()

    # Mock 모드: XBeeSerial 없이 실행
    class MockSerial:
        def write(self, data): pass
        def read_available(self): return b""
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass

    serial = MockSerial() if (MOCK_MODE and COMM_MOCK) else None

    def _run(serial, running):

        threads = [
            threading.Thread(
                target=sensor_loop,
                args=(sensor, sen_pre, sen_log, tx_q, seq, id_mgr, sensor_q, running, enqueue, img_sending),
                daemon=True, name="sensor"
            ),
            threading.Thread(
                target=image_loop,
                args=(camera, validator, quality, preprocessor,
                        detector, det_log, selector, time_trigger,
                        tx_q, seq, id_mgr, img_q, running, enqueue, img_sending),
                daemon=True, name="image"
            ),
            threading.Thread(
                target=image_chunk_loop,
                args=(tx_q, seq, img_q, running, enqueue, img_sending, chunk_cache,
                        IMAGE_SEND_TIMEOUT_S),
                daemon=True, name="img_chunk"
            ),
            threading.Thread(
                target=nack_loop,
                args=(serial, tx_q, seq, running, chunk_cache, enqueue, IMG_RETRANSMIT_PRIORITY,
                        IMAGE_SEND_TIMEOUT_S),
                daemon=True, name="nack"
            ),
            threading.Thread(
                target=heartbeat_loop,
                args=(tx_q, seq, running, enqueue),
                daemon=True, name="heartbeat"
            ),
            threading.Thread(
                target=gimbal_loop,
                args=(running, i2c_lock, sensor.imu),
                daemon=True, name="gimbal"
            ),
            threading.Thread(
                target=sensor.calibrate_ground_altitude,
                args=(90,),
                daemon=True, name="baro_calib"
            ),
        ]
        for t in threads:
            t.start()

        logger.info("Onboard system started")

        bytes_sent   = 0
        packets_sent = 0
        total_duration_s = 0.0
        last_power_report = time.monotonic()

        while running[0]:
            # 이 while 루프는 메인 스레드라 여기서 예외가 새어나가면 프로세스
            # 전체가 죽는다. 개별 구간에 이미 try/except가 있어도, 앞으로
            # 코드가 바뀌며 새로 생길 수 있는 예외까지 다 막아줄 최후의
            # 안전망으로 루프 전체를 한 번 더 감싼다 — 무슨 일이 있어도
            # 이 루프 자체는 절대 멈추지 않아야 한다.
            try:
                try:
                    item = tx_q.get(timeout=0.1)
                except queue.Empty:
                    item = None

                if item is not None:
                    with _type_counts_lock:
                        _type_counts[item.ptype] -= 1
                    if item.on_dequeue is not None:
                        try:
                            item.on_dequeue()
                        except Exception as e:
                            logger.error("on_dequeue callback error: %s", e)
                    try:
                        serial.write(item.raw)
                        n = len(item.raw)
                        bytes_sent   += n
                        packets_sent += 1
                        total_duration_s += n * 8 / XBEE_BAUDRATE  # 송신 시간 누적
                    except Exception as e:
                        logger.error("Serial write error: %s", e)

                # POWER 패킷 주기적 송신
                now = time.monotonic()
                if now - last_power_report >= POWER_REPORT_INTERVAL:
                    try:
                        energy_mwh = (XBEE_VOLTAGE_V * XBEE_CURRENT_MA * total_duration_s) / 3600000.0
                        pd = CommPowerData(
                            timestamp    = time.time(),
                            voltage_v    = XBEE_VOLTAGE_V,
                            current_ma   = XBEE_CURRENT_MA,
                            duration_s   = total_duration_s,
                            energy_mwh   = energy_mwh,
                            bytes_sent   = bytes_sent,
                            packets_sent = packets_sent,
                        )
                        enqueue(tx_q, PacketType.POWER, pd.to_bytes(), seq, 5)
                        logger.info("POWER: duration=%.2fs, energy=%.4fmWh, bytes=%d",
                                    total_duration_s, energy_mwh, bytes_sent)
                    except Exception as e:
                        logger.error("POWER packet error: %s", e)
                    last_power_report = now
            except Exception as e:
                logger.error("Main TX loop error (caught, continuing): %s", e)

        camera.close()
        sensor.close()
        logger.info("Onboard system stopped")

    seq = SeqCounter()

    if COMM_MOCK:
        _run(serial, running)
    else:
        try:
            with XBeeSerial(XBEE_PORT, XBEE_BAUDRATE) as serial:
                _run(serial, running)
        except Exception as e:
            # XBee가 재시도까지 다 실패해도, 카메라/센서/로컬 CSV 기록 같은
            # 나머지 파이프라인은 계속 돌게 한다 — 무선 통신이 완전히
            # 죽더라도 SD카드에는 데이터가 남아야 한다 (0보다는 낫다).
            logger.error("XBee connection failed after retries, running with no radio comm: %s", e)
            _run(MockSerial(), running)


if __name__ == "__main__":
    main()