# onboard/system/threads/image_thread.py

from __future__ import annotations

import logging
import os
import queue
import time
import cv2

from protocol  import PacketType
from telemetry import YoloDetection

from onboard.input.camera                      import Camera
from onboard.input.id_manager                  import IDManager
from onboard.preprocess.image_validator        import ImageValidator
from onboard.preprocess.image_quality          import ImageQuality
from onboard.preprocess.image_preprocess       import ImagePreprocess
from onboard.detection.detector                import Detector
from onboard.detection.detection_logger        import DetectionLogger
from onboard.detection.representative_selector import RepresentativeSelector
from onboard.system.config import CAMERA_FPS, ALTITUDE_TRIGGER, QUALITY_SAVE_DIR

logger = logging.getLogger("onboard.image")


def image_loop(camera: Camera, validator: ImageValidator,
               quality: ImageQuality, preprocessor: ImagePreprocess,
               detector: Detector, det_logger: DetectionLogger,
               selector: RepresentativeSelector,
               tx_q: queue.PriorityQueue, seq,
               id_mgr: IDManager, sensor_q: queue.Queue,
               img_q: queue.Queue, running: list, enqueue_fn) -> None:

    interval  = 1.0 / CAMERA_FPS
    next_time = time.monotonic()
    logger.info("Image loop started (1 fps)")

    selector.reset()
    rep_sent = False

    while running[0]:
        now = time.monotonic()

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

            # 3. 고도 트리거 - 대표 이미지 선별 및 전송 (1회만)
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

            # 4. 손상 이미지 필터링
            img, valid = validator.validate(raw_img)
            if not valid:
                continue

            # 5. 품질 판별 (블러/노출/자세각)
            quality_ok, lap_score = quality.check(img, imu)
            if not quality_ok:
                continue
            filename = f"{image_id_str}_{lap_score:.1f}.jpg"
            cv2.imwrite(os.path.join(QUALITY_SAVE_DIR, filename), img)

            # 6. 전처리 (640×640 letterbox)
            preprocessed = preprocessor.process(img)
            if preprocessed is None:
                continue

            # 7. YOLO 탐지
            detections = detector.detect(preprocessed, image_id_str)

            # 8. 탐지 결과 저장
            det_logger.log(detections, raw_img, ts)

            # 9. YOLO_META 패킷 송신
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
                enqueue_fn(tx_q, PacketType.YOLO_META, yd.to_bytes(), seq, 50)

            # 10. 대표 이미지 후보 등록 (전송 전까지만)
            if not rep_sent:
                selector.add(image_id_str, raw_img, detections, lap_score)

        except Exception as e:
            logger.error("Image loop error: %s", e)

    logger.info("Image loop stopped")