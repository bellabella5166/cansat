# onboard/system/main.py

from __future__ import annotations

import logging
import os
import queue
import signal
import sys
import threading
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
from onboard.system.threads.sensor_thread      import sensor_loop
from onboard.system.threads.image_thread       import image_loop
from onboard.system.threads.chunk_thread       import image_chunk_loop
from onboard.system.threads.heartbeat_thread   import heartbeat_loop
from onboard.system.threads.nack_thread        import nack_loop

# ── 설정 ──────────────────────────────────────────────────────────────────────
from onboard.system.config import (
    MOCK_MODE, COMM_MOCK,
    IMAGE_SAVE_DIR, SENSOR_SAVE_DIR, LOG_SAVE_DIR,
    XBEE_PORT, XBEE_BAUDRATE, QUALITY_SAVE_DIR,
    CAMERA_FPS,
    MAX_RETRY,
    ALTITUDE_TRIGGER,
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
}

# ── 큐 최대 크기 ──────────────────────────────────────────────────────────────
SENSOR_Q_MAX = 20
YOLO_Q_MAX   = 50
IMG_Q_MAX    = 200
HB_INTERVAL  = 5.0

# ── TX 큐 아이템 ──────────────────────────────────────────────────────────────
@dataclass(order=True)
class TxItem:
    priority: int
    raw: bytes = field(compare=False)


# ── 시퀀스 카운터 (thread-safe) ───────────────────────────────────────────────
class SeqCounter:
    def __init__(self):
        self._v, self._lock = 0, threading.Lock()

    def next(self) -> int:
        with self._lock:
            self._v = (self._v + 1) & 0xFFFF
            return self._v


# ── 큐 enqueue 헬퍼 ───────────────────────────────────────────────────────────
def enqueue(q: queue.PriorityQueue, ptype: PacketType,
            payload: bytes, seq: SeqCounter, max_size: int) -> None:
    if q.qsize() >= max_size:
        logger.debug("Queue full (%s), packet dropped", ptype.name)
        return
    raw = encode_packet(Packet(ptype=ptype, seq=seq.next(), payload=payload))
    try:
        q.put_nowait(TxItem(_PRIORITY.get(ptype, 99), raw))
    except queue.Full:
        logger.warning("TX queue full: %s dropped", ptype.name)

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

    # 모듈 초기화
    id_mgr       = IDManager()
    camera       = Camera(mock=MOCK_MODE)
    sensor       = Sensor(mock=MOCK_MODE)
    validator    = ImageValidator()
    quality      = ImageQuality()
    preprocessor = ImagePreprocess()
    sen_pre      = SensorPreprocess()
    sen_log      = SensorLogger()
    detector     = Detector(mock=MOCK_MODE)
    det_log      = DetectionLogger()
    selector     = RepresentativeSelector()

    tx_q    = queue.PriorityQueue()
    sensor_q = queue.Queue(maxsize=5)
    img_q   = queue.Queue(maxsize=3)

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
                args=(sensor, sen_pre, sen_log, tx_q, seq, id_mgr, sensor_q, running, enqueue),
                daemon=True, name="sensor"
            ),
            threading.Thread(
                target=image_loop,
                args=(camera, validator, quality, preprocessor,
                      detector, det_log, selector,
                      tx_q, seq, id_mgr, sensor_q, img_q, running, enqueue),
                daemon=True, name="image"
            ),
            threading.Thread(
                target=image_chunk_loop,
                args=(tx_q, seq, img_q, running, enqueue),
                daemon=True, name="img_chunk"
            ),
            threading.Thread(
                target=nack_loop,
                args=(serial, tx_q, seq, running),
                daemon=True, name="nack"
            ),
            threading.Thread(
                target=heartbeat_loop,
                args=(tx_q, seq, running, enqueue),
                daemon=True, name="heartbeat"
            ),
        ]
        for t in threads:
            t.start()

        logger.info("Onboard system started")

        while running[0]:
            try:
                item = tx_q.get(timeout=0.1)
                serial.write(item.raw)
            except queue.Empty:
                pass
            except Exception as e:
                logger.error("Serial write error: %s", e)

        camera.close()
        sensor.close()
        logger.info("Onboard system stopped")

    seq = SeqCounter()

    if COMM_MOCK:
        _run(serial, running)
    else:
        with XBeeSerial(XBEE_PORT, XBEE_BAUDRATE) as serial:
            _run(serial, running)


if __name__ == "__main__":
    main()