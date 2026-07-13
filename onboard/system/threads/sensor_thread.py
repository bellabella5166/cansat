# onboard/system/threads/sensor_thread.py

from __future__ import annotations

import logging
import queue
import time

from protocol  import PacketType
from telemetry import SensorData

from onboard.input.sensor                 import Sensor
from onboard.input.id_manager             import IDManager
from onboard.preprocess.sensor_preprocess import SensorPreprocess
from onboard.preprocess.sensor_logger     import SensorLogger

logger = logging.getLogger("onboard.sensor")


def sensor_loop(sensor: Sensor, preprocess: SensorPreprocess,
                sensor_logger: SensorLogger, tx_q: queue.PriorityQueue,
                seq, id_mgr: IDManager, sensor_q: queue.Queue,
                running: list, enqueue_fn) -> None:

    interval  = 0.1  # 10 Hz
    next_time = time.monotonic()
    logger.info("Sensor loop started (10 Hz)")

    while running[0]:
        now = time.monotonic()
        if now < next_time:
            time.sleep(next_time - now)
        next_time += interval

        try:
            sid     = id_mgr.get_sensor_id()
            raw, ts = sensor.read(sid)
            if raw is None:
                continue

            processed = preprocess.process(raw, ts)
            if processed is None:
                continue

            sensor_logger.log(processed)

            sd = SensorData(
                timestamp     = processed.get("timestamp",    0.0),
                latitude      = processed.get("lat",          0.0),
                longitude     = processed.get("lon",          0.0),
                gps_altitude  = processed.get("gps_altitude", 0.0),
                baro_altitude = processed.get("baro_altitude",0.0),
                temperature   = processed.get("temp",         0.0),
                pressure      = processed.get("pressure",     0.0),
                roll          = processed.get("roll",         0.0),
                pitch         = processed.get("pitch",        0.0),
                yaw           = processed.get("yaw",          0.0),
                accel_x       = processed.get("accel_x",      0.0),
                accel_y       = processed.get("accel_y",      0.0),
                accel_z       = processed.get("accel_z",      0.0),
                gyro_x        = processed.get("gyro_x",       0.0),
                gyro_y        = processed.get("gyro_y",       0.0),
                gyro_z        = processed.get("gyro_z",       0.0),
                satellites    = int(processed.get("satellites",   0)),
                fix_quality   = int(processed.get("fix_quality",  0)),
                hdop          = float(processed.get("hdop",       0.0)),
            )
            enqueue_fn(tx_q, PacketType.SENSOR, sd.to_bytes(), seq, 20)

            try:
                sensor_q.put_nowait(processed)
            except Exception:
                pass

        except Exception as e:
            logger.error("Sensor loop error: %s", e)

    logger.info("Sensor loop stopped")