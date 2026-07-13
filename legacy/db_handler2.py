import sqlite3

DB_NAME = 'tangram.db'

def get_pending_target():
    """Mengambil 1 balok yang berstatus 'pending' dari memori fisik (live_tracking)."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Kita ambil data dari live_tracking sekarang, bukan dari tangram_recipes lagi
    cursor.execute("""
        SELECT block_name, block_name, target_x, target_y 
        FROM live_tracking 
        WHERE status = 'pending' 
        LIMIT 1
    """)
    record = cursor.fetchone()
    conn.close()
    
    # Format return: (target_id, block_name, target_x, target_y)
    # Karena target_id tidak kita pakai lagi di tabel baru, kita isi ganda dengan block_name 
    # agar tidak error saat di-unpack oleh main.py
    return record

def mark_target_completed(block_name):
    """
    Mengubah status menjadi 'completed' SETELAH Dobot sukses menaruh balok.
    Kerennya Digital Twin: Posisi saat ini (current) otomatis diperbarui menjadi posisi target!
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE live_tracking 
        SET status = 'completed',
            current_x = target_x,
            current_y = target_y,
            current_r = target_r
        WHERE block_name = ?
    """, (block_name,))
    
    conn.commit()
    conn.close()

def activate_template(shape_name):
    """
    Fungsi cerdas yang dipanggil HMI saat memilih "Kucing" / "Rumah".
    Tugasnya: Meng-copy resep dari tabel 'templates' dan menimpanya ke target 'live_tracking'.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Ambil resep desain dari tabel master
    cursor.execute("SELECT block_name, target_x, target_y, target_r FROM templates WHERE shape_name = ?", (shape_name,))
    resep_blok = cursor.fetchall()
    
    if len(resep_blok) > 0:
        # 2. Suntikkan satu per satu ke memori Dobot (live_tracking) dan bangunkan statusnya
        for blok in resep_blok:
            nama_b, t_x, t_y, t_r = blok
            cursor.execute("""
                UPDATE live_tracking
                SET target_x = ?, target_y = ?, target_r = ?, status = 'pending'
                WHERE block_name = ?
            """, (t_x, t_y, t_r, nama_b))
        
        conn.commit()
        print(f"\n[DATABASE] Template '{shape_name}' aktif! Membangunkan {len(resep_blok)} balok untuk dirakit.")
    else:
        print(f"\n[DATABASE] ERROR: Template '{shape_name}' belum ada di buku resep SQLite.")
        
    conn.close()

# Opsional: Jika sewaktu-waktu kita butuh menyimpan data balok dari Kamera Visi
def update_current_position(block_name, cx, cy, cr):
    """Dipanggil oleh Computer Vision untuk meng-update titik 'Asal' di meja sesungguhnya."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE live_tracking 
        SET current_x = ?, current_y = ?, current_r = ?
        WHERE block_name = ?
    """, (cx, cy, cr, block_name))
    conn.commit()
    conn.close()

def add_new_shape(shape_name, blocks):
    """Menyimpan template baru dari web ke database."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        records = []
        for blk in blocks:
            target_x = blk.get('x', 0)
            target_y = blk.get('y', 0)
            target_r = blk.get('r', 0)  # TAMBAHAN: Ambil nilai rotasinya juga
            block_name = blk.get('block_name', 'UNKNOWN')
            
            # Ubah ke tabel 'templates', hapus status, masukkan target_r
            records.append((shape_name, block_name, target_x, target_y, target_r))
            
        cursor.executemany("""
            INSERT INTO templates (shape_name, block_name, target_x, target_y, target_r)
            VALUES (?, ?, ?, ?, ?)
        """, records)
        
        conn.commit()
        print(f"[DATABASE] Sukses menyimpan bentuk baru: {shape_name} ({len(records)} kepingan)")
    except Exception as e:
        print(f"[DATABASE ERROR] Gagal menyimpan bentuk baru: {e}")
    finally:
        conn.close()

def delete_shape(shape_name):
    """Menghapus template dari database berdasarkan namanya."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Ubah tangram_recipes jadi templates
        cursor.execute("DELETE FROM templates WHERE shape_name = ?", (shape_name,))
        conn.commit()
        print(f"[DATABASE] Sukses menghapus bentuk: {shape_name} dari database")
    except Exception as e:
        print(f"[DATABASE ERROR] Gagal menghapus bentuk: {e}")
    finally:
        conn.close()