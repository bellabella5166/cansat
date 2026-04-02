import cv2
import numpy as np

def load_image(path):
    img = cv2.imread(path)

    if img is None:
        print(f"오류 : 이미지를 읽을 수 없음 → {path}")
        return None

    if img.shape[0] == 0 or img.shape[1] == 0:
        print("오류 : 이미지 크기가 0")
        return None

    if img.max() == 0:
        print("오류 : 이미지가 완전히 검정 (빈 이미지)")
        return None

    print(f"정상 이미지 : {img.shape}")
    return img


img = load_image('imageSrc.jpg')

if img is not None:
    print("이미지 정상 로드 완료!")
else:
    print("이미지 로드 실패!")

img = load_image('없는파일.jpg')
img = load_image('image.jpg')