import cv2
import numpy as np

result = cv2.imread('imageSrc.jpg')

resized = cv2.resize(result, (224, 224))

normalized = resized / 255.0

# 5. 결과 확인
print(f"원본 크기 : {result.shape}") 
print(f"조정 후 크기 : {resized.shape}")
print(f"정규화 전 최댓값 : {resized.max()}")
print(f"정규화 후 최댓값 : {normalized.max():.2f}")

# 6. 저장
cv2.imwrite('preprocessed.jpg', resized)
print("저장 완료!")