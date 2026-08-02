
import sys
import queue
import threading
import time
import numpy as np
sys.path.insert(0, ".")
sys.path.insert(0, "shared")

from onboard.detection.representative_selector import RepresentativeSelector
from onboard.system.main import enqueue, TxItem, SeqCounter
from protocol import PacketType, PacketParser

print("=" * 50)
print("[1] 후보 등록 후 트리거 - 정상 동작 확인")
selector = RepresentativeSelector()
dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)

# 후보 3장 등록
selector.add("IMG_001", dummy_img, [], 50.0)          # 탐지 없음
selector.add("IMG_002", dummy_img, [{"confidence": 0.8}], 80.0)  # 탐지 있음
selector.add("IMG_003", dummy_img, [{"confidence": 0.6}], 60.0)  # 탐지 있음

rep_img, rep_id = selector.select()
assert rep_img is not None, "FAIL: 후보 있는데 None 반환"
assert rep_id == "IMG_002", f"FAIL: 신뢰도 높은 이미지 선택 안됨 (got {rep_id})"
print(f"  선택된 이미지: {rep_id}")
print("  PASS")

print("=" * 50)
print("[2] 탐지 없어도 라플라시안 기준으로 선택 확인")
selector2 = RepresentativeSelector()
selector2.add("IMG_001", dummy_img, [], 30.0)
selector2.add("IMG_002", dummy_img, [], 80.0)  # 라플라시안 가장 높음
selector2.add("IMG_003", dummy_img, [], 50.0)

rep_img2, rep_id2 = selector2.select()
assert rep_img2 is not None, "FAIL: 탐지 없어도 이미지 선택돼야 함"
assert rep_id2 == "IMG_002", f"FAIL: 라플라시안 높은 이미지 선택 안됨 (got {rep_id2})"
print(f"  선택된 이미지: {rep_id2}")
print("  PASS")

print("=" * 50)
print("[3] 후보 없을 때 None 반환 확인")
selector3 = RepresentativeSelector()
rep_img3, rep_id3 = selector3.select()
assert rep_img3 is None, "FAIL: 후보 없으면 None이어야 함"
assert rep_id3 is None, "FAIL: 후보 없으면 None이어야 함"
print("  PASS")

print("=" * 50)
print("[4] rep_sent 플래그 - 성공 시에만 True 확인")
img_q = queue.Queue(maxsize=3)
rep_sent = False

# 성공 케이스
selector4 = RepresentativeSelector()
selector4.add("IMG_001", dummy_img, [], 50.0)
rep_img4, rep_id4 = selector4.select()
if rep_img4 is not None:
    try:
        img_q.put_nowait(("representative", 1, rep_img4))
        rep_sent = True  # 성공 시에만
    except Exception:
        pass

assert rep_sent == True, "FAIL: 성공 시 rep_sent가 True여야 함"
print("  성공 시 rep_sent=True PASS")

# 실패 케이스 (큐 가득 참)
img_q2 = queue.Queue(maxsize=1)
img_q2.put_nowait(("dummy", 0, dummy_img))  # 큐 꽉 채움
rep_sent2 = False
selector5 = RepresentativeSelector()
selector5.add("IMG_001", dummy_img, [], 50.0)
rep_img5, _ = selector5.select()
if rep_img5 is not None:
    try:
        img_q2.put_nowait(("representative", 1, rep_img5))
        rep_sent2 = True
    except Exception:
        pass  # 큐 실패 시 rep_sent2 유지

assert rep_sent2 == False, "FAIL: 큐 실패 시 rep_sent가 False여야 함"
print("  큐 실패 시 rep_sent=False PASS")

print("=" * 50)
print("[5] 청크 큐 적재 확인")
from image_chunker import prepare_chunks
tx_q = queue.PriorityQueue()
seq = SeqCounter()

from PIL import Image
import io
buf = io.BytesIO()
Image.fromarray(dummy_img).save(buf, format="JPEG")
chunks = prepare_chunks(buf.getvalue(), 1)
for chunk_payload in chunks:
    enqueue(tx_q, PacketType.IMG, chunk_payload, seq, 200)

assert not tx_q.empty(), "FAIL: 청크가 TX 큐에 없음"
print(f"  {len(chunks)}개 청크 TX 큐 적재 PASS")

print("=" * 50)
print("All tests passed.")