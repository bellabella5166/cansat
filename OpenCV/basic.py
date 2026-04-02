import cv2
import numpy as np

img = cv2.imread('imageSrc.jpg')

print(img.shape)  # (높이, 너비, 채널)
print(img.dtype)  # uint8

#gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

laplacian_score = cv2.Laplacian(img, cv2.CV_64F).var()
print(f"선명도 점수 : {laplacian_score:.2f}")

if laplacian_score > 100:
    print("판단 : 선명한 이미지")
else:
    print("판단 : 흐린 이미지")

