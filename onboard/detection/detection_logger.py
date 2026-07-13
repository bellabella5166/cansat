
import os
import csv
import cv2
import numpy as np
from onboard.system.config import IMAGE_SAVE_DIR, SENSOR_SAVE_DIR
from onboard.input.timestamp_manager import format_timestamp


class DetectionLogger:
    """
    유효한 탐지 결과를 CSV로 저장하고
    bbox가 시각화된 이미지를 SD카드에 저장한다.
    """

    def __init__(self, csv_dir: str = SENSOR_SAVE_DIR, image_dir: str = IMAGE_SAVE_DIR):
        """
        Args:
            csv_dir (str): CSV 저장 경로
            image_dir (str): bbox 이미지 저장 경로
        """
        self.csv_dir = csv_dir
        self.image_dir = image_dir
        self.csv_path = os.path.join(self.csv_dir, "yolo_detection_log.csv")

        os.makedirs(self.csv_dir, exist_ok=True)
        os.makedirs(self.image_dir, exist_ok=True)
        self._init_csv()

    def _init_csv(self):
        """CSV 헤더 작성 (파일이 없을 때만)"""
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'image_id', 'timestamp',
                    'class', 'confidence',
                    'x1', 'y1', 'x2', 'y2'
                ])

    def log(self, detections: list, raw_image: np.ndarray, timestamp: float) -> bool:
        """
        탐지 결과를 CSV에 저장하고 bbox 시각화 이미지를 저장한다.

        Args:
            detections (list): 탐지 결과 list of dict
            raw_image (np.ndarray): 원시 이미지 (H×W×3)
            timestamp (float): 타임스탬프

        Returns:
            bool: 저장 성공 시 True, 실패 시 False
        """
        if detections is None:
            print("[DetectionLogger] ❌ detection result None")
            return False

        if raw_image is None:
            print("[DetectionLogger] ❌ raw image None")
            return False

        # 탐지 결과 없으면 저장 안 함
        if len(detections) == 0:
            return True

        try:
            # 1. CSV 저장
            with open(self.csv_path, 'a', newline='') as f:
                writer = csv.writer(f)
                for det in detections:
                    x1, y1, x2, y2 = det['bbox']
                    writer.writerow([
                        det['image_id'], timestamp,
                        det['class'], det['confidence'],
                        x1, y1, x2, y2
                    ])

            # 2. bbox 시각화 이미지 저장
            self._save_bbox_image(detections, raw_image, timestamp)

            return True

        except Exception as e:
            print(f"[DetectionLogger] ❌ save error: {e}")
            return False

    def _save_bbox_image(self, detections: list, raw_image: np.ndarray, timestamp: float):
        """bbox가 그려진 이미지를 저장한다."""

        # 색상 정의
        colors = {'farm': (0, 255, 0), 'building': (0, 0, 255)}

        # 이미지 복사 (원본 보존)
        vis_image = raw_image.copy()

        # 이미지 크기
        h, w = vis_image.shape[:2]

        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            cls = det['class']
            conf = det['confidence']

            # bbox 좌표가 640×640 기준이면 원본 크기로 스케일링
            scale_x = w / 640.0
            scale_y = h / 640.0
            x1 = int(x1 * scale_x)
            y1 = int(y1 * scale_y)
            x2 = int(x2 * scale_x)
            y2 = int(y2 * scale_y)

            color = colors.get(cls, (255, 255, 255))

            # bbox 그리기
            cv2.rectangle(vis_image, (x1, y1), (x2, y2), color, 2)

            # 라벨 그리기
            label = f"{cls} {conf:.2f}"
            cv2.putText(vis_image, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # 저장
        image_id = detections[0]['image_id']
        filename = f"bbox_{image_id}_{format_timestamp(timestamp)}.jpg"
        save_path = os.path.join(self.image_dir, filename)
        cv2.imwrite(save_path, cv2.cvtColor(vis_image, cv2.COLOR_RGB2BGR))