"""FastAPI control service for Dobot running on RevPi.

Run from this folder with:
    uvicorn control_api:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
import json
import re
import sqlite3
import threading

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import dobot_driver

app = FastAPI(title="RevPi Dobot Control API")
_DEVICE_LOCK = threading.Lock()
_DB_NAME = "/home/pi/kodeintegrasi/data/tangram.db"
_DB_LOG_NAME = "/home/pi/kodeintegrasi/data/tangram_logs.db"
_DB_LOG_TIMEOUT_SECONDS = 1.0
_PIECE_TO_BLOCK = {
    "segitiga_besar_1": "BT1",
    "segitiga_besar_2": "BT2",
    "segitiga_sedang_1": "MT",
    "persegi_1": "SQ",
    "segitiga_kecil_1": "ST1",
    "segitiga_kecil_2": "ST2",
    "jajar_genjang_1": "PL",
}


class ConnectRequest(BaseModel):
    port: str = dobot_driver.DEFAULT_PORT


class CalibrateMarkerRequest(BaseModel):
    marker_id: int
    label: Optional[str] = None
    world_x_mm: Optional[float] = None
    world_y_mm: Optional[float] = None


class CalibrateOriginRequest(BaseModel):
    marker_id: int = dobot_driver.REFERENCE_MARKER_ID
    label: str = dobot_driver.REFERENCE_MARKER_LABEL


class CalibrateReferenceRequest(BaseModel):
    marker_id: int = dobot_driver.SECONDARY_REFERENCE_MARKER_ID
    label: str = dobot_driver.SECONDARY_REFERENCE_MARKER_LABEL


class CartesianMoveRequest(BaseModel):
    x_mm: float
    y_mm: float
    z_mm: float
    r_deg: float = 0.0
    suck: float = 0.0
    safe_z_mm: Optional[float] = None


class SuckRequest(BaseModel):
    enabled: bool


class ExecutePlanRequest(BaseModel):
    coordinate_frame: Optional[Dict[str, Any]] = None
    move_plan: Optional[List[Dict[str, Any]]] = None
    moves: Optional[List[Dict[str, Any]]] = None


class MonitorRecordRequest(BaseModel):
    generated_at: Optional[str] = None
    pieces: List[Dict[str, Any]] = []


def _connected_or_503() -> None:
    if not dobot_driver.is_connected():
        raise HTTPException(status_code=503, detail={"error": "dobot_not_connected"})


def _raise_from_driver_error(exc: Exception) -> None:
    message = str(exc)
    if isinstance(exc, RuntimeError):
        raise HTTPException(status_code=409, detail={"error": "runtime_error", "reason": message}) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": message}) from exc
    raise HTTPException(status_code=500, detail={"error": "unexpected_driver_error", "reason": message}) from exc


def _resolve_plan_and_mode(payload: ExecutePlanRequest) -> Tuple[List[Dict[str, Any]], bool, Dict[str, Any]]:
    move_plan = payload.move_plan if payload.move_plan is not None else payload.moves
    if not move_plan:
        raise HTTPException(status_code=400, detail={"error": "move_plan_empty"})

    coordinate_frame = payload.coordinate_frame or {
        "type": "relative_to_apriltag",
        "marker_id": dobot_driver.REFERENCE_MARKER_ID,
    }
    frame_type = str(coordinate_frame.get("type", "relative_to_apriltag")).strip().lower()
    use_relative_coordinates = frame_type not in {"absolute", "absolute_dobot_mm"}

    if use_relative_coordinates:
        origin = dobot_driver.get_origin_calibration()
        if origin is None:
            raise HTTPException(status_code=409, detail={"error": "origin_not_calibrated"})
        frame_calibration = dobot_driver.get_frame_calibration()
        if frame_calibration is None:
            raise HTTPException(status_code=409, detail={"error": "frame_transform_not_ready"})
        marker_id = int(coordinate_frame.get("marker_id", dobot_driver.REFERENCE_MARKER_ID))
        if int(origin["marker_id"]) != marker_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "origin_marker_mismatch",
                    "requested_marker_id": marker_id,
                    "current_marker_id": int(origin["marker_id"]),
                },
            )

    return move_plan, use_relative_coordinates, coordinate_frame


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "service": "revpi-dobot-control",
        "ok": True,
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    with _DEVICE_LOCK:
        return {
            "ok": True,
            "status": dobot_driver.get_runtime_status(),
        }


@app.get("/calibration")
def calibration_status() -> Dict[str, Any]:
    with _DEVICE_LOCK:
        return {
            "ok": True,
            "markers": dobot_driver.get_all_marker_calibrations(),
            "origin": dobot_driver.get_origin_calibration(),
            "reference": dobot_driver.get_reference_calibration(),
            "frame_calibration": dobot_driver.get_frame_calibration(),
        }


@app.post("/connect")
def connect(request: ConnectRequest) -> Dict[str, Any]:
    with _DEVICE_LOCK:
        ok = dobot_driver.connect(port=request.port)
        if not ok:
            raise HTTPException(status_code=503, detail={"error": "connect_failed", "port": request.port})
        return {
            "ok": True,
            "status": dobot_driver.get_runtime_status(),
        }


@app.post("/disconnect")
def disconnect() -> Dict[str, Any]:
    with _DEVICE_LOCK:
        dobot_driver.disconnect()
        return {
            "ok": True,
            "status": dobot_driver.get_runtime_status(),
        }


@app.post("/clear-alarms")
def clear_alarms() -> Dict[str, Any]:
    with _DEVICE_LOCK:
        _connected_or_503()
        ok = dobot_driver.clear_alarms()
        return {
            "ok": bool(ok),
            "status": dobot_driver.get_runtime_status(),
        }


@app.get("/pose")
def pose() -> Dict[str, Any]:
    with _DEVICE_LOCK:
        _connected_or_503()
        try:
            return {
                "ok": True,
                "pose": dobot_driver.get_current_pose_payload(),
            }
        except Exception as exc:
            _raise_from_driver_error(exc)


@app.get("/origin")
def origin() -> Dict[str, Any]:
    with _DEVICE_LOCK:
        return {
            "ok": True,
            "origin": dobot_driver.get_origin_calibration(),
        }


@app.get("/reference")
def reference() -> Dict[str, Any]:
    with _DEVICE_LOCK:
        return {
            "ok": True,
            "reference": dobot_driver.get_reference_calibration(),
        }


@app.get("/markers")
def markers() -> Dict[str, Any]:
    with _DEVICE_LOCK:
        return {
            "ok": True,
            "markers": dobot_driver.get_all_marker_calibrations(),
        }


@app.get("/monitor/live-tracking.js", include_in_schema=False)
def monitor_live_tracking_jsonp(callback: str = "renderVisionPieces") -> Response:
    if not re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", callback):
        raise HTTPException(status_code=400, detail={"error": "invalid_callback"})
    with sqlite3.connect(_DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute("""
            SELECT block_name, current_x, current_y, current_r, target_x, target_y, target_r, status
            FROM live_tracking
            ORDER BY block_name
        """)]
    body = json.dumps({"ok": True, "pieces": rows}, ensure_ascii=False)
    return Response(content=f"{callback}({body});", media_type="application/javascript")


@app.post("/monitor/record")
def monitor_record(request: MonitorRecordRequest) -> Dict[str, Any]:
    rows = []
    for piece in request.pieces:
        block_name = _PIECE_TO_BLOCK.get(str(piece.get("piece_id", "")))
        pose = piece.get("pose") if isinstance(piece.get("pose"), dict) else {}
        if not block_name or not pose:
            continue
        try:
            rows.append((float(pose["x_mm"]), float(pose["y_mm"]), float(pose.get("theta_deg", 0.0)), block_name))
        except (KeyError, TypeError, ValueError):
            continue

    if not rows:
        raise HTTPException(status_code=400, detail={"error": "no_recordable_pieces"})

    with sqlite3.connect(_DB_NAME) as conn:
        conn.executemany(
            """
            UPDATE live_tracking
            SET current_x = ?, current_y = ?, current_r = ?
            WHERE block_name = ?
            """,
            rows,
        )

    return {"ok": True, "recorded_count": len(rows), "generated_at": request.generated_at}


@app.post("/calibrate-marker")
def calibrate_marker(request: CalibrateMarkerRequest) -> Dict[str, Any]:
    with _DEVICE_LOCK:
        _connected_or_503()
        try:
            marker_payload = dobot_driver.calibrate_marker(
                marker_id=request.marker_id,
                label=request.label,
                world_x_mm=request.world_x_mm,
                world_y_mm=request.world_y_mm,
            )
            return {
                "ok": True,
                "marker": marker_payload,
                "frame_calibration": dobot_driver.get_frame_calibration(),
            }
        except Exception as exc:
            _raise_from_driver_error(exc)


@app.post("/calibrate-origin")
def calibrate_origin(request: CalibrateOriginRequest) -> Dict[str, Any]:
    with _DEVICE_LOCK:
        _connected_or_503()
        try:
            origin_payload = dobot_driver.calibrate_origin(marker_id=request.marker_id, label=request.label)
            return {
                "ok": True,
                "origin": origin_payload,
                "frame_calibration": dobot_driver.get_frame_calibration(),
            }
        except Exception as exc:
            _raise_from_driver_error(exc)


@app.post("/calibrate-reference")
def calibrate_reference(request: CalibrateReferenceRequest) -> Dict[str, Any]:
    with _DEVICE_LOCK:
        _connected_or_503()
        try:
            reference_payload = dobot_driver.calibrate_reference(marker_id=request.marker_id, label=request.label)
            return {
                "ok": True,
                "reference": reference_payload,
                "frame_calibration": dobot_driver.get_frame_calibration(),
            }
        except Exception as exc:
            _raise_from_driver_error(exc)


@app.delete("/origin")
def clear_origin() -> Dict[str, Any]:
    with _DEVICE_LOCK:
        dobot_driver.clear_origin_calibration()
        return {
            "ok": True,
            "origin": None,
            "reference": None,
            "frame_calibration": None,
        }


@app.delete("/calibration")
def clear_calibration() -> Dict[str, Any]:
    with _DEVICE_LOCK:
        dobot_driver.clear_origin_calibration()
        return {
            "ok": True,
            "markers": [],
            "frame_calibration": None,
        }


@app.post("/move-absolute")
def move_absolute(request: CartesianMoveRequest) -> Dict[str, Any]:
    with _DEVICE_LOCK:
        _connected_or_503()
        try:
            ok = dobot_driver.move_to_absolute(
                request.x_mm,
                request.y_mm,
                request.z_mm,
                target_r=request.r_deg,
                suck_val=request.suck,
                safe_z=request.safe_z_mm,
            )
            if not ok:
                raise HTTPException(status_code=409, detail={"error": "move_failed"})
            return {
                "ok": True,
                "pose": dobot_driver.get_current_pose_payload(),
            }
        except HTTPException:
            raise
        except Exception as exc:
            _raise_from_driver_error(exc)


@app.post("/move-relative")
def move_relative(request: CartesianMoveRequest) -> Dict[str, Any]:
    with _DEVICE_LOCK:
        _connected_or_503()
        try:
            ok = dobot_driver.move_to_relative(
                request.x_mm,
                request.y_mm,
                request.z_mm,
                target_r=request.r_deg,
                suck_val=request.suck,
                safe_z=request.safe_z_mm,
            )
            if not ok:
                raise HTTPException(status_code=409, detail={"error": "move_failed"})
            return {
                "ok": True,
                "pose": dobot_driver.get_current_pose_payload(),
                "frame_calibration": dobot_driver.get_frame_calibration(),
            }
        except HTTPException:
            raise
        except Exception as exc:
            _raise_from_driver_error(exc)


@app.post("/suction")
def set_suction(request: SuckRequest) -> Dict[str, Any]:
    with _DEVICE_LOCK:
        _connected_or_503()
        try:
            dobot_driver.set_suction(bool(request.enabled))
            return {
                "ok": True,
                "suction_enabled": bool(request.enabled),
            }
        except Exception as exc:
            _raise_from_driver_error(exc)


@app.post("/execute-plan")
def execute_plan(request: ExecutePlanRequest) -> Dict[str, Any]:
    with _DEVICE_LOCK:
        _connected_or_503()
        move_plan, use_relative_coordinates, coordinate_frame = _resolve_plan_and_mode(request)
        try:
            results = dobot_driver.execute_move_plan(
                move_plan,
                use_relative_coordinates=use_relative_coordinates,
            )
            return {
                "ok": True,
                "executed_count": len(results),
                "coordinate_frame": coordinate_frame,
                "frame_calibration": dobot_driver.get_frame_calibration(),
                "results": results,
            }
        except Exception as exc:
            _raise_from_driver_error(exc)


@app.get("/api/logs")
def get_logs() -> Dict[str, Any]:
    result = {"hmi_logs": [], "system_logs": [], "production_logs": []}
    try:
        with sqlite3.connect(_DB_LOG_NAME, timeout=_DB_LOG_TIMEOUT_SECONDS) as conn:
            conn.execute("PRAGMA busy_timeout = 1000")
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT id, timestamp, operator_id, action FROM hmi_user_logs ORDER BY id DESC LIMIT 200")
            result["hmi_logs"] = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT id, timestamp, event_type, component, message FROM system_event_logs ORDER BY id DESC LIMIT 200")
            result["system_logs"] = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT id, shape_name, start_time, end_time, duration_sec, status FROM production_metrics ORDER BY id DESC LIMIT 200")
            result["production_logs"] = [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": "log_query_failed", "reason": str(exc)})
    return result
