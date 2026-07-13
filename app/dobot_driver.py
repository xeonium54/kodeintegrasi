# -*- coding: utf-8 -*-
"""Shared Dobot control helpers for RevPi runtime."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union
import math
import time
import threading

from pydobotplus import Dobot
from pydobot.enums import PTPMode
from pydobot.message import Message

DEFAULT_PORT = "/dev/ttyUSB2"

# ==========================================
# KONFIGURASI KALIBRASI KAMERA & APRILTAG
# ==========================================
REFERENCE_MARKER_ID = 1
REFERENCE_MARKER_LABEL = "apriltag_1"
SECONDARY_REFERENCE_MARKER_ID = 0
SECONDARY_REFERENCE_MARKER_LABEL = "apriltag_0"

MARKER_WORLD_POSITIONS_MM = {
    0: (135.3, -292.4),
    1: (179.3, -1.2),
    2: (227.4, -306.0),
    3: (271.4, -14.8),
}

# ==========================================
# KONFIGURASI BATAS KERJA & KECEPATAN
# ==========================================
X_LIMIT = (-320.0, 320.0)
Y_LIMIT = (-320.0, 320.0)
Z_LIMIT = (-50.0, 170.0)
R_MIN_SAFE = 150.0  
R_MAX_SAFE = 330.0  

DEFAULT_SAFE_Z = 26.0
DEFAULT_SPEED_XY = 400.0
DEFAULT_SPEED_Z = 200.0

SLOW_SPEED_XY = 100.0
SLOW_SPEED_Z = 100.0

POSE_REFRESH_DELAY_S = 0.05 
SUCTION_SETTLE_DELAY_S = 0.1
VECTOR_EPSILON_MM = 1e-6

is_busy = False
device: Optional[Dobot] = None
_alat_lock = threading.RLock()

_marker_calibrations: Dict[int, Dict[str, Any]] = {}
_frame_calibration: Optional[Dict[str, Any]] = None

# =========================================================================
# FUNGSI KONTUR & KINEMATIKA DINAMIS
# =========================================================================
def get_terrain_z(x: float, y: float) -> float:
    if 140.0 <= x <= 323.0 and -267.0 <= y <= 73.0:
        return -16.90
    return -30.5      

def get_r_min_safe(z: float) -> float:
    if z <= 10.0: return 145.0
    elif z <= 50.0: return 145.0 + ((z - 10.0) * 0.25)
    else: return 155.0 + ((z - 50.0) * 1.0)

def normalize_r(r_deg: float) -> float:
    """Membungkus sudut ke -180 s/d 180, lalu melimitasi fisik di +-150."""
    r = float(r_deg)
    
    while r > 180.0: r -= 360.0
    while r <= -180.0: r += 360.0
    
    if r > 150.0: return 150.0
    if r < -150.0: return -150.0
    
    return round(r, 1)

def calculate_smart_grip(vision_r: float, target_r: float) -> Tuple[float, float]:
    """
    LOGIKA SUPER AMAN: SPLIT BURDEN (Beban Ganda)
    Mencegah lengan terpelintir jauh dengan cara membagi beban rotasi secara simetris.
    Servo J4 dijamin tidak akan pernah melampaui rentang -90 hingga +90 derajat!
    """
    # 1. Hitung selisih putaran terpendek yang BENAR-BENAR dibutuhkan (Maksimal pasti 180 atau -180)
    delta_r = (target_r - vision_r + 180.0) % 360.0 - 180.0
    
    # 2. Bagi rotasi sama rata! Setengah putaran untuk Jemput, Setengah untuk Taruh.
    # Karena titik tengahnya adalah 0, maka putarannya selalu seimbang dan ringan.
    pick_r = -delta_r / 2.0
    place_r = delta_r / 2.0
        
    return round(pick_r, 1), round(place_r, 1)

def is_path_safe(x1: float, y1: float, x2: float, y2: float, r_min: float) -> bool:
    dx = x2 - x1
    dy = y2 - y1
    jarak_total = math.sqrt(dx**2 + dy**2)
    
    if jarak_total == 0:
        return math.sqrt(x1**2 + y1**2) >= r_min
        
    langkah = max(1, int(jarak_total / 5.0)) 
    for i in range(langkah + 1):
        t = i / langkah
        cek_x = x1 + (t * dx)
        cek_y = y1 + (t * dy)
        if math.sqrt(cek_x**2 + cek_y**2) < r_min:
            return False 
    return True

def _safe_error_message(x: float, y: float, z: float) -> str:
    if not (X_LIMIT[0] <= x <= X_LIMIT[1]): return f"X diluar batas {X_LIMIT}"
    if not (Y_LIMIT[0] <= y <= Y_LIMIT[1]): return f"Y diluar batas {Y_LIMIT}"
    if not (Z_LIMIT[0] <= z <= Z_LIMIT[1]): return f"Z diluar batas vertikal ekstrem {Z_LIMIT}"
        
    radius = math.sqrt(x**2 + y**2)
    dynamic_r_min = get_r_min_safe(z)
    
    if radius > R_MAX_SAFE or radius < dynamic_r_min: 
        return f"Singularitas! Z:{z:.1f} mengharuskan Radius antar ({dynamic_r_min:.1f}-{R_MAX_SAFE} mm). Aktual: {radius:.1f}"
    return ""

def is_safe(x: float, y: float, z: float) -> bool: 
    return not _safe_error_message(float(x), float(y), float(z))

# ==========================================
# UTILITAS KONEKSI & KALIBRASI KAMERA
# ==========================================
def _copy_pose_payload(pose: Dict[str, Any]) -> Dict[str, float]:
    return {"x_mm": float(pose["x_mm"]), "y_mm": float(pose["y_mm"]), "z_mm": float(pose["z_mm"]), "r_deg": float(pose["r_deg"])}

def _world_point_for_marker(marker_id: int, world_x_mm: Optional[float] = None, world_y_mm: Optional[float] = None) -> Tuple[float, float]:
    if world_x_mm is not None and world_y_mm is not None:
        return float(world_x_mm), float(world_y_mm)
    point = MARKER_WORLD_POSITIONS_MM.get(int(marker_id))
    if point is None: raise ValueError(f"Marker ID {marker_id} belum punya koordinat dunia")
    return float(point[0]), float(point[1])

def _require_device() -> Dobot:
    if device is None: raise RuntimeError("Dobot is not connected")
    return device

def is_connected() -> bool:
    return device is not None

def connect(port: str = DEFAULT_PORT) -> bool:
    global device
    if device is not None: return True
    with _alat_lock:
        try:
            device = Dobot(port=port)
            print(">>> Membuka Koneksi Serial Dobot...")
            time.sleep(1.0) 
            clear_alarms()
            _require_device().speed(float(DEFAULT_SPEED_XY), float(DEFAULT_SPEED_Z))
            time.sleep(0.5)
            print(">>> Koneksi Berhasil & Dobot Siap!")
            return True
        except Exception as exc:
            device = None
            print(f"!!! Gagal koneksi Dobot: {exc}")
            return False

def disconnect() -> None:
    global device
    if device is None: return
    with _alat_lock:
        try: device.suck(False)
        except Exception: pass
        try: device.close()
        finally:
            device = None
            print(">>> Koneksi Serial Dobot Ditutup.")

def clear_alarms() -> bool:
    try: controller = _require_device()
    except RuntimeError: return False
    with _alat_lock:
        try: controller._set_queued_cmd_clear()
        except AttributeError: pass
        msg = Message()
        msg.id = 20
        msg.ctrl = 0x01
        controller._send_command(msg)
    return True

def get_current_pose() -> Tuple[float, float, float, float]:
    with _alat_lock:
        controller = _require_device()
        pose = controller.get_pose() 
        if pose is None:
            time.sleep(POSE_REFRESH_DELAY_S)
            pose = controller.get_pose()
            if pose is None: raise RuntimeError("Gagal mengambil data pose Dobot")
        return float(pose.position.x), float(pose.position.y), float(pose.position.z), float(pose.position.r)

def get_current_pose_payload() -> Dict[str, float]:
    x_mm, y_mm, z_mm, r_deg = get_current_pose()
    return {"x_mm": x_mm, "y_mm": y_mm, "z_mm": z_mm, "r_deg": r_deg}

def set_suction(enabled: bool) -> None:
    with _alat_lock:
        controller = _require_device()
        controller.suck(bool(enabled))

def _normalize_suck_value(suck_val: Union[float, bool, int]) -> bool: 
    return bool(float(suck_val))

def _resolve_world_relative_xy(rel_x_mm: float, rel_y_mm: float) -> Tuple[float, float]:
    frame = _frame_calibration
    origin = _marker_calibrations.get(REFERENCE_MARKER_ID)
    if origin is None: raise RuntimeError("Origin belum dikalibrasi")
    if frame is None: return float(rel_x_mm), float(rel_y_mm)

    rotation_rad = math.radians(float(frame["rotation_deg"]))
    scale_xy = float(frame["scale_xy"])
    cos_theta = math.cos(rotation_rad)
    sin_theta = math.sin(rotation_rad)

    dx = scale_xy * ((cos_theta * float(rel_x_mm)) - (sin_theta * float(rel_y_mm)))
    dy = scale_xy * ((sin_theta * float(rel_x_mm)) + (cos_theta * float(rel_y_mm)))
    return float(dx), float(dy)

def resolve_relative_pose(rel_x_mm: float, rel_y_mm: float, rel_z_mm: float, target_r_deg: float = 0.0) -> Tuple[float, float, float, float]:
    origin = _marker_calibrations.get(REFERENCE_MARKER_ID)
    if origin is None: raise RuntimeError("Origin belum dikalibrasi")
    delta_x_mm, delta_y_mm = _resolve_world_relative_xy(rel_x_mm, rel_y_mm)
    pose = origin["pose"]
    return (float(pose["x_mm"]) + float(delta_x_mm), float(pose["y_mm"]) + float(delta_y_mm), float(pose["z_mm"]) + float(rel_z_mm), float(target_r_deg))

# =========================================================================
# FUNGSI PERGERAKAN UTAMA ABSOLUT
# =========================================================================
def move_to_absolute(target_x: float, target_y: float, target_z: Optional[float] = None, target_r: float = 0.0, suck_val: Union[float, bool, int] = 0.0, safe_z: Optional[float] = None, is_transit: bool = False) -> bool:
    controller = _require_device()
    target_x, target_y = float(target_x), float(target_y)
    commanded_safe_z = float(DEFAULT_SAFE_Z if safe_z is None else safe_z)

    if target_z is None: target_z = get_terrain_z(target_x, target_y)
    else: target_z = float(target_z)

    if not is_safe(target_x, target_y, target_z):
        print(f"!!! GERAKAN DIBATALKAN: Koordinat target ({target_x:.1f}, {target_y:.1f}, {target_z:.1f}) di luar batas fisik!")
        return False

    curr_x, curr_y, curr_z, curr_r = get_current_pose()
    target_r = normalize_r(target_r) 
    
    if not is_transit:
        dynamic_r_min = get_r_min_safe(commanded_safe_z)
        if not is_path_safe(curr_x, curr_y, target_x, target_y, r_min=dynamic_r_min):
            print(f"\n   [MITIGASI] Rute lurus ke ({target_x:.1f}, {target_y:.1f}) memotong batas lengan!")
            pull_x = 180.0  
            pull_y = curr_y

            if curr_x < pull_x:
                if is_safe(pull_x, pull_y, commanded_safe_z):
                    print(f"   -> [JEMBATAN 1] Menarik lengan aman ke depan (X:{pull_x}, Y:{pull_y:.1f})")
                    if not move_to_absolute(pull_x, pull_y, commanded_safe_z, target_r, suck_val, safe_z, is_transit=True):
                        return False
                    curr_x, curr_y, curr_z, curr_r = get_current_pose()

            kandidat_transit = [(300.0, 0.0), (250.0,0.0), (180.0,180.0), (180.0, -180.0), (180.0, -150.0), (180.0,150.0)]
            rute_aman_ditemukan = False
            for tx, ty in kandidat_transit:
                if is_path_safe(curr_x, curr_y, tx, ty, dynamic_r_min) and is_path_safe(tx, ty, target_x, target_y, dynamic_r_min):
                    print(f"   -> [JEMBATAN 2] Rute penyeberangan aman via ({tx}, {ty})...")
                    if not move_to_absolute(tx, ty, commanded_safe_z, target_r, suck_val, safe_z, is_transit=True):
                        return False
                    rute_aman_ditemukan = True
                    break
            
            if not rute_aman_ditemukan:
                print("!!! [MITIGASI GAGAL] Tidak ada rute memutar yang aman. Gerakan dibatalkan.")
                return False
                
            curr_x, curr_y, curr_z, curr_r = get_current_pose()

    fly_z = commanded_safe_z if curr_z < commanded_safe_z else curr_z

    # -----------------------------------------------------------------
    # LANGKAH 1: Naik & Geser Horizontal (Gunakan MOVJ agar luwes & aman)
    # -----------------------------------------------------------------
    with _alat_lock:
        if curr_z < commanded_safe_z:
            controller._set_ptp_cmd(curr_x, curr_y, fly_z, curr_r, mode=PTPMode.MOVJ_XYZ.value, wait=False)
        controller._set_ptp_cmd(target_x, target_y, fly_z, target_r, mode=PTPMode.MOVJ_XYZ.value, wait=False)

    start_time = time.time()
    while True:
        cx, cy, cz, _ = get_current_pose()
        jarak_horizontal = math.sqrt((cx - target_x)**2 + (cy - target_y)**2)
        if jarak_horizontal < 2.5 and abs(cz - fly_z) < 2.5: 
            break
        if time.time() - start_time > 8.0:
            print("\n!!! [TIMEOUT] Gerak horizontal terhambat.")
            clear_alarms()
            return False
        time.sleep(0.05)

    # -----------------------------------------------------------------
    # LANGKAH 2: Interlock Pompa Vakum
    # -----------------------------------------------------------------
    is_picking = _normalize_suck_value(suck_val)
    if not is_transit and is_picking:
        print("   [MEKANIK] Menyalakan pompa vakum di atas titik jemput...")
        set_suction(True)
        time.sleep(0.1) 
        
    # -----------------------------------------------------------------
    # LANGKAH 3: Turun Vertikal Terkontrol (MOVL + Kecepatan Diperlambat)
    # -----------------------------------------------------------------
    with _alat_lock:
        controller.speed(float(SLOW_SPEED_XY), float(SLOW_SPEED_Z))
        controller._set_ptp_cmd(target_x, target_y, target_z, target_r, mode=PTPMode.MOVL_XYZ.value, wait=False)

    start_time = time.time()
    gerakan_turun_sukses = False
    
    while True:
        try:
            cx, cy, cz, _ = get_current_pose()
            jarak_vertikal = abs(cz - target_z)
            
            if jarak_vertikal < 2.5: 
                gerakan_turun_sukses = True
                break
                
            if time.time() - start_time > 6.0:
                print(f"\n!!! [TIMEOUT] Lengan mentok turun di Z={cz:.1f}. Target Z={target_z}.")
                clear_alarms()
                break
        except RuntimeError as e:
            raise RuntimeError(f"Hardware alarm terpicu di perjalanan turun: {e}")
        time.sleep(0.05)

    with _alat_lock:
        controller.speed(float(DEFAULT_SPEED_XY), float(DEFAULT_SPEED_Z))
        
    if not gerakan_turun_sukses:
        return False

    # -----------------------------------------------------------------
    # LANGKAH 4: Penahanan Durasi Waktu di Bawah
    # -----------------------------------------------------------------
    if not is_transit:
        if is_picking:
            print("   [MEKANIK] Kontak tercapai. Menahan posisi 0.5 detik untuk penguncian vakum...")
            time.sleep(0.5) 
        else:
            print("   [MEKANIK] Pelepasan kepingan di koordinat target...")
            set_suction(False)
            time.sleep(SUCTION_SETTLE_DELAY_S)
        
    return True

def move_to_relative(rel_x_mm: float, rel_y_mm: float, rel_z_mm: float, target_r: float = 0.0, suck_val: Union[float, bool, int] = 0.0, safe_z: Optional[float] = None) -> bool:
    target_x, target_y, target_z, resolved_r = resolve_relative_pose(rel_x_mm=rel_x_mm, rel_y_mm=rel_y_mm, rel_z_mm=rel_z_mm, target_r_deg=target_r)
    return move_to_absolute(target_x, target_y, target_z, resolved_r, suck_val=suck_val, safe_z=safe_z)


# =========================================================================
# FUNGSI MOVE WRAPPER DENGAN Z-LIFT ESCAPE SEQUENCE
# =========================================================================
def move_to_target(target_x: float, target_y: float, target_z: Optional[float] = None, target_r: float = 0.0, suck_val: Union[float, bool, int] = 0.0) -> bool:
    if target_z is None: 
        target_z = get_terrain_z(target_x, target_y)
        
    is_picking = _normalize_suck_value(suck_val)
    max_retries = 3 if is_picking else 1  
    
    for attempt in range(1, max_retries + 1):
        sukses = move_to_absolute(target_x, target_y, target_z, target_r=target_r, suck_val=suck_val)
        
        if sukses:
            return True
            
        if attempt < max_retries:
            print(f"\n   [RETRY {attempt}/{max_retries}] Lengan gagal mencapai koordinat (X:{target_x:.1f}, Y:{target_y:.1f}).")
            print("   [ESCAPE] Mengeksekusi Prosedur Pelarian Vertikal (Z-Lift Escape)...")
            clear_alarms()
            time.sleep(0.5)
            
            # CEK KESELAMATAN Z-LIFT: Mencegah tabrakan siku lengan sendiri di bawah
            cx, cy, cz, cr = get_current_pose()
            current_r_radius = math.sqrt(cx**2 + cy**2)
            safe_r_for_lift = get_r_min_safe(DEFAULT_SAFE_Z)
            
            if current_r_radius < safe_r_for_lift:
                print(f"   [ESCAPE] Lengan terlipat terlalu dalam (R={current_r_radius:.1f}). Mendorong keluar dulu...")
                scale = (safe_r_for_lift + 5.0) / current_r_radius if current_r_radius > 0.1 else 1.0
                nx, ny = cx * scale, cy * scale
                move_to_absolute(nx, ny, cz, cr, is_transit=True)
                
            print("   [ESCAPE] Mengangkat ke elevasi aman...")
            curr_x, curr_y, _, curr_r = get_current_pose()
            move_to_absolute(curr_x, curr_y, DEFAULT_SAFE_Z, curr_r, is_transit=True)
            
            print("   [MITIGASI] Mundur ke Titik Jembatan (200, 0) untuk me-reset trajektori...")
            move_to_absolute(200.0, 0.0, DEFAULT_SAFE_Z, 0.0, is_transit=True)
            time.sleep(0.5)
            print("   [MITIGASI] Mencoba kembali ke titik target awal...\n")
        else:
            print("   [FAILED] Seluruh percobaan mitigasi gagal. Menyerah pada balok ini.")
            
    return False

# ==========================================
# FUNGSI TAMBAHAN HMI & HOMING
# ==========================================
HOME_X, HOME_Y, HOME_Z, HOME_R = 0.0, -200.0, 0.0, 0.0

def reset_home():
    global device, is_busy
    if not device: return False
    
    if is_busy:
        print("!!! [HMI-WARNING] Proses sedang berjalan! Abaikan klik tombol berlebih.")
        return False
        
    is_busy = True
    try:
        print("\n>>> [MEKANIK] Mempersiapkan Kalibrasi Homing...")
        clear_alarms()
        time.sleep(1.0)
        
        print(">>> Membawa lengan ke posisi aman Pra-Homing (X:200, Y:0, Z:30)...")
        try:
            controller = _require_device()
            controller._set_ptp_cmd(HOME_X, HOME_Y, HOME_Z, HOME_R, mode=PTPMode.MOVJ_XYZ.value, wait=True)
            time.sleep(1.5)
        except Exception as e:
            print(f"[WARNING] Gerak pra-homing terhambat: {e}. Terpaksa bypass ke Homing langsung.")

        with _alat_lock:
            controller = _require_device()
            controller.speed(float(DEFAULT_SPEED_XY), float(DEFAULT_SPEED_Z))
            time.sleep(0.5)
            print(">>> Mengeksekusi Homing. Menunggu ayunan selesai (~20 detik)...")
            controller.home()
            print(">>> Homing beres. Mengembalikan lengan ke titik Standby...")
            
        move_to_absolute(HOME_X, HOME_Y, HOME_Z, HOME_R, suck_val=0.0)
        return True
    finally:
        is_busy = False

def fast_jog(action, step=1.0):
    global device
    if not device: return
    
    cx, cy, cz, cr = get_current_pose()

    if action == 'maju': cx += step
    elif action == 'mundur': cx -= step
    elif action == 'kiri': cy += step
    elif action == 'kanan': cy -= step
    elif action == 'atas': cz += step
    elif action == 'bawah': cz -= step
    elif action == 'rotate_ccw': cr += step
    elif action == 'rotate_cw': cr -= step
    elif action == 'stop':
        with _alat_lock:
            try: _require_device()._set_queued_cmd_clear()
            except AttributeError: pass
        return

    if is_safe(cx, cy, cz):
        with _alat_lock:
            _require_device()._set_ptp_cmd(cx, cy, cz, cr, mode=PTPMode.MOVL_XYZ.value, wait=False)
    else:
        print("!!! [WARNING] Jog dibatalkan: Mentok batas mekanik.")