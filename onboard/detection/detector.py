import numpy as np
import onnxruntime as ort
from onboard.config import (
    MOCK_MODE,
    MODEL_PATH,
    CONFIDENCE_THRESHOLD,
)


class Detector:
    """
    YOLOv8n ONNX 기반 농경지/건물 객체 탐지를 수행한다.
    Mock 모드에서는 랜덤 탐지 결과를 생성한다.
    """

    CLASS_NAMES = {0: 'farm', 1: 'building'}

    def __init__(self, model_path: str = MODEL_PATH, mock: bool = MOCK_MODE):
        """
        Args:
            model_path (str): ONNX 모델 경로
            mock (bool): True면 Mock 모드 (로컬 테스트용)
        """
        self.mock = mock
        self.confidence_threshold = CONFIDENCE_THRESHOLD
        self.session = None

        if not self.mock:
            self._load_model(model_path)

    def _load_model(self, model_path: str):
        """ONNX 모델 로드"""
        try:
            self.session = ort.InferenceSession(
                model_path,
                providers=['CPUExecutionProvider']
            )
            print(f"[Detector] ✅ model load succeed : {model_path}")
        except Exception as e:
            print(f"[Detector] ❌ model load fail : {e}")
            self.session = None

    def detect(self, image: np.ndarray, image_id: str) -> list:
        """
        이미지에서 농경지/건물을 탐지한다.

        Args:
            image (np.ndarray): 전처리된 이미지 (640×640×3, float32)
            image_id (str): 이미지 고유 식별자

        Returns:
            list of dict: 탐지 결과
                [{'class': str, 'confidence': float, 'bbox': [x1,y1,x2,y2], 'image_id': str}]
                탐지 결과 없으면 빈 리스트 반환
        """
        if image is None:
            print("[Detector] ❌ input image None")
            return []

        try:
            if self.mock:
                return self._mock_detect(image_id)
            else:
                return self._real_detect(image, image_id)

        except Exception as e:
            print(f"[Detector] ❌ detection error: {e}")
            return []

    def _mock_detect(self, image_id: str) -> list:
        """Mock 탐지 결과 생성 (로컬 테스트용)"""
        results = []
        num_detections = np.random.randint(0, 4)

        for _ in range(num_detections):
            x1 = float(np.random.randint(0, 540))
            y1 = float(np.random.randint(0, 540))
            x2 = float(min(x1 + np.random.randint(50, 100), 640.0))
            y2 = float(min(y1 + np.random.randint(50, 100), 640.0))

            results.append({
                'class': self.CLASS_NAMES[np.random.randint(0, 2)],
                'confidence': float(np.random.uniform(
                    self.confidence_threshold, 1.0
                )),
                'bbox': [x1, y1, x2, y2],
                'image_id': image_id
            })

        return results

    def _real_detect(self, image: np.ndarray, image_id: str) -> list:
        """실제 YOLOv8n ONNX 추론"""
        if self.session is None:
            print("[Detector] ❌ model load None")
            return []

        # ONNX 입력 형식: (1, 3, 640, 640), float32
        input_tensor = image.astype(np.float32).transpose(2, 0, 1)[np.newaxis, :]

        input_name = self.session.get_inputs()[0].name
        outputs = self.session.run(None, {input_name: input_tensor})

        return self._parse_output(outputs[0], image_id)

    def _parse_output(self, output: np.ndarray, image_id: str) -> list:
        """YOLOv8n 출력 파싱"""
        results = []

        # YOLOv8n 출력: (1, 6, 8400) → (8400, 6)
        predictions = output[0].T

        for pred in predictions:
            x_center, y_center, w, h = pred[0], pred[1], pred[2], pred[3]
            class_scores = pred[4:]
            class_id = int(np.argmax(class_scores))
            confidence = float(class_scores[class_id])

            if confidence < self.confidence_threshold:
                continue

            # bbox 변환 (center → corner)
            x1 = float(x_center - w / 2)
            y1 = float(y_center - h / 2)
            x2 = float(x_center + w / 2)
            y2 = float(y_center + h / 2)

            if class_id in self.CLASS_NAMES:
                results.append({
                    'class': self.CLASS_NAMES[class_id],
                    'confidence': confidence,
                    'bbox': [x1, y1, x2, y2],
                    'image_id': image_id
                })

        return results