# -*- coding: utf-8 -*-
import sqlite3
import random
from datetime import datetime

DB_NAME = '/home/pi/kodeintegrasi/data/tangram.db'
DB_LOG_NAME = '/home/pi/kodeintegrasi/data/tangram_logs.db'
LOG_DB_TIMEOUT_SECONDS = 1.0

BLOCKS = ["BT1", "BT2", "MT", "SQ", "ST1", "ST2", "PL"]

# =========================================================================
# INTERNAL CORE FUNCTIONS (Database Utama: tangram.db)
# =========================================================================

def get_pending_target():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT block_name, current_x, current_y, current_r, target_x, target_y, target_r 
        FROM live_tracking 
        WHERE status = 'pending' 
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return row

def has_pending_blocks():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM live_tracking WHERE status = 'pending' LIMIT 1")
    result = cursor.fetchone() is not None
    conn.close()
    return result

def mark_target_completed(block_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE live_tracking 
        SET current_x = target_x, current_y = target_y, current_r = target_r, status = 'idle' 
        WHERE block_name = ?
    """, (block_name,))
    conn.commit()
    conn.close()

def mark_target_error(block_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE live_tracking 
        SET status = 'error' 
        WHERE block_name = ?
    """, (block_name,))
    conn.commit()
    conn.close()
    print(f">>> [DB] Tugas {block_name} dialihkan ke status 'error'. Antrean aman.")

def backup_current_to_last_point():
    """
    Menyimpan posisi kepingan yang berserakan di meja (current) ke tabel last_point.
    Otomatis dipanggil sebelum mengeksekusi resep bentuk.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        # 1. Geser history sebelumnya (History 1 menjadi History 2)
        cursor.execute('''
            UPDATE last_point
            SET last_x_2 = last_x_1, last_y_2 = last_y_1, last_r_2 = last_r_1
        ''')
        
        # 2. Simpan posisi aktual saat ini di meja ke History 1
        cursor.execute('''
            UPDATE last_point
            SET last_x_1 = (SELECT current_x FROM live_tracking WHERE live_tracking.block_name = last_point.block_name),
                last_y_1 = (SELECT current_y FROM live_tracking WHERE live_tracking.block_name = last_point.block_name),
                last_r_1 = (SELECT current_r FROM live_tracking WHERE live_tracking.block_name = last_point.block_name)
        ''')
        conn.commit()
        print(">>> [DB] Posisi berserakan berhasil di-backup ke memori.")
    except Exception as e:
        print(f"!!! [DB ERROR] Gagal mem-backup ke last_point: {e}")
    finally:
        conn.close()

def activate_template(shape_name):
    # BACKUP DULU POSISI SAAT INI SEBELUM MENJADI TARGET BARU!
    backup_current_to_last_point()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT block_name, target_x, target_y, target_r FROM templates WHERE shape_name = ?", (shape_name,))
    template_data = cursor.fetchall()
    
    if not template_data:
        print(f"!!! [DB] Template '{shape_name}' tidak ditemukan di database.")
        conn.close()
        return
        
    for row in template_data:
        b_name, tx, ty, tr = row
        cursor.execute("""
            UPDATE live_tracking 
            SET target_x = ?, target_y = ?, target_r = ?, status = 'pending'
            WHERE block_name = ?
        """, (tx, ty, tr, b_name))
    
    cursor.execute("DELETE FROM batch_info")
    cursor.execute("INSERT INTO batch_info (shape_name, start_time) VALUES (?, ?)",
                   (shape_name, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    print(f">>> [DB] Template '{shape_name}' siap dieksekusi oleh mesin.")

def get_active_batch():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT shape_name, start_time FROM batch_info LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row

def clear_active_batch():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM batch_info")
    conn.commit()
    conn.close()

def return_blocks_to_last_point():
    """
    Mengembalikan target ke posisi sebelum dirakit (last_point 1).
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE live_tracking
            SET target_x = (SELECT last_x_1 FROM last_point WHERE last_point.block_name = live_tracking.block_name),
                target_y = (SELECT last_y_1 FROM last_point WHERE last_point.block_name = live_tracking.block_name),
                target_r = (SELECT last_r_1 FROM last_point WHERE last_point.block_name = live_tracking.block_name),
                status = 'pending'
            WHERE block_name IN ('BT1', 'BT2', 'MT', 'SQ', 'ST1', 'ST2', 'PL')
        ''')
        conn.commit()
        print(">>> [DB] Mode KEMBALIKAN diaktifkan! Target disetel ke lokasi semula.")
    except Exception as e:
        print(f"!!! [DB ERROR] Gagal mengembalikan ke last_point: {e}")
    finally:
        conn.close()

def trigger_acak_kepingan():
    # Karena kita ingin "Acak Kepingan" berfungsi sebagai Undo/Kembalikan,
    # kita tidak lagi menggunakan random, melainkan memanggil fungsi restore.
    return_blocks_to_last_point()

def save_new_template(shape_name, blocks, hint=""):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM templates WHERE shape_name = ?", (shape_name,))
    for blk in blocks:
        cursor.execute("""
            INSERT INTO templates (shape_name, block_name, target_x, target_y, target_r, hint)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (shape_name, blk['block_name'], blk['x'], blk['y'], blk['r'], hint))
    conn.commit()
    conn.close()
    print(f">>> [DB] Desain master '{shape_name}' berhasil direkam.")

def delete_template(shape_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM templates WHERE shape_name = ?", (shape_name,))
    conn.commit()
    conn.close()
    print(f">>> [DB] Desain master '{shape_name}' telah dihapus.")

def update_live_tracking_from_vision(vision_blocks):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        for blk in vision_blocks:
            nama = blk.get("block_name")
            cx = blk.get("x")
            cy = blk.get("y")
            cr = blk.get("r")
            cursor.execute("""
                UPDATE live_tracking 
                SET current_x = ?, current_y = ?, current_r = ?
                WHERE block_name = ?
            """, (cx, cy, cr, nama))
        conn.commit()
        print(f">>> [DB] Sinkronisasi Digital Twin sukses untuk {len(vision_blocks)} kepingan.")
    except Exception as e:
        print(f"!!! [DB-ERROR] Gagal sinkronisasi data visi: {e}")
    finally:
        conn.close()

# =========================================================================
# ANALYTICS LOGGER FUNCTIONS (Database Historis: tangram_logs.db)
# =========================================================================

def log_system_event(event_type: str, component: str, message: str):
    conn = sqlite3.connect(DB_LOG_NAME, timeout=LOG_DB_TIMEOUT_SECONDS)
    conn.execute("PRAGMA busy_timeout = 1000")
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO system_event_logs (event_type, component, message)
            VALUES (?, ?, ?)
        """, (event_type.upper(), component, message))
        conn.commit()
    except Exception as e:
        print(f"[LOG ERROR] Gagal menulis log sistem: {e}")
    finally:
        conn.close()

def log_production_metric(shape_name: str, start_time: str, end_time: str, duration_sec: float, status: str):
    conn = sqlite3.connect(DB_LOG_NAME, timeout=LOG_DB_TIMEOUT_SECONDS)
    conn.execute("PRAGMA busy_timeout = 1000")
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO production_metrics (shape_name, start_time, end_time, duration_sec, status)
            VALUES (?, ?, ?, ?, ?)
        """, (shape_name, start_time, end_time, float(duration_sec), status.upper()))
        conn.commit()
        print(f">>> [LOG ANALYTICS] Siklus kerja '{shape_name}' tercatat ({duration_sec:.1f} detik, Status: {status})")
    except Exception as e:
        print(f"[LOG ERROR] Gagal menulis metrik produksi: {e}")
    finally:
        conn.close()

def log_hmi_action(operator_id: str, action: str):
    conn = sqlite3.connect(DB_LOG_NAME, timeout=LOG_DB_TIMEOUT_SECONDS)
    conn.execute("PRAGMA busy_timeout = 1000")
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO hmi_user_logs (operator_id, action)
            VALUES (?, ?)
        """, (operator_id, action))
        conn.commit()
    except Exception as e:
        print(f"[LOG ERROR] Gagal menulis log HMI: {e}")
    finally:
        conn.close()