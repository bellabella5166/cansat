"""
shared/telemetry.py
===================
센서 데이터 / YOLO 탐지 결과의 dataclass 및 바이너리 직렬화.
온보드·지상국 양쪽에서 동일하게 사용한다.

바이너리 포맷 (little-endian):

  SensorData (62 bytes):
    timestamp    : double  (8)   Unix epoch
    latitude     : double  (8)   도(°)
    longitude    : double  (8)   도(°)
    gps_altitude : float   (4)   m
    baro_altitude: float   (4)   m
    temperature  : float   (4)   °C
    pressure     : float   (4)   hPa
    roll         : float   (4)   °
    pitch        : float   (4)   °
    yaw          : float   (4)   °
    accel_x      : float   (4)   m/s²
    accel_y      : float   (4)   m/s²
    accel_z      : float   (4)   m/s²
    gyro_x       : float   (4)   °/s
    gyro_y       : float   (4)   °/s
    gyro_z       : float   (4)   °/s
    satellites   : uint8   (1)
    fix_quality  : uint8   (1)
    hdop         : float   (4)
    total:  82 bytes

  YoloDetection (25 bytes):
    timestamp    : double  (8)
    image_id     : uint16  (2)
    object_id    : uint16  (2)
    class_id     : uint8   (1)   CLASS_NAMES 참조
    confidence   : float   (4)
    x_min        : uint16  (2)   640×640 기준 픽셀
    y_min        : uint16  (2)
    x_max        : uint16  (2)
    y_max        : uint16  (2)
    total: 25 bytes

  NACK payload:
    image_id     : uint16  (2)
    count        : uint16  (2)
    chunk_ids    : uint16 × count

클래스 이름 (임무제안서 §4.1.3):
  0: farmland  – 농경지
  1: building  – 건물/시설
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

ENDIAN = "<"

# ── 토지피복 클래스 이름 ──────────────────────────────────────────────────────
# ★ 실제 YOLOv8n 모델 학습 시 labels.yaml 의 순서와 반드시 일치시킬 것
CLASS_NAMES: dict[int, str] = {
    0: "farm",   # 농경지
    1: "building",   # 건물/시설
}
CLASS_COLORS: dict[int, str] = {
    0: "#4CAF50",   # 녹색 – 농경지
    1: "#FF5722",   # 주황 – 건물/시설
}

# ── SensorData ────────────────────────────────────────────────────────────────
# 포맷: 3d + 13f + 2B + 1f  = 3×8 + 13×4 + 2×1 + 4 = 24+52+2+4 = 82 bytes
# (accel 3개 + gyro 3개 추가 → 임무제안서 §4.1.1 IMU 데이터 포함)
_SENSOR_FMT  = f"{ENDIAN}dddfffffffffffffBBf"
_SENSOR_STRUCT = struct.Struct(_SENSOR_FMT)
SENSOR_PAYLOAD_SIZE: int = _SENSOR_STRUCT.size  # 실행 시 출력해서 확인 가능


@dataclass
class SensorData:
    timestamp:     float = 0.0
    latitude:      float = 0.0
    longitude:     float = 0.0
    gps_altitude:  float = 0.0
    baro_altitude: float = 0.0
    temperature:   float = 0.0
    pressure:      float = 0.0
    roll:          float = 0.0
    pitch:         float = 0.0
    yaw:           float = 0.0
    accel_x:       float = 0.0
    accel_y:       float = 0.0
    accel_z:       float = 0.0
    gyro_x:        float = 0.0
    gyro_y:        float = 0.0
    gyro_z:        float = 0.0
    satellites:    int   = 0
    fix_quality:   int   = 0
    hdop:          float = 0.0

    def to_bytes(self) -> bytes:
        return _SENSOR_STRUCT.pack(
            self.timestamp, self.latitude, self.longitude,
            self.gps_altitude, self.baro_altitude,
            self.temperature, self.pressure,
            self.roll, self.pitch, self.yaw,
            self.accel_x, self.accel_y, self.accel_z,
            self.gyro_x, self.gyro_y, self.gyro_z,
            self.satellites, self.fix_quality,
            self.hdop,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "SensorData":
        if len(data) < _SENSOR_STRUCT.size:
            raise ValueError(
                f"SensorData: {_SENSOR_STRUCT.size} bytes 필요, {len(data)} 수신"
            )
        v = _SENSOR_STRUCT.unpack_from(data)
        return cls(
            timestamp=v[0],  latitude=v[1],    longitude=v[2],
            gps_altitude=v[3], baro_altitude=v[4],
            temperature=v[5],  pressure=v[6],
            roll=v[7],   pitch=v[8],   yaw=v[9],
            accel_x=v[10], accel_y=v[11], accel_z=v[12],
            gyro_x=v[13],  gyro_y=v[14],  gyro_z=v[15],
            satellites=v[16], fix_quality=v[17], hdop=v[18],
        )

    @staticmethod
    def csv_header() -> list[str]:
        return [
            "timestamp", "latitude", "longitude",
            "gps_altitude", "baro_altitude",
            "temperature", "pressure",
            "roll", "pitch", "yaw",
            "accel_x", "accel_y", "accel_z",
            "gyro_x", "gyro_y", "gyro_z",
            "satellites", "fix_quality", "hdop",
        ]

    def to_csv_row(self) -> list:
        return [
            self.timestamp, self.latitude, self.longitude,
            self.gps_altitude, self.baro_altitude,
            self.temperature, self.pressure,
            self.roll, self.pitch, self.yaw,
            self.accel_x, self.accel_y, self.accel_z,
            self.gyro_x, self.gyro_y, self.gyro_z,
            self.satellites, self.fix_quality, self.hdop,
        ]


# ── YoloDetection ─────────────────────────────────────────────────────────────
# 포맷: d H H B f H H H H = 8+2+2+1+4+2+2+2+2 = 25 bytes
_YOLO_FMT    = f"{ENDIAN}dHHBfHHHH"
_YOLO_STRUCT = struct.Struct(_YOLO_FMT)
YOLO_PAYLOAD_SIZE: int = _YOLO_STRUCT.size


@dataclass
class YoloDetection:
    timestamp:  float = 0.0
    image_id:   int   = 0
    object_id:  int   = 0
    class_id:   int   = 0
    confidence: float = 0.0
    x_min:      int   = 0
    y_min:      int   = 0
    x_max:      int   = 0
    y_max:      int   = 0

    @property
    def detected_class(self) -> str:
        return CLASS_NAMES.get(self.class_id, f"class_{self.class_id}")

    @property
    def color(self) -> str:
        return CLASS_COLORS.get(self.class_id, "#9E9E9E")

    def to_bytes(self) -> bytes:
        return _YOLO_STRUCT.pack(
            self.timestamp, self.image_id, self.object_id,
            self.class_id, self.confidence,
            self.x_min, self.y_min, self.x_max, self.y_max,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "YoloDetection":
        if len(data) < _YOLO_STRUCT.size:
            raise ValueError(
                f"YoloDetection: {_YOLO_STRUCT.size} bytes need, {len(data)} receive"
            )
        v = _YOLO_STRUCT.unpack_from(data)
        return cls(
            timestamp=v[0], image_id=v[1], object_id=v[2],
            class_id=v[3], confidence=v[4],
            x_min=v[5], y_min=v[6], x_max=v[7], y_max=v[8],
        )

    @staticmethod
    def csv_header() -> list[str]:
        return [
            "timestamp", "image_id", "object_id",
            "detected_class", "confidence",
            "x_min", "y_min", "x_max", "y_max",
        ]

    def to_csv_row(self) -> list:
        return [
            self.timestamp, self.image_id, self.object_id,
            self.detected_class, self.confidence,
            self.x_min, self.y_min, self.x_max, self.y_max,
        ]

# ── ACK / NACK 위에 추가 ──────────────────────────────────────────────────────
# Communication power telemetry
# Format: d f f f f I I = 8+4+4+4+4+4+4 = 32 bytes
_POWER_FMT = f"{ENDIAN}dffffII"
_POWER_STRUCT = struct.Struct(_POWER_FMT)
POWER_PAYLOAD_SIZE: int = _POWER_STRUCT.size


@dataclass
class CommPowerData:
    timestamp: float = 0.0
    voltage_v: float = 0.0
    current_ma: float = 0.0
    duration_s: float = 0.0
    energy_mwh: float = 0.0
    bytes_sent: int = 0
    packets_sent: int = 0

    def to_bytes(self) -> bytes:
        return _POWER_STRUCT.pack(
            self.timestamp,
            self.voltage_v,
            self.current_ma,
            self.duration_s,
            self.energy_mwh,
            self.bytes_sent & 0xFFFFFFFF,
            self.packets_sent & 0xFFFFFFFF,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "CommPowerData":
        if len(data) < _POWER_STRUCT.size:
            raise ValueError(
                f"CommPowerData: {_POWER_STRUCT.size} bytes need, {len(data)} receive"
            )
        v = _POWER_STRUCT.unpack_from(data)
        return cls(
            timestamp=v[0],
            voltage_v=v[1],
            current_ma=v[2],
            duration_s=v[3],
            energy_mwh=v[4],
            bytes_sent=v[5],
            packets_sent=v[6],
        )

    @staticmethod
    def csv_header() -> list[str]:
        return [
            "timestamp", "voltage_v", "current_ma", "duration_s",
            "energy_mwh", "bytes_sent", "packets_sent",
        ]

    def to_csv_row(self) -> list:
        return [
            self.timestamp, self.voltage_v, self.current_ma, self.duration_s,
            self.energy_mwh, self.bytes_sent, self.packets_sent,
        ]

# ── ACK / NACK ────────────────────────────────────────────────────────────────
_NACK_HDR = struct.Struct(f"{ENDIAN}HH")  # image_id, count

def encode_nack(image_id: int, missing: list[int]) -> bytes:
    return _NACK_HDR.pack(image_id, len(missing)) + struct.pack(
        f"{ENDIAN}" + "H" * len(missing), *missing
    )

def decode_nack(data: bytes) -> tuple[int, list[int]]:
    image_id, count = _NACK_HDR.unpack_from(data)
    chunk_ids = list(struct.unpack_from(f"{ENDIAN}" + "H" * count, data, _NACK_HDR.size))
    return image_id, chunk_ids
