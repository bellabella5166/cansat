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
from onboard.detection.time_trigger            import TimeTrigger
from onboard.system.config import CAMERA_FPS, QUALITY_SAVE_DIR

logger = logging.getLogger("onboard.image")


def image_loop(camera: Camera, validator: ImageValidator,
               quality: ImageQuality, preprocessor: ImagePreprocess,
               detector: Detector, det_logger: DetectionLogger,
               selector: RepresentativeSelector, time_trigger: TimeTrigger,
               tx_q: queue.PriorityQueue, seq,
               id_mgr: IDManager,
               img_q: queue.Queue, running: list, enqueue_fn, img_sending) -> None:

    interval  = 1.0 / CAMERA_FPS
    next_time = time.monotonic()
    last_yolo_tx_time = time.monotonic()
    logger.info("Image loop started (1 fps)")

    selector.reset()
    time_trigger.start(time.monotonic())

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

            # 2. 손상 이미지 필터링
            img, valid = validator.validate(raw_img)
            if not valid:
                continue

            # 3. 품질 판별 (블러/노출)
            quality_ok, lap_score = quality.check(img)
            if not quality_ok:
                continue
            filename = f"{image_id_str}_{lap_score:.1f}.jpg"
            cv2.imwrite(os.path.join(QUALITY_SAVE_DIR, filename), img)

            # 4. 전처리 (640×640 letterbox)
            preprocessed = preprocessor.process(img)
            if preprocessed is None:
                continue

            # 5. YOLO 탐지
            detections = detector.detect(preprocessed, image_id_str)

            # 6. 탐지 결과 저장
            det_logger.log(detections, raw_img, ts)

            # 7. YOLO_META 패킷 송신
            now_tx = time.monotonic()
            yolo_interval = 2.0 if img_sending.is_set() else 0.0
            if now_tx - last_yolo_tx_time >= yolo_interval:
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
                last_yolo_tx_time = now_tx

            # 8. 대표 이미지 후보 등록 — 트리거 체크보다 먼저!
            selector.add(image_id_str, raw_img, detections, lap_score)

            # 9. 시간 기반 트리거 - 대표 이미지 선별 및 전송
            # 전원 인가(프로그램 시작) 시점부터 IMAGE_SEND_INTERVAL_S 간격으로
            # 무한 반복 발동 (고도값을 신뢰하지 않기로 하고 전환).
            fire = time_trigger.poll(now)

            if fire:
                rep_img, rep_id = selector.select()
                if rep_img is not None:
                    rep_id_u16 = id_mgr.get_image_id_uint16()
                    try:
                        img_q.put_nowait(("representative", rep_id_u16, rep_img))
                        logger.info("Time trigger fired, id=%s", rep_id)
                        time_trigger.confirm_fired()  # 성공했을 때만 다음 예정 시각으로 진행
                        selector.reset()               # 다음 구간을 위해 후보 초기화
                    except Exception:
                        pass   # 큐 실패 시 상태 유지 → 다음 프레임에서 재시도
                else:
                    logger.warning("No representative image available for time trigger — will retry next frame")
                    # confirm_fired를 호출하지 않음 → 후보 쌓일 때까지 재시도 가능

        except Exception as e:
            logger.error("Image loop error: %s", e)

    logger.info("Image loop stopped")