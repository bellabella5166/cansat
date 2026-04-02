import csv
import os

# 1. 패킷 생성 (송신측)
def create_packet(temperature):
    header = 0xAA
    data = int(float(temperature)) 
    data_bytes = data.to_bytes(2, byteorder='big')
    checksum = sum(data_bytes) % 256

    packet = bytes([header, len(data_bytes)]) + data_bytes + bytes([checksum])
    return packet

# 2. 패킷 파싱 (수신측)
def parse_packet(packet):
    header = packet[0]
    length = packet[1]
    data_bytes = packet[2:2+length]
    checksum = packet[-1]

    # 체크섬 검증
    if sum(data_bytes) % 256 != checksum:
        print("⚠️ 오류 : 체크섬 불일치")
        return None

    temperature = int.from_bytes(data_bytes, byteorder='big') / 100.0
    return temperature

# --- 메인 실행부: CSV 파일 읽기 ---
file_name = "temp_data.csv"

# 파일이 존재하는지 먼저 확인
if not os.path.exists(file_name):
    print(f"❌ '{file_name}' 파일이 없습니다. 먼저 데이터를 저장하는 코드를 실행하세요.")
else:
    print(f"📂 {file_name}에서 데이터를 불러와 패킷을 생성합니다...\n")
    
    with open(file_name, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            # CSV에서 'Raw_Temperature' 값 가져오기
            raw_temp_str = row['Raw_Temperature']
            
            # 1. 송신측: 패킷 생성
            packet = create_packet(raw_temp_str)
            
            # 2. 수신측: 패킷 파싱
            parsed_temp = parse_packet(packet)
            
            if parsed_temp is not None:
                print(f"[데이터 {row['Index']}] Raw: {raw_temp_str} -> 생성된 패킷: {packet.hex()} -> 복원된 온도: {parsed_temp}°C")

    print("\n✅ 모든 데이터 처리가 완료되었습니다.")

print("사실 나는 dev야")