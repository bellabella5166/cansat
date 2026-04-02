import cv2

img = cv2.imread('imageSrc.jpg')


gaussian = cv2.GaussianBlur(img, (15,15), 5)
result = cv2.medianBlur(gaussian, 7)
result = cv2.GaussianBlur(result, (9,9), 3)

cv2.imwrite('denoised.jpg', result)