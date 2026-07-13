"""Shared Dobot control helpers for RevPi runtime."""



from __future__ import annotations



from typing import Any

from typing import Dict

from typing import List

from typing import Optional

from typing import Tuple

from typing import Union

import math

import time



from pydobot import Dobot

from pydobot.enums import PTPMode

from pydobot.message import Message



DEFAULT_PORT = "/dev/ttyUSB2"



REFERENCE_MARKER_ID = 1

REFERENCE_MARKER_LABEL = "apriltag_1"

SECONDARY_REFERENCE_MARKER_ID = 0

SECONDARY_REFERENCE_MARKER_LABEL = "apriltag_0"



# Nominal marker centers in the same world frame used by the laptop AprilTag calibration.

MARKER_WORLD_POSITIONS_MM = {

    0: (135.3, -292.4),

    1: (179.3, -1.2),

    2: (227.4, -306.0),

    3: (271.4, -14.8),

}



X_LIMIT = (-30.0, 300.0)

Y_LIMIT = (-300.0, 300.0)

Z_LIMIT = (-30.0, 170.0)



DEFAULT_SAFE_Z = 20.0

DEFAULT_SPEED_XY = 220.0

DEFAULT_SPEED_Z = 150.0

POSE_REFRESH_DELAY_S = 0.3

SUCTION_SETTLE_DELAY_S = 1.0

VECTOR_EPSILON_MM = 1e-6



device: Optional[Dobot] = None

_marker_calibrations: Dict[int, Dict[str, Any]] = {}

_frame_calibration: Optional[Dict[str, Any]] = None





def _copy_pose_payload(pose: Dict[str, Any]) -> Dict[str, float]:

    return {

        "x_mm": float(pose["x_mm"]),

        "y_mm": float(pose["y_mm"]),

        "z_mm": float(pose["z_mm"]),

        "r_deg": float(pose["r_deg"]),

    }





def _copy_marker_payload(marker: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:

    if marker is None:

        return None

    return {

        "marker_id": int(marker["marker_id"]),

        "label": str(marker["label"]),

        "calibrated_at_epoch": float(marker["calibrated_at_epoch"]),

        "world": {

            "x_mm": float(marker["world"]["x_mm"]),

            "y_mm": float(marker["world"]["y_mm"]),

        },

        "pose": _copy_pose_payload(marker["pose"]),

    }





def _copy_frame_payload(frame: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:

    if frame is None:

        return None

    return {

        "ready": bool(frame["ready"]),

        "origin_marker_id": int(frame["origin_marker_id"]),

        "reference_marker_id": int(frame["reference_marker_id"]),

        "rotation_deg": float(frame["rotation_deg"]),

        "scale_xy": float(frame["scale_xy"]),

        "origin_world": {

            "x_mm": float(frame["origin_world"]["x_mm"]),

            "y_mm": float(frame["origin_world"]["y_mm"]),

        },

        "reference_world": {

            "x_mm": float(frame["reference_world"]["x_mm"]),

            "y_mm": float(frame["reference_world"]["y_mm"]),

        },

        "origin_pose": _copy_pose_payload(frame["origin_pose"]),

        "reference_pose": _copy_pose_payload(frame["reference_pose"]),

    }





def _require_device() -> Dobot:

    if device is None:

        raise RuntimeError("Dobot is not connected")

    return device





def _safe_error_message(x: float, y: float, z: float) -> str:

    if not (X_LIMIT[0] <= x <= X_LIMIT[1]):

        return f"X diluar batas {X_LIMIT}"

    if not (Y_LIMIT[0] <= y <= Y_LIMIT[1]):

        return f"Y diluar batas {Y_LIMIT}"

    if not (Z_LIMIT[0] <= z <= Z_LIMIT[1]):

        return f"Z diluar batas {Z_LIMIT}"

    return ""





def _marker_label(marker_id: int) -> str:

    return f"apriltag_{int(marker_id)}"





def _world_point_for_marker(

    marker_id: int,

    world_x_mm: Optional[float] = None,

    world_y_mm: Optional[float] = None,

) -> Tuple[float, float]:

    if world_x_mm is not None and world_y_mm is not None:

        return float(world_x_mm), float(world_y_mm)



    point = MARKER_WORLD_POSITIONS_MM.get(int(marker_id))

    if point is None:

        raise ValueError(f"Marker ID {marker_id} belum punya world coordinate bawaan")

    return float(point[0]), float(point[1])





def _vector_from_points(start_xy: Tuple[float, float], end_xy: Tuple[float, float]) -> Tuple[float, float]:

    return float(end_xy[0] - start_xy[0]), float(end_xy[1] - start_xy[1])





def _vector_norm(x_mm: float, y_mm: float) -> float:

    return float(math.hypot(float(x_mm), float(y_mm)))





def _vector_angle_rad(x_mm: float, y_mm: float) -> float:

    return float(math.atan2(float(y_mm), float(x_mm)))





def _rebuild_frame_calibration() -> None:

    global _frame_calibration



    origin = _marker_calibrations.get(REFERENCE_MARKER_ID)

    reference = _marker_calibrations.get(SECONDARY_REFERENCE_MARKER_ID)

    if origin is None or reference is None:

        _frame_calibration = None

        return



    world_vector = _vector_from_points(

        (float(origin["world"]["x_mm"]), float(origin["world"]["y_mm"])),

        (float(reference["world"]["x_mm"]), float(reference["world"]["y_mm"])),

    )

    dobot_vector = _vector_from_points(

        (float(origin["pose"]["x_mm"]), float(origin["pose"]["y_mm"])),

        (float(reference["pose"]["x_mm"]), float(reference["pose"]["y_mm"])),

    )



    world_norm = _vector_norm(world_vector[0], world_vector[1])

    dobot_norm = _vector_norm(dobot_vector[0], dobot_vector[1])

    if world_norm <= VECTOR_EPSILON_MM or dobot_norm <= VECTOR_EPSILON_MM:

        raise ValueError("Kalibrasi 2 titik gagal: jarak antar marker terlalu kecil")



    rotation_rad = _vector_angle_rad(dobot_vector[0], dobot_vector[1]) - _vector_angle_rad(world_vector[0], world_vector[1])

    rotation_deg = math.degrees(rotation_rad)

    scale_xy = dobot_norm / world_norm



    _frame_calibration = {

        "ready": True,

        "origin_marker_id": int(origin["marker_id"]),

        "reference_marker_id": int(reference["marker_id"]),

        "rotation_deg": float(rotation_deg),

        "scale_xy": float(scale_xy),

        "origin_world": {

            "x_mm": float(origin["world"]["x_mm"]),

            "y_mm": float(origin["world"]["y_mm"]),

        },

        "reference_world": {

            "x_mm": float(reference["world"]["x_mm"]),

            "y_mm": float(reference["world"]["y_mm"]),

        },

        "origin_pose": _copy_pose_payload(origin["pose"]),

        "reference_pose": _copy_pose_payload(reference["pose"]),

    }





def is_connected() -> bool:

    return device is not None





def connect(port: str = DEFAULT_PORT) -> bool:

    """Open serial connection to Dobot and prepare it for commands."""

    global device



    if device is not None:

        return True



    try:

        device = Dobot(port=port, verbose=False)

        print(">>> Membuka Koneksi Serial Dobot...")

        time.sleep(1.0)

        clear_alarms()

        _require_device().speed(float(DEFAULT_SPEED_XY), float(DEFAULT_SPEED_Z))

        time.sleep(1.0)

        print(">>> Koneksi Berhasil & Dobot Siap Menerima Perintah!")

        return True

    except Exception as exc:

        device = None

        print(f"!!! Gagal koneksi Dobot: {exc}")

        return False





def disconnect() -> None:

    """Close Dobot connection and clear runtime calibration."""

    global device



    if device is None:

        clear_origin_calibration()

        return



    try:

        device.suck(False)

    except Exception:

        pass



    try:

        device.close()

    finally:

        device = None

        clear_origin_calibration()

        print(">>> Koneksi Serial Dobot Ditutup.")





def clear_alarms() -> bool:

    """Clear Dobot alarm state if the device is connected."""

    try:

        controller = _require_device()

    except RuntimeError:

        return False



    msg = Message()

    msg.id = 20

    msg.ctrl = 0x01

    controller._send_command(msg)

    return True





def set_suction(enabled: bool) -> None:

    """Set suction state without moving the robot."""

    controller = _require_device()

    controller.suck(bool(enabled))





def get_current_pose() -> Tuple[float, float, float, float]:

    """Read the latest robot pose with one refresh request first."""

    controller = _require_device()

    controller.pose()

    time.sleep(POSE_REFRESH_DELAY_S)

    pose = controller.pose()

    if pose is None:

        raise RuntimeError("Gagal mengambil data pose Dobot")

    return float(pose[0]), float(pose[1]), float(pose[2]), float(pose[3])





def get_current_pose_payload() -> Dict[str, float]:

    x_mm, y_mm, z_mm, r_deg = get_current_pose()

    return {

        "x_mm": x_mm,

        "y_mm": y_mm,

        "z_mm": z_mm,

        "r_deg": r_deg,

    }





def get_marker_calibration(marker_id: int) -> Optional[Dict[str, Any]]:

    return _copy_marker_payload(_marker_calibrations.get(int(marker_id)))





def get_origin_calibration() -> Optional[Dict[str, Any]]:

    return get_marker_calibration(REFERENCE_MARKER_ID)





def get_reference_calibration() -> Optional[Dict[str, Any]]:

    return get_marker_calibration(SECONDARY_REFERENCE_MARKER_ID)





def get_all_marker_calibrations() -> List[Dict[str, Any]]:

    payload: List[Dict[str, Any]] = []

    for marker_id in sorted(_marker_calibrations.keys()):

        marker_payload = get_marker_calibration(marker_id)

        if marker_payload is not None:

            payload.append(marker_payload)

    return payload





def get_frame_calibration() -> Optional[Dict[str, Any]]:

    return _copy_frame_payload(_frame_calibration)





def clear_origin_calibration() -> None:

    """Clear all marker/frame calibration state."""

    global _frame_calibration

    _marker_calibrations.clear()

    _frame_calibration = None





def calibrate_marker(

    marker_id: int,

    label: Optional[str] = None,

    world_x_mm: Optional[float] = None,

    world_y_mm: Optional[float] = None,

) -> Dict[str, Any]:

    """Store the current Dobot pose for one known marker in the world frame."""

    marker_id = int(marker_id)

    world_point = _world_point_for_marker(marker_id, world_x_mm=world_x_mm, world_y_mm=world_y_mm)

    pose = get_current_pose_payload()

    _marker_calibrations[marker_id] = {

        "marker_id": marker_id,

        "label": str(label or _marker_label(marker_id)),

        "calibrated_at_epoch": time.time(),

        "world": {

            "x_mm": float(world_point[0]),

            "y_mm": float(world_point[1]),

        },

        "pose": pose,

    }

    _rebuild_frame_calibration()

    marker_payload = get_marker_calibration(marker_id)

    if marker_payload is None:

        raise RuntimeError("Gagal menyimpan marker calibration")

    return marker_payload





def calibrate_origin(

    marker_id: int = REFERENCE_MARKER_ID,

    label: str = REFERENCE_MARKER_LABEL,

) -> Dict[str, Any]:

    return calibrate_marker(marker_id=marker_id, label=label)





def calibrate_reference(

    marker_id: int = SECONDARY_REFERENCE_MARKER_ID,

    label: str = SECONDARY_REFERENCE_MARKER_LABEL,

) -> Dict[str, Any]:

    return calibrate_marker(marker_id=marker_id, label=label)





def get_runtime_status() -> Dict[str, Any]:

    """Return lightweight controller status for CLI/API responses."""

    status: Dict[str, Any] = {

        "connected": is_connected(),

        "origin_calibrated": get_origin_calibration() is not None,

        "reference_calibrated": get_reference_calibration() is not None,

        "frame_transform_ready": _frame_calibration is not None,

        "limits": {

            "x": [float(X_LIMIT[0]), float(X_LIMIT[1])],

            "y": [float(Y_LIMIT[0]), float(Y_LIMIT[1])],

            "z": [float(Z_LIMIT[0]), float(Z_LIMIT[1])],

        },

        "default_safe_z_mm": float(DEFAULT_SAFE_Z),

        "origin": get_origin_calibration(),

        "reference": get_reference_calibration(),

        "markers": get_all_marker_calibrations(),

        "frame_calibration": get_frame_calibration(),

    }

    if is_connected():

        try:

            status["pose"] = get_current_pose_payload()

        except RuntimeError as exc:

            status["pose_error"] = str(exc)

    return status





def is_safe(x: float, y: float, z: float) -> bool:

    return not _safe_error_message(float(x), float(y), float(z))





def get_safety_error(x: float, y: float, z: float) -> str:

    return _safe_error_message(float(x), float(y), float(z))





def validate_safe(x: float, y: float, z: float) -> None:

    error = get_safety_error(x, y, z)

    if error:

        raise ValueError(error)





def _resolve_world_relative_xy(rel_x_mm: float, rel_y_mm: float) -> Tuple[float, float]:

    frame = _frame_calibration

    origin = _marker_calibrations.get(REFERENCE_MARKER_ID)

    if origin is None:

        raise RuntimeError("Origin belum dikalibrasi")



    if frame is None:

        return float(rel_x_mm), float(rel_y_mm)



    rotation_rad = math.radians(float(frame["rotation_deg"]))

    scale_xy = float(frame["scale_xy"])

    cos_theta = math.cos(rotation_rad)

    sin_theta = math.sin(rotation_rad)



    dx = scale_xy * ((cos_theta * float(rel_x_mm)) - (sin_theta * float(rel_y_mm)))

    dy = scale_xy * ((sin_theta * float(rel_x_mm)) + (cos_theta * float(rel_y_mm)))

    return float(dx), float(dy)





def resolve_relative_pose(

    rel_x_mm: float,

    rel_y_mm: float,

    rel_z_mm: float,

    target_r_deg: float = 0.0,

) -> Tuple[float, float, float, float]:

    """Convert world-frame relative coordinates into Dobot coordinates."""

    origin = _marker_calibrations.get(REFERENCE_MARKER_ID)

    if origin is None:

        raise RuntimeError("Origin belum dikalibrasi")



    delta_x_mm, delta_y_mm = _resolve_world_relative_xy(rel_x_mm, rel_y_mm)

    pose = origin["pose"]

    return (

        float(pose["x_mm"]) + float(delta_x_mm),

        float(pose["y_mm"]) + float(delta_y_mm),

        float(pose["z_mm"]) + float(rel_z_mm),

        float(target_r_deg),

    )





def _normalize_suck_value(suck_val: Union[float, bool, int]) -> bool:

    return bool(float(suck_val))





def move_to_absolute(

    target_x: float,

    target_y: float,

    target_z: float,

    target_r: float = 0.0,

    suck_val: Union[float, bool, int] = 0.0,

    safe_z: Optional[float] = None,

) -> bool:

    """Move using a simple Z-hop trajectory in Dobot absolute coordinates."""

    controller = _require_device()

    target_x = float(target_x)

    target_y = float(target_y)

    target_z = float(target_z)

    target_r = float(target_r)

    commanded_safe_z = float(DEFAULT_SAFE_Z if safe_z is None else safe_z)



    if not is_safe(target_x, target_y, target_z):

        print(

            f"!!! GERAKAN DIBATALKAN: Koordinat ({target_x}, {target_y}, {target_z}) di luar batas limit!"

        )

        return False



    if not is_safe(target_x, target_y, commanded_safe_z):

        print(

            f"!!! GERAKAN DIBATALKAN: Safe-Z {commanded_safe_z} untuk target ({target_x}, {target_y}) di luar batas!"

        )

        return False



    curr_x, curr_y, curr_z, curr_r = get_current_pose()

    fly_z = commanded_safe_z if curr_z < commanded_safe_z else curr_z

    if not is_safe(curr_x, curr_y, fly_z):

        print(

            f"!!! GERAKAN DIBATALKAN: Posisi terbang saat ini ({curr_x}, {curr_y}, {fly_z}) di luar batas!"

        )

        return False



    if curr_z < commanded_safe_z:

        controller._set_ptp_cmd(curr_x, curr_y, fly_z, curr_r, mode=PTPMode.MOVL_XYZ, wait=False)



    controller._set_ptp_cmd(target_x, target_y, fly_z, target_r, mode=PTPMode.MOVJ_XYZ, wait=False)



    try:

        controller._set_ptp_cmd(target_x, target_y, target_z, target_r, mode=PTPMode.MOVL_XYZ, wait=True)

    except Exception:

        print("\n>>> [WARNING] Singularitas atau error gerak! Reset otomatis...")

        clear_alarms()

        return False



    controller.suck(_normalize_suck_value(suck_val))

    time.sleep(SUCTION_SETTLE_DELAY_S)

    return True





def move_to_relative(

    rel_x_mm: float,

    rel_y_mm: float,

    rel_z_mm: float,

    target_r: float = 0.0,

    suck_val: Union[float, bool, int] = 0.0,

    safe_z: Optional[float] = None,

) -> bool:

    """Move relative to the calibrated world origin and frame."""

    target_x, target_y, target_z, resolved_r = resolve_relative_pose(

        rel_x_mm=rel_x_mm,

        rel_y_mm=rel_y_mm,

        rel_z_mm=rel_z_mm,

        target_r_deg=target_r,

    )

    return move_to_absolute(target_x, target_y, target_z, resolved_r, suck_val=suck_val, safe_z=safe_z)





def move_to_target(

    target_x: float,

    target_y: float,

    target_z: float,

    target_r: float = 0.0,

    suck_val: Union[float, bool, int] = 0.0,

) -> bool:

    """Backward-compatible alias for absolute Dobot moves."""

    return move_to_absolute(target_x, target_y, target_z, target_r=target_r, suck_val=suck_val)





def _rotation_from_pose(pose: Optional[Dict[str, Any]]) -> float:

    if not isinstance(pose, dict):

        return 0.0

    if pose.get("r_deg") is not None:

        return float(pose.get("r_deg", 0.0))

    if pose.get("r") is not None:

        return float(pose.get("r", 0.0))

    return 0.0





def _run_plan_step(operation: Dict[str, Any], use_relative_coordinates: bool) -> Dict[str, Any]:

    from_pose = operation.get("from", {}) if isinstance(operation, dict) else {}

    to_pose = operation.get("to", {}) if isinstance(operation, dict) else {}

    safe_z_mm = float(operation.get("safe_z_mm", DEFAULT_SAFE_Z))

    z_pick_mm = float(operation.get("z_pick_mm", 0.0))

    z_place_mm = float(operation.get("z_place_mm", 0.0))

    piece_id = str(operation.get("piece_id", ""))



    move_fn = move_to_relative if use_relative_coordinates else move_to_absolute



    pick_ok = move_fn(

        float(from_pose.get("x_mm", 0.0)),

        float(from_pose.get("y_mm", 0.0)),

        z_pick_mm,

        target_r=_rotation_from_pose(from_pose),

        suck_val=1.0,

        safe_z=safe_z_mm,

    )

    if not pick_ok:

        raise RuntimeError(f"Gagal pick piece {piece_id or 'unknown'}")



    place_ok = move_fn(

        float(to_pose.get("x_mm", 0.0)),

        float(to_pose.get("y_mm", 0.0)),

        z_place_mm,

        target_r=_rotation_from_pose(to_pose),

        suck_val=0.0,

        safe_z=safe_z_mm,

    )

    if not place_ok:

        raise RuntimeError(f"Gagal place piece {piece_id or 'unknown'}")



    return {

        "piece_id": piece_id,

        "picked": True,

        "placed": True,

    }





def execute_move_plan(move_plan: List[Dict[str, Any]], use_relative_coordinates: bool = True) -> List[Dict[str, Any]]:

    """Execute a move plan produced by the laptop solver."""

    if not isinstance(move_plan, list) or not move_plan:

        raise ValueError("move_plan harus berupa list dan tidak boleh kosong")



    results: List[Dict[str, Any]] = []

    for operation in move_plan:

        results.append(_run_plan_step(operation, use_relative_coordinates=use_relative_coordinates))

    return results