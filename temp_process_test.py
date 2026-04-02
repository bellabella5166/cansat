import time
import random

# 현실적인 raw 온도 데이터 생성
def generate_raw_temperature():
    base_temp = 2500  # 25.00°C 기준
    noise = random.randint(-30, 30)        # 일반 노이즈
    spike = random.choices(
        [0, random.randint(3000, 7000)],   # 가끔 이상값 발생
        weights=[95, 5]                     # 95% 정상, 5% 이상값
    )[0]
    return base_temp + noise + spike

# 100개 raw 데이터 생성
raw_data = [generate_raw_temperature() for _ in range(100)]

import csv

file_name = "temp_data.csv"

with open(file_name, mode="w", newline="") as file:
    writer = csv.writer(file)
    # 헤더(제목) 작성
    writer.writerow(["Index", "Raw_Temperature"])
    
    # 데이터 행 단위로 작성
    for i, value in enumerate(raw_data):
        writer.writerow([i, value])

print(f"✅ 데이터가 {file_name}에 저장되었습니다!")

import numpy as np
import time

# 1. raw 데이터 → 온도 변환
raw_data = np.array(raw_data)
temp_data = raw_data / 100.0

# 2. 이상값 처리
mask = (temp_data >= -40) & (temp_data <= 85)
invalid = temp_data[~mask]
for val in invalid:
    print(f"이상값 감지 : {val:.2f}°C → 무시")
temp_clean = np.where(mask, temp_data, np.nan)

# 3. 이동평균 필터
def moving_average(data, window=3):
    return np.convolve(data, np.ones(window)/window, mode='valid')

temp_valid = temp_clean[~np.isnan(temp_clean)]
avg_data = moving_average(temp_valid)

# 4. 출력
for i, temp in enumerate(temp_valid):
    if i >= 2:  # window=3 이상부터 평균 출력 가능
        print(f"온도 : {temp:.2f}°C | 평균 : {avg_data[i-2]:.2f}°C")
    else:
        print(f"온도 : {temp:.2f}°C")
    time.sleep(0.5)