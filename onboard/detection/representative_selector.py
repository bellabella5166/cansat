
import numpy as np


class RepresentativeSelector:
    """
    탐지 결과 중 대표 이미지를 선별한다.
    1순위: 평균 신뢰도가 가장 높은 이미지
    2순위: laplacian_score가 가장 높은 이미지
    """

    def __init__(self):
        # {image_id: {'image': np.ndarray, 'confidences': list, 'laplacian_score': float}}
        self._candidates = {}

    def add(self, image_id: str, image: np.ndarray,
            detections: list, laplacian_score: float):
        """
        대표 이미지 후보를 추가한다.

        Args:
            image_id (str): 이미지 고유 식별자
            image (np.ndarray): 원시 이미지
            detections (list): 탐지 결과 list of dict
            laplacian_score (float): 품질 점수
        """
        if image is None or detections is None:
            return

        confidences = [det['confidence'] for det in detections]

        self._candidates[image_id] = {
            'image': image,
            'confidences': confidences,
            'laplacian_score': laplacian_score
        }

    def select(self) -> tuple:
        """
        대표 이미지를 선별한다.

        Returns:
            tuple: (np.ndarray, image_id: str)
                   후보 없으면 (None, None) 반환
        """
        if not self._candidates:
            print("[RepresentativeSelector] ❌ candidate image none")
            return None, None

        # 1순위: 탐지 있고 평균 신뢰도 높은 이미지
        # 2순위: 탐지 없어도 라플라시안 점수 높은 이미지
        best_id = max(
            self._candidates,
            key=lambda k: (
                len(self._candidates[k]['confidences']) > 0,           # 탐지 여부 (있으면 우선)
                np.mean(self._candidates[k]['confidences']) if len(self._candidates[k]['confidences']) > 0 else 0.0,
                self._candidates[k]['laplacian_score']
            )
        )

        print(f"[RepresentativeSelector] Selected: {best_id}, "
              f"detections={len(self._candidates[best_id]['confidences'])}, "
              f"laplacian={self._candidates[best_id]['laplacian_score']:.2f}")
        return self._candidates[best_id]['image'], best_id

    def reset(self):
        """후보 초기화 (테스트 용도)"""
        self._candidates = {}