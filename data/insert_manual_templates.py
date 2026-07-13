# -*- coding: utf-8 -*-
import sqlite3

DB_NAME = '/home/pi/kodeintegrasi/data/tangram.db'

# 1. EDIT NAMA DAN KOORDINAT DI BAWAH INI
SHAPE_NAME = "CRAB"
HINT_TEXT = "UANG UANG UANG UANG UANG"


# ST1 Kuning
# BT1 Cyan atau sedikit biru muda(?)
# BT2 pink (?)

# Format -> "KUCING DUDUK MANIS": (Target_X, Target_Y, Target_R)
MANUAL_BLOCKS = {
    "BT1": (238.0, -60.9, 180.0),
    "BT2": (248.0, -131.0, 0.0),
    "MT":  (185.9, -16.1, -135.0),
    "SQ":  (198.2, -91.9, 0.0),
    "ST1": (276.4, -48.6, -90.0),
    "ST2": (163.5, -161.8, 180.0),
    "PL":  (199.1, -152.6, 45.0)
}

def main():
    print(f"Menyuntikkan 7 blok untuk resep '{SHAPE_NAME}' ke database...")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    records = []
    for block, (x, y, r) in MANUAL_BLOCKS.items():
        records.append((SHAPE_NAME, block, x, y, r, HINT_TEXT))
        
    # Eksekusi sapu jagat (sekali jalan langsung 7 baris)
    cursor.executemany("""
        INSERT INTO templates (shape_name, block_name, target_x, target_y, target_r, hint)
        VALUES (?, ?, ?, ?, ?, ?)
    """, records)
    
    conn.commit()
    conn.close()
    
    print("[SUCCESS] Data berhasil ditambahkan!")

if __name__ == "__main__":
    main()