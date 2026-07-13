import sqlite3
import numpy as np

DB_NAME = 'tangram.db'

# Daftar 7 Blok Tangram Standar
BLOCKS = ["BT1", "BT2", "MT", "SQ", "ST1", "ST2", "PL"]

def setup_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    print(">>> [DB] Membangun ulang arsitektur database...")

    # ==================================================
    # 1. TABEL BUKU RESEP (Master Templates)
    # ==================================================
    cursor.execute("DROP TABLE IF EXISTS templates")
    cursor.execute("""
    CREATE TABLE templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shape_name TEXT,
        block_name TEXT,
        target_x REAL,
        target_y REAL,
        target_r REAL
    );
    """)

    # ==================================================
    # 2. TABEL LIVE TRACKING (Digital Twin - 14 Data)
    # ==================================================
    cursor.execute("DROP TABLE IF EXISTS live_tracking")
    cursor.execute("""
    CREATE TABLE live_tracking (
        block_name TEXT PRIMARY KEY,
        
        -- Data 1: Posisi Aktual / Asal
        current_x REAL,
        current_y REAL,
        current_r REAL,
        
        -- Data 2: Posisi Tujuan Akhir
        target_x REAL,
        target_y REAL,
        target_r REAL,
        
        status TEXT
    );
    """)

    # ==================================================
    # 3. SUNTIKKAN DATA AWAL (Inisialisasi)
    # ==================================================
    # Kita isi 7 baris live_tracking dengan status 'idle' 
    # (Anggap posisi awalnya masih 0, nanti di-update oleh Kamera)
    for block in BLOCKS:
        cursor.execute("""
            INSERT INTO live_tracking (block_name, current_x, current_y, current_r, target_x, target_y, target_r, status)
            VALUES (?, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'idle')
        """, (block,))

    # Suntikkan 1 Resep Bawaan: Kucing (Dari perhitungan matriksmu sebelumnya)
    # tx=200, ty=0 agar jatuhnya aman di tengah meja
    cat_recipe = generate_cat_recipe(s=90, tx=200.0, ty=0.0)
    cursor.executemany("""
        INSERT INTO templates (shape_name, block_name, target_x, target_y, target_r)
        VALUES (?, ?, ?, ?, ?)
    """, cat_recipe)

    conn.commit()
    print(">>> [DB] Selesai! Tabel 'templates' & 'live_tracking' siap digunakan.")
    conn.close()

# --- Fungsi Matematika (Jangan Dihapus) ---
def get_b(s): return [round(s / (np.sqrt(2)**i), 3) for i in range(5)]
def get_center(coords): return np.round(np.mean(coords, axis=0), 3).tolist()

def generate_cat_recipe(s=90, tx=310.0, ty=0.0):
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
    theta = np.radians(90.0)
    cos_t, sin_t = np.round(np.cos(theta), 5), np.round(np.sin(theta), 5)
    
    db_records = []
    for name, pts in local_blocks.items():
        new_pts = [[(x * cos_t) - (y * sin_t) + tx, (x * sin_t) + (y * cos_t) + ty] for x, y in pts]
        center = get_center(new_pts)
        # Format: (Nama Bentuk, Nama Blok, Target X, Target Y, Rotasi R)
        db_records.append(('Kucing', name, center[0], center[1], 0.0))
        
    return db_records

if __name__ == "__main__":
    setup_database()