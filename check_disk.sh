#!/usr/bin/env bash
# data/ 저장 경로가 있는 파티션(SD카드)의 여유 용량을 확인한다.
# CANSAT 저장소 루트에서 실행할 것.

WARN_THRESHOLD_GB=2

LINE=$(df -h --output=avail,pcent,target . | tail -n 1)
AVAIL=$(echo "$LINE" | awk '{print $1}')
PCENT=$(echo "$LINE" | awk '{print $2}')
MOUNT=$(echo "$LINE" | awk '{print $3}')

AVAIL_GB=$(df --output=avail -BG . | tail -n 1 | tr -dc '0-9')

echo "mount: $MOUNT"
echo "avail: $AVAIL (used $PCENT)"

if [ "$AVAIL_GB" -lt "$WARN_THRESHOLD_GB" ]; then
    echo "WARNING: 여유 공간이 ${WARN_THRESHOLD_GB}GB 미만입니다 — 발사 전 데이터 정리 필요" >&2
    exit 1
fi
