# onboard/system/main.py

from __future__ import annotations

import logging
import os
import queue
import signal
import sys
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path

# ── 경로 설정 ──────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent.parent
SHARED_DIR = BASE_DIR / "shared"
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(BASE_DIR))

# ── shared 모듈 ────────────────────────────────────────────────────────────────
from protocol      import Packet, PacketType, encode_packet, PacketParser
from telemetry     import SensorData, YoloDetection, decode_nack
from image_chunker import prepare_chunks
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

# ── 설정 ──────────────────────────────────────────────────────────────────────
from onboard.config import (
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

# ── 전역 상태 ─────────────────────────────────────────────────────────────────
_running = True


def _stop(sig, frame):
    global _running
    _running = False
    logger.info("Stop signal received")


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


# ── 센서 루프 (10 Hz) ─────────────────────────────────────────────────────────
def sensor_loop(sensor: Sensor, preprocess: SensorPreprocess,
                sensor_logger: SensorLogger, tx_q: queue.PriorityQueue,
                seq: SeqCounter, id_mgr: IDManager,
                sensor_q: queue.Queue):

    interval  = 0.1  # 10 Hz
    next_time = time.monotonic()
    logger.info("Sensor loop started (10 Hz)")

    while _running:
        now = time.monotonic()
        if now < next_time:
            time.sleep(next_time - now)
        next_time += interval

        try:
            sid     = id_mgr.get_sensor_id()
            raw, ts = sensor.read(sid)
            if raw is None:
                continue

            processed = preprocess.process(raw, ts)
            if processed is None:
                continue

            sensor_logger.log(processed)

            # ★ 실제 교체 지점: SensorData 직접 구성
            sd = SensorData(
                timestamp     = processed.get("timestamp",    0.0),
                latitude      = processed.get("lat",          0.0),
                longitude     = processed.get("lon",          0.0),
                gps_altitude  = processed.get("gps_altitude", 0.0),
                baro_altitude = processed.get("baro_altitude",0.0),
                temperature   = processed.get("temp",         0.0),
                pressure      = processed.get("pressure",     0.0),
                roll          = processed.get("roll",         0.0),
                pitch         = processed.get("pitch",        0.0),
                yaw           = processed.get("yaw",          0.0),
                accel_x       = processed.get("accel_x",      0.0),
                accel_y       = processed.get("accel_y",      0.0),
                accel_z       = processed.get("accel_z",      0.0),
                gyro_x        = processed.get("gyro_x",       0.0),
                gyro_y        = processed.get("gyro_y",       0.0),
                gyro_z        = processed.get("gyro_z",       0.0),
                satellites    = int(processed.get("satellites",   0)),
                fix_quality   = int(processed.get("fix_quality",  0)),
                hdop          = float(processed.get("hdop",       0.0)),
            )
            enqueue(tx_q, PacketType.SENSOR, sd.to_bytes(), seq, SENSOR_Q_MAX)

            # 이미지 루프에 IMU 데이터 전달
            try:
                sensor_q.put_nowait(processed)
            except Exception:
                pass

        except Exception as e:
            logger.error("Sensor loop error: %s", e)

    logger.info("Sensor loop stopped")


# ── 이미지 루프 (1 fps) ───────────────────────────────────────────────────────
def image_loop(camera: Camera, validator: ImageValidator,
               quality: ImageQuality, preprocessor: ImagePreprocess,
               detector: Detector, det_logger: DetectionLogger,
               selector: RepresentativeSelector,
               tx_q: queue.PriorityQueue, seq: SeqCounter,
               id_mgr: IDManager, sensor_q: queue.Queue,
               img_q: queue.Queue):

    interval  = 1.0 / CAMERA_FPS
    next_time = time.monotonic()
    hb_time   = time.monotonic()
    logger.info("Image loop started (1 fps)")

    selector.reset()
    rep_sent = False  # 대표 이미지 전송 여부 플래그

    while _running:
        now = time.monotonic()

        # HEARTBEAT 5초 주기
        if now - hb_time >= HB_INTERVAL:
            enqueue(tx_q, PacketType.HEARTBEAT, b"", seq, 5)
            hb_time = now

        if now < next_time:
            time.sleep(0.01)
            continue
        next_time += interval

        try:
            # 1. 이미지 캡처
            image_id_str = id_mgr.get_image_id()
            image_id_u16 = id_mgr.get_image_id_uint16()
            raw_img, ts, _ = camera.capture(image_id_str)
            if raw_img is None:
                continue

            # 2. 최신 IMU/고도 데이터 가져오기
            imu = {}
            while not sensor_q.empty():
                imu = sensor_q.get_nowait()

            # ★ 고도 150m 이하 도달 시 대표 이미지 선별 및 전송 (1회만)
            baro_alt = imu.get("baro_altitude", 9999.0)
            if not rep_sent and baro_alt <= ALTITUDE_TRIGGER:
                rep_img, rep_id = selector.select()
                if rep_img is not None:
                    rep_id_u16 = id_mgr.get_image_id_uint16()
                    try:
                        img_q.put_nowait(("representative", rep_id_u16, rep_img))
                        logger.info("Representative image triggered at alt=%.1fm, id=%s",
                                    baro_alt, rep_id)
                    except Exception:
                        pass
                else:
                    logger.warning("No representative image available at alt=%.1fm", baro_alt)
                rep_sent = True

            # 3. 손상 이미지 필터링
            img, valid = validator.validate(raw_img)
            if not valid:
                continue

            # 4. 품질 판별 (블러/노출/자세각)
            quality_ok, lap_score = quality.check(img, imu)
            if not quality_ok:
                continue
            filename = f"{image_id_str}_{lap_score:.1f}.jpg"
            cv2.imwrite(os.path.join(QUALITY_SAVE_DIR, filename), img)
            
            # 5. 전처리 (640×640 letterbox)
            preprocessed = preprocessor.process(img)
            if preprocessed is None:
                continue

            # 6. YOLO 탐지
            detections = detector.detect(preprocessed, image_id_str)

            # 7. 탐지 결과 저장
            det_logger.log(detections, raw_img, ts)

            # 8. YOLO_META 패킷 송신
            for i, det in enumerate(detections):
                yd = YoloDetection(
                    timestamp  = ts,
                    image_id   = image_id_u16,
                    object_id  = i,
                    class_id   = 0 if det["class"] == "farm" else 1,
                    confidence = det["confidence"],
                    x_min      = int(det["bbox"][0]),
                    y_min      = int(det["bbox"][1]),
                    x_max      = int(det["bbox"][2]),
                    y_max      = int(det["bbox"][3]),
                )
                enqueue(tx_q, PacketType.YOLO_META, yd.to_bytes(), seq, YOLO_Q_MAX)

            # 9. 대표 이미지 후보 등록 (전송 전까지만)
            if not rep_sent:
                selector.add(image_id_str, raw_img, detections, lap_score)

        except Exception as e:
            logger.error("Image loop error: %s", e)

    logger.info("Image loop stopped")


# ── 이미지 청크 루프 ──────────────────────────────────────────────────────────
def image_chunk_loop(tx_q: queue.PriorityQueue, seq: SeqCounter,
                     img_q: queue.Queue):
    logger.info("Image chunk loop started")
    while _running:
        try:
            kind, img_id, raw_img = img_q.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            import io
            from PIL import Image
            buf = io.BytesIO()
            Image.fromarray(raw_img).save(buf, format="JPEG")
            chunks = prepare_chunks(buf.getvalue(), img_id)
            for chunk_payload in chunks:
                enqueue(tx_q, PacketType.IMG, chunk_payload, seq, IMG_Q_MAX)
            logger.info("Representative image id=%d → %d chunks queued",
                        img_id, len(chunks))
        except Exception as e:
            logger.error("Image chunk error: %s", e)
    logger.info("Image chunk loop stopped")


# ── NACK 수신 루프 ────────────────────────────────────────────────────────────
def nack_loop(serial, tx_q: queue.PriorityQueue, seq: SeqCounter):
    parser = PacketParser()
    retry_counts: dict[int, int] = {}
    logger.info("NACK loop started")

    while _running:
        try:
            raw = serial.read_available()
        except Exception as e:
            logger.error("Serial read error: %s", e)
            time.sleep(0.1)
            continue

        if raw:
            for pkt in parser.feed(raw):
                if pkt.ptype == PacketType.NACK:
                    try:
                        img_id, missing = decode_nack(pkt.payload)
                        cnt = retry_counts.get(img_id, 0) + 1
                        retry_counts[img_id] = cnt
                        if cnt <= MAX_RETRY:
                            logger.info(
                                "NACK received: image_id=%d missing=%s (retry %d/%d)",
                                img_id, missing, cnt, MAX_RETRY
                            )
                        else:
                            logger.warning(
                                "image_id=%d max retry exceeded", img_id
                            )
                    except Exception as e:
                        logger.error("NACK decode error: %s", e)

        time.sleep(0.005)

    logger.info("NACK loop stopped")


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
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

    def _run(serial):
        threads = [
            threading.Thread(
                target=sensor_loop,
                args=(sensor, sen_pre, sen_log, tx_q, seq, id_mgr, sensor_q),
                daemon=True, name="sensor"
            ),
            threading.Thread(
                target=image_loop,
                args=(camera, validator, quality, preprocessor,
                      detector, det_log, selector,
                      tx_q, seq, id_mgr, sensor_q, img_q),
                daemon=True, name="image"
            ),
            threading.Thread(
                target=image_chunk_loop,
                args=(tx_q, seq, img_q),
                daemon=True, name="img_chunk"
            ),
            threading.Thread(
                target=nack_loop,
                args=(serial, tx_q, seq),
                daemon=True, name="nack"
            ),
        ]
        for t in threads:
            t.start()

        logger.info("Onboard system started")

        while _running:
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
        _run(serial)
    else:
        with XBeeSerial(XBEE_PORT, XBEE_BAUDRATE) as serial:
            _run(serial)


if __name__ == "__main__":
    main()