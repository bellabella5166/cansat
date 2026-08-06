#!/usr/bin/env bash
# 실제 비행 Pi에서 실행: GPS UART(disable-bt) 설정과 시스템 시각 동기화 상태를 확인한다.

echo "=== 1) disable-bt 오버레이 확인 ==="
CONFIG_TXT=""
for f in /boot/firmware/config.txt /boot/config.txt; do
    [ -f "$f" ] && CONFIG_TXT="$f" && break
done

if [ -z "$CONFIG_TXT" ]; then
    echo "WARNING: config.txt를 찾을 수 없습니다" >&2
else
    if grep -Eq '^\s*dtoverlay=disable-bt' "$CONFIG_TXT"; then
        echo "OK: $CONFIG_TXT 에 dtoverlay=disable-bt 적용됨"
    else
        echo "WARNING: $CONFIG_TXT 에 dtoverlay=disable-bt 없음 — GPS가 미니 UART(ttyS0)를 쓰게 됨" >&2
    fi
fi

echo
echo "=== 2) hciuart 서비스 확인 ==="
HCIUART_STATE=$(systemctl is-enabled hciuart 2>/dev/null)
if [ "$HCIUART_STATE" = "disabled" ] || [ "$HCIUART_STATE" = "masked" ]; then
    echo "OK: hciuart $HCIUART_STATE"
else
    echo "WARNING: hciuart 상태 = ${HCIUART_STATE:-확인불가} — disabled/masked 이어야 함" >&2
fi

echo
echo "=== 3) /dev/serial0 실제 매핑 확인 ==="
if [ -L /dev/serial0 ]; then
    REAL=$(readlink -f /dev/serial0)
    echo "/dev/serial0 -> $REAL"
    case "$REAL" in
        */ttyAMA0) echo "OK: 하드웨어 UART(ttyAMA0)로 매핑됨 (GPS용으로 정상)" ;;
        */ttyS0)   echo "WARNING: 미니 UART(ttyS0)로 매핑됨 — CPU 부하에 따라 GPS 값 깨질 수 있음" >&2 ;;
        *)         echo "WARNING: 알 수 없는 대상 — 수동 확인 필요" >&2 ;;
    esac
else
    echo "WARNING: /dev/serial0 심볼릭 링크가 없습니다" >&2
fi

echo
echo "=== 4) 시스템 시각 동기화 확인 ==="
date
timedatectl status 2>/dev/null | grep -E "System clock synchronized|NTP service|Time zone"
