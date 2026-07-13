import sqlite3
import numpy as np
import os
import math

DB_DIR = '/home/pi/kodeintegrasi/data'
DB_NAME = os.path.join(DB_DIR, 'tangram.db')
DB_LOG_NAME = os.path.join(DB_DIR, 'tangram_logs.db')

BLOCKS = ["BT1", "BT2", "MT", "SQ", "ST1", "ST2", "PL"]

def setup_core_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    print(">>> [DB CORE] Membangun ulang arsitektur database utama...")

    cursor.execute("DROP TABLE IF EXISTS templates")
    cursor.execute("""
    CREATE TABLE templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shape_name TEXT,
        block_name TEXT,
        target_x REAL,
        target_y REAL,
        target_r REAL,
        hint TEXT DEFAULT ''
    );
    """)

    cursor.execute("DROP TABLE IF EXISTS live_tracking")
    cursor.execute("""
    CREATE TABLE live_tracking (
        block_name TEXT PRIMARY KEY,
        current_x REAL,
        current_y REAL,
        current_r REAL,
        target_x REAL,
        target_y REAL,
        target_r REAL,
        status TEXT
    );
    """)

    for block in BLOCKS:
        cursor.execute("""
            INSERT INTO live_tracking (block_name, current_x, current_y, current_r, target_x, target_y, target_r, status)
            VALUES (?, 150.0, 150.0, 0.0, 150.0, 150.0, 0.0, 'idle')
        """, (block,))
        
    cursor.execute("DROP TABLE IF EXISTS last_point")
    cursor.execute("""
    CREATE TABLE last_point (
        block_name TEXT PRIMARY KEY,
        last_x_1 REAL,
        last_y_1 REAL,
        last_r_1 REAL,
        last_x_2 REAL,
        last_y_2 REAL,
        last_r_2 REAL
    );
    """)

    for block in BLOCKS:
        cursor.execute("""
            INSERT INTO last_point (block_name, last_x_1, last_y_1, last_r_1, last_x_2, last_y_2, last_r_2)
            VALUES (?, 150.0, 150.0, 0.0, 150.0, 150.0, 0.0)
        """, (block,))

    cursor.execute("DROP TABLE IF EXISTS batch_info")
    cursor.execute("""
    CREATE TABLE batch_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shape_name TEXT,
        start_time TEXT
    );
    """)

    print(">>> [DB CORE] Menginjeksikan Resep-Resep Tangram ke Zona Aman...")
    
    # Injeksi dengan 6 Binding (?, ?, ?, ?, ?, ?)
    kucing_recipe = generate_kucing_recipe(s=105.0, tx=310.0, ty=0.0, rot_deg=90.0) 
    cursor.executemany("INSERT INTO templates (shape_name, block_name, target_x, target_y, target_r, hint) VALUES (?, ?, ?, ?, ?, ?)", kucing_recipe)

    rumah_recipe = generate_rumah_recipe(s=105.0, tx=280.0, ty=-70.0, rot_deg=90.0) 
    cursor.executemany("INSERT INTO templates (shape_name, block_name, target_x, target_y, target_r, hint) VALUES (?, ?, ?, ?, ?, ?)", rumah_recipe)

    unta_recipe = generate_unta_recipe(s=105.0, tx=300.0, ty=-60.0, rot_deg=90.0) 
    cursor.executemany("INSERT INTO templates (shape_name, block_name, target_x, target_y, target_r, hint) VALUES (?, ?, ?, ?, ?, ?)", unta_recipe)

    kotak_recipe = generate_kotak_recipe(s=105.0, tx=280.0, ty= 0.0, rot_deg=90.0) 
    cursor.executemany("INSERT INTO templates (shape_name, block_name, target_x, target_y, target_r, hint) VALUES (?, ?, ?, ?, ?, ?)", kotak_recipe)

    kambing_recipe = generate_kambing_recipe(s=105.0, tx=300.0, ty=-110.0, rot_deg=90.0) 
    cursor.executemany("INSERT INTO templates (shape_name, block_name, target_x, target_y, target_r, hint) VALUES (?, ?, ?, ?, ?, ?)", kambing_recipe)

    hiu_recipe = generate_hiu_recipe(s=105.0, tx=250.0, ty=-190.0, rot_deg=90.0) 
    cursor.executemany("INSERT INTO templates (shape_name, block_name, target_x, target_y, target_r, hint) VALUES (?, ?, ?, ?, ?, ?)", hiu_recipe)

    pesawat_recipe = generate_pesawat_recipe(s=105.0, tx=250.0, ty=-100.0, rot_deg=90.0) 
    cursor.executemany("INSERT INTO templates (shape_name, block_name, target_x, target_y, target_r, hint) VALUES (?, ?, ?, ?, ?, ?)", pesawat_recipe)

    kucing_duduk_recipe = generate_kucing_duduk_recipe(s=105.0, tx=310.0, ty=-60.0, rot_deg=90.0) 
    cursor.executemany("INSERT INTO templates (shape_name, block_name, target_x, target_y, target_r, hint) VALUES (?, ?, ?, ?, ?, ?)", kucing_duduk_recipe)

    conn.commit()
    conn.close()
    print(">>> [DB CORE] Basis data operasional utama SUKSES dikonfigurasi.")


def setup_logging_database():
    conn = sqlite3.connect(DB_LOG_NAME)
    cursor = conn.cursor()
    
    print("\n>>> [DB LOG] Memeriksa arsitektur data logger...")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hmi_user_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        operator_id TEXT,
        action TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_event_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        event_type TEXT,
        component TEXT,
        message TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS production_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shape_name TEXT,
        start_time DATETIME,
        end_time DATETIME,
        duration_sec REAL,
        status TEXT
    );
    """)

    conn.commit()
    conn.close()
    print(">>> [DB LOG] Basis data logging analitik SUKSES dikonfigurasi.")



# FUNGSI MATEMATIKA SPASIAL (per akar 2)
def get_b(s): 
    return [round(s / (np.sqrt(2)**i), 3) for i in range(5)]

def get_center(coords): 
    return np.round(np.mean(coords, axis=0), 1).tolist()

# GENERATOR BENTUK TANGRAM
def generate_kucing_recipe(s=105.0, tx=310.0, ty=0.0, rot_deg=90.0, hint="", mirror=False):
    b = get_b(s)
    P1, P2, P3, P4, P5 = b[0], b[1], b[2], b[3], b[4]
    local_blocks = {
        "BT1": [[0, 0], [-P2, 0], [0, P2]], 
        "BT2": [[0, P2], [-P3, P2-P3], [-P3, P2+P3]], 
        "MT":  [[-P3, P2+P3], [-P3, P3], [-(P4 + P3), P2 + P3 - P4]], 
        "SQ":  [[-P1, P2 + P3], [-(P1 - P5), P2 + P3 - P5], [-P3, P2 + P3], [-(P1 - P5), P2 + 2*P3 - P5]], 
        "ST1": [[-(P1 - P5), P2 + 2*P3 - P5], [-P1, P2 + P3], [-P1, P2 + 2*P3]], 
        "ST2": [[-(P1 - P5), P2 + 2*P3 - P5], [-P3, P2 + P3], [-P3, P2 + 2*P3]], 
        "PL":  [[0, 0], [P3, 0], [3*P5, P5], [P5, P5]] 
    }
    hint = "Hewan berbulu yang suka mengeong"
    return _build_db_records('kucing', local_blocks, tx, ty, rot_deg, hint, mirror)

def generate_rumah_recipe(s=105.0, tx=280.0, ty=-70.0, rot_deg=90.0, hint="", mirror=False):
    b = get_b(s)
    P1, P2, P3, P4, P5 = b[0], b[1], b[2], b[3], b[4]
    local_blocks = {
        "BT1": [[0, 0], [P1, 0], [P3, P3]], 
        "BT2": [[P3+P4-P1, P3], [P3+P4, P3], [P4, 2*P3]], 
        "MT":  [[0, 0], [P3, P3], [0, P3]], 
        "SQ":  [[P3, P3+P4], [P3+P4, P3+P4], [P3+P4, P3+2*P4], [P3, P3+2*P4]], 
        "ST1": [[P1, 0], [P1, P3], [1.5*P3, P5]], 
        "ST2": [[P3, P3], [1.5*P3, P5], [P1, P3]], 
        "PL":  [[P3+P4, P3], [P3+2*P4, P3], [P3+P4, P3+P4], [P3, P3+P4]] 
    }
    hint="Tempat kita berlindung dan tinggal"
    return _build_db_records('rumah', local_blocks, tx, ty, rot_deg, hint, mirror)

def generate_unta_recipe(s=105.0, tx=300.0, ty=-60.0, rot_deg=90.0, hint="", mirror=False):
    b = get_b(s)
    P1, P2, P3, P4, P5 = b[0], b[1], b[2], b[3], b[4]
    local_blocks = {
        "BT1": [[0, 0], [P3, P3], [0, P1]], 
        "BT2": [[P5, 1.5*P3], [P5+P2, 1.5*P3-P2], [P5+P2, 1.5*P3]], 
        "MT":  [[P5, 1.5*P3], [P5+P2, 1.5*P3], [P5+0.5*P2, 1.5*P3+P4]], 
        "SQ":  [[P5, 1.5*P3], [P3, P1], [P5, P1+P5], [0, P1]], 
        "ST1": [[-P5, 2.5*P3], [0, P1], [0, P1+P3]], 
        "ST2": [[-P5, 2.5*P3], [0, P1+P3], [-2*P5, 3*P3]], 
        "PL":  [[-P5, 1.5*P3], [0, P2-P5], [0, P1], [-P5, 2.5*P3]] 
    }
    hint="Hewan pelintas gurun dengan punuk"
    return _build_db_records('unta', local_blocks, tx, ty, rot_deg, hint, mirror)

def generate_kotak_recipe(s=105.0, tx=270.0, ty=-60.0, rot_deg=90.0, hint="", mirror=True): 
    b = get_b(s)
    P1, P2, P3, P4, P5 = b[0], b[1], b[2], b[3], b[4]
    local_blocks = {
        "BT1": [[0, 0], [P1, 0], [P3, P3]], 
        "BT2": [[P1, 0], [P1, P1], [P3, P3]], 
        "MT":  [[0, P3], [P3, P3+2*P5], [0, 2*P3]], 
        "SQ":  [[P3, P3], [1.5*P3, 1.5*P3], [P3, P3+2*P5], [P5, P5+P3]], 
        "ST1": [[P5, P5], [P3, P3], [P5, P5+P3]], 
        "ST2": [[1.5*P3, 1.5*P3], [P1, P1], [P3, P3+2*P5]], 
        "PL":  [[0, 0], [P5, P5], [P5, P5+P3], [0, P3]] 
    }
    hint="Bentuk dasar bersisi empat"
    return _build_db_records('kotak', local_blocks, tx, ty, rot_deg, hint, mirror)

def generate_kambing_recipe(s=105.0, tx=300.0, ty=-110.0, rot_deg=90.0, hint="", mirror=False):
    b = get_b(s)
    P1, P2, P3, P4, P5 = b[0], b[1], b[2], b[3], b[4]
    local_blocks = {
        "BT1": [[0, 0], [P2, P2], [0, P2]], 
        "BT2": [[P2+P3-P1, P2-P3], [P2+P3, P2-P3], [P2, P2]], 
        "MT":  [[P2+P5, P2+P5], [P2+P3+P5, P2+P5-P3], [P2+P3+P5, P2+P5]], 
        "SQ":  [[P2, P2], [P2+P5, P2-P5], [P2+P3, P2], [P2+P5, P2+P5]], 
        "ST1": [[0, P2-0.5*P3], [0, P2+0.5*P3], [-P5, P2]], 
        "ST2": [[P2+P3-P4, P2-P3], [P2+P3, P2-P3], [P2+P3, P2-P3-P4]], 
        "PL":  [[P2+P3-P4+P5, P2+P5], [P2+P3+P5, P2+P5], [P2+P3-P4+P5, P2+P5+P4], [P2+P3-2*P4+P5, P2+P5+P4]] 
    }
    hint="Mbeeeee"
    return _build_db_records('kambing', local_blocks, tx, ty, rot_deg, hint, mirror)

def generate_hiu_recipe(s=105.0, tx=250.0, ty=-190.0, rot_deg=90.0, hint="", mirror=False):
    b = get_b(s)
    P1, P2, P3, P4, P5 = b[0], b[1], b[2], b[3], b[4]
    local_blocks = {
        "BT1": [[0, 0], [P1, 0], [P3, P3]], 
        "BT2": [[P3, P3], [P3+P2, P3-P2], [P3+P2, P3]], 
        "MT":  [[P3+P2+2*P4, P3], [2*P3+P2+2*P4, P3], [P3+P2+2*P4, 2*P3]], 
        "SQ":  [[P3+P2, P3-P4], [P3+P2+P4, P3-P4], [P3+P2+P4, P3], [P3+P2, P3]], 
        "ST1": [[P1-P3, 0], [P1-P5, -P5], [P1, 0]], 
        "ST2": [[P3+P2-0.5*P4, P3], [P3+P2+0.5*P4, P3], [P3+P2+0.5*P4, P3+P4]], 
        "PL":  [[P3+P2+P4, P3-P4], [P3+P2+2*P4, P3], [P3+P2+2*P4, P3+P4], [P3+P2+P4, P3]] 
    }
    hint="baby .... dododododo"
    return _build_db_records('hiu', local_blocks, tx, ty, rot_deg, hint, mirror)

def generate_pesawat_recipe(s=105.0, tx=250.0, ty=-100.0, rot_deg=90.0, hint="", mirror=False):
    b = get_b(s)
    P1, P2, P3, P4, P5 = b[0], b[1], b[2], b[3], b[4]
    local_blocks = {
        "BT1": [[0, P3], [P3, 0], [P1, P3]], 
        "BT2": [[P3+P5, P5], [2*P3+2*P5, P5], [2*P3+2*P5, P5+P2]], 
        "MT":  [[P3, 0], [2*P3, -P3], [2*P3, 0]], 
        "SQ":  [[-P5, P5], [0, 0], [P5, P5], [0, P3]], 
        "ST1": [[0, 0], [P3, 0], [P5, P5]], 
        "ST2": [[0.25*P1, P3], [0.75*P1, P3], [P3, P3+P5]], 
        "PL":  [[P3, 0], [2*P3, 0], [2*P3+P5, P5], [P3+P5, P5]] 
    }
    hint="kendaraan terbang dengan sayap"
    return _build_db_records('pesawat', local_blocks, tx, ty, rot_deg, hint, mirror)

def generate_kucing_duduk_recipe(s=105.0, tx=310.0, ty=-60.0, rot_deg=90.0, hint="", mirror=True):
    b = get_b(s)
    P1, P2, P3, P4, P5 = b[0], b[1], b[2], b[3], b[4]
    local_blocks = {
        "BT1": [[0, 0], [P3, P3], [-P3, P3]], 
        "BT2": [[P3, P3], [0, 2*P3], [-P3, P3]], 
        "MT":  [[0, 0], [P3, 0], [P3, P3]], 
        "SQ":  [[0, 2*P3], [0.5*P3, 2.5*P3], [0, 3*P3], [-0.5*P3, 2.5*P3]], 
        "ST1": [[-0.5*P3, 2.5*P3], [0, 3*P3], [-0.5*P3, 3.5*P3]], 
        "ST2": [[0, 3*P3], [0.5*P3, 2.5*P3], [0.5*P3, 3.5*P3]], 
        "PL":  [[P3, 0], [P3+P5, P5], [P3+P5, P3+P5], [P3, P3]] 
    }
    hint="kucing kucing apa yang lagi duduk"
    return _build_db_records('kucing_duduk', local_blocks, tx, ty, rot_deg, hint, mirror)

def _build_db_records(shape_name, blocks, tx, ty, rot_deg, hint="", mirror=False):
    theta_rad = np.radians(rot_deg)
    cos_t, sin_t = np.cos(theta_rad), np.sin(theta_rad)
    
    db_records = []
    for name, pts in blocks.items():
        new_pts = []
        for x, y in pts:
            # 1. ROTASI & TRANSLASI GLOBAL
            nx = (x * cos_t) - (y * sin_t) + tx
            ny = (x * sin_t) + (y * cos_t) + ty
            
            # 2. MIRRORING GLOBAL (Refleksi sejajar sumbu X / garis Y = ty)
            if mirror:
                ny = 2 * ty - ny
                
            new_pts.append([nx, ny])
            
        center = get_center(new_pts)
        
        # 3. KALKULASI SUDUT LOKAL (R)
        block_type = name.upper()
        
        def get_dist_sq(p1, p2):
            return (p1[0]-p2[0])**2 + (p1[1]-p2[1])**2

        if block_type.startswith("BT") or block_type.startswith("MT") or block_type.startswith("ST"):
            d01 = get_dist_sq(new_pts[0], new_pts[1])
            d12 = get_dist_sq(new_pts[1], new_pts[2])
            d20 = get_dist_sq(new_pts[2], new_pts[0])
            
            if d01 >= d12 and d01 >= d20: p_r, pA, pB = new_pts[2], new_pts[0], new_pts[1]
            elif d12 >= d01 and d12 >= d20: p_r, pA, pB = new_pts[0], new_pts[1], new_pts[2]
            else: p_r, pA, pB = new_pts[1], new_pts[2], new_pts[0]
            
            vBisect = ((pA[0]-p_r[0]) + (pB[0]-p_r[0]), (pA[1]-p_r[1]) + (pB[1]-p_r[1]))
            raw_angle = math.degrees(math.atan2(vBisect[1], vBisect[0]))
            calc_r = 45.0 - raw_angle
            
        elif block_type.startswith("SQ"):
            v = (new_pts[1][0]-new_pts[0][0], new_pts[1][1]-new_pts[0][1])
            calc_r = -math.degrees(math.atan2(v[1], v[0]))
            
        elif block_type.startswith("PL"):
            # [UBAH: Logika disederhanakan, cukup cari sisi terpanjang]
            side_vectors = [
                (new_pts[1][0]-new_pts[0][0], new_pts[1][1]-new_pts[0][1]),
                (new_pts[2][0]-new_pts[1][0], new_pts[2][1]-new_pts[1][1]),
                (new_pts[3][0]-new_pts[2][0], new_pts[3][1]-new_pts[2][1]),
                (new_pts[0][0]-new_pts[3][0], new_pts[0][1]-new_pts[3][1])
            ]
            lens = [vx**2 + vy**2 for vx, vy in side_vectors]
            max_idx = lens.index(max(lens))
            vLongSide = side_vectors[max_idx]
            
            calc_r = -math.degrees(math.atan2(vLongSide[1], vLongSide[0]))
            
        else:
            calc_r = 0.0

        # ==========================================================
        # 4. NORMALISASI SUDUT CERDAS
        # ==========================================================
        calc_r = round(calc_r / 45.0) * 45.0
        
        if block_type.startswith("SQ"):
            calc_r = abs(calc_r) % 90
            if calc_r == 90: calc_r = 0.0
            
        elif block_type.startswith("PL"):
            # [TAMBAH: Membungkus sudut PL ke rentang batas fisik uniknya]
            # Karena 180 derajat identik dengan 0 derajat pada jajar genjang
            calc_r = calc_r % 180
            if calc_r > 90:
                calc_r -= 180
            if calc_r == 90: 
                calc_r = -90
                
        else: # Segitiga (Punya 8 sisi orientasi bebas)
            while calc_r > 180: calc_r -= 360
            while calc_r <= -180: calc_r += 360
            if calc_r == -180: calc_r = 180

        if calc_r == -0.0: calc_r = 0.0

        db_records.append((shape_name, name, center[0], center[1], calc_r, hint))
        
    return db_records
    

if __name__ == "__main__":
    print("=== INISIALISASI ARSITEKTUR MULTI-DATABASE TANGRAM IIOT ===")
    
    os.makedirs(DB_DIR, exist_ok=True)
    
    setup_core_database()
    setup_logging_database()
    print("\n[SUCCESS] Semua database berhasil di-deploy terpisah!")