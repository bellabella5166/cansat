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
from onboard.detection.checkpoint_trigger       import CheckpointTrigger
from onboard.preprocess.altitude_arbiter        import AltitudeArbiter
from onboard.preprocess.altitude_anchor         import AltitudeAnchor
from onboard.system.config import CAMERA_FPS, QUALITY_SAVE_DIR

logger = logging.getLogger("onboard.image")


def image_loop(camera: Camera, validator: ImageValidator,
               quality: ImageQuality, preprocessor: ImagePreprocess,
               detector: Detector, det_logger: DetectionLogger,
               selector: RepresentativeSelector, altitude_arbiter: AltitudeArbiter,
               checkpoint_trigger: CheckpointTrigger, altitude_anchor: AltitudeAnchor,
               tx_q: queue.PriorityQueue, seq,
               id_mgr: IDManager, sensor_q: queue.Queue,
               img_q: queue.Queue, running: list, enqueue_fn, img_sending) -> None:

    interval  = 1.0 / CAMERA_FPS
    next_time = time.monotonic()
    last_yolo_tx_time = time.monotonic()
    logger.info("Image loop started (1 fps)")

    selector.reset()

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
            now_wall = time.time()  # anchor/시간 백업 트리거용 wall-clock (센서 timestamp와 동일 기준)
            alt, alt_source = altitude_arbiter.resolve(imu)
            altitude_anchor.update(imu, now_wall)


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

            # 9. 대표 이미지 후보 등록 (남은 체크포인트가 있는 동안만) — 트리거 체크보다 먼저!
            if not checkpoint_trigger.all_done():
                selector.add(image_id_str, raw_img, detections, lap_score)

            # 10. 고도 체크포인트 트리거 - 대표 이미지 선별 및 전송
            # 정상 고도 기반 트리거(기압계 우선, 이상 시 GPS로 자동 전환)를 먼저 확인하고,
            # baro/gps 다중화마저 둘 다 무응답(SENSOR_FAILURE_TIMEOUT_S 이상)일 때만
            # anchor 기반 시간 백업 트리거로 넘어간다.
            via_time_backup = False
            fire = checkpoint_trigger.poll(alt)
            if not fire and not checkpoint_trigger.all_done() and altitude_anchor.is_sensor_failure(now_wall):
                fire = checkpoint_trigger.poll_time_backup(
                    altitude_anchor.last_valid_altitude, altitude_anchor.last_valid_time, now_wall)
                via_time_backup = fire

            if fire:
                target = checkpoint_trigger.current_target()
                rep_img, rep_id = selector.select()
                if rep_img is not None:
                    rep_id_u16 = id_mgr.get_image_id_uint16()
                    try:
                        img_q.put_nowait(("representative", rep_id_u16, rep_img))
                        if via_time_backup:
                            info = checkpoint_trigger.time_backup_info()
                            logger.info(
                                "Checkpoint %.0fm TIME-BACKUP triggered (baro/gps both unresponsive): "
                                "anchor_altitude=%.1fm anchor_time=%.3f estimated_time=%.3f fired_time=%.3f, id=%s",
                                target, info["anchor_altitude"], info["anchor_time"],
                                info["estimated_time"], now_wall, rep_id
                            )
                        else:
                            logger.info("Checkpoint %.0fm triggered at alt=%.1fm (source=%s), id=%s",
                                        target, alt, alt_source, rep_id)
                        checkpoint_trigger.confirm_fired()  # 성공했을 때만 다음 체크포인트로 진행
                        selector.reset()                    # 다음 체크포인트를 위해 후보 초기화
                    except Exception:
                        pass   # 큐 실패 시 상태 유지 → 다음 프레임에서 재시도
                else:
                    logger.warning("No representative image available at alt=%.1fm (source=%s) for checkpoint %.0fm — will retry next frame",
                                    alt, alt_source, target)
                    # confirm_fired를 호출하지 않음 → 후보 쌓일 때까지 재시도 가능

        except Exception as e:
            logger.error("Image loop error: %s", e)

    logger.info("Image loop stopped")