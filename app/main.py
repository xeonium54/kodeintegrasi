# -*- coding: utf-8 -*-
import time
import threading
from datetime import datetime
import db_handler
import dobot_driver
import mqtt_handler 

def telemetry_worker():
    while True:
        if dobot_driver.is_connected():
            try:
                pose = dobot_driver.get_current_pose_payload()
                data_posisi = {
                    "x": round(pose["x_mm"], 1),
                    "y": round(pose["y_mm"], 1),
                    "z": round(pose["z_mm"], 1),
                    "r": round(pose["r_deg"], 1)
                }
                mqtt_handler.publish_telemetry(data_posisi)
            except Exception:
                pass 
        time.sleep(0.5) 

def main_loop():
    print("=== Sistem Otomasi Perakitan Tangram Dimulai ===")
    
    koneksi_sukses = dobot_driver.connect()
    if not koneksi_sukses:
        print("[FATAL] Tidak dapat terhubung ke Dobot. Periksa kabel serial USB.")
        return

    mqtt_handler.start_listener()
    
    t_telemetry = threading.Thread(target=telemetry_worker, daemon=True)
    t_telemetry.start()
    
    is_idle = False 
    batch_was_active = False

    while True:
        target = db_handler.get_pending_target()
        
        if target is None:
            if batch_was_active and not db_handler.has_pending_blocks():
                batch = db_handler.get_active_batch()
                if batch:
                    shape_name, start_time_str = batch
                    end_time = datetime.now()
                    start_time = datetime.fromisoformat(start_time_str)
                    duration = (end_time - start_time).total_seconds()
                    db_handler.log_production_metric(shape_name, start_time_str, end_time.isoformat(), duration, "SUCCESS")
                db_handler.clear_active_batch()
                batch_was_active = False

            if not is_idle:
                print("\n[INFO] Mode Otomatis Idle. Menunggu instruksi dari HMI...")
                print("   [Dobot] Menyingkir ke posisi Standby (0, -200) agar pandangan Kamera WGWK bebas.")
                dobot_driver.move_to_target(target_x=0.0, target_y=-200.0, target_z=0.0, target_r=0.0, suck_val=0.0)
                is_idle = True
            time.sleep(1) 
            continue  
            
        is_idle = False
        batch_was_active = True
        
        block_name, pick_x, pick_y, pick_r, drop_x, drop_y, drop_r = target
        
        # ---------------------------------------------------------
        # 1. PENGGUNAAN SMART GRIP OFFSET
        # Menghitung rotasi servo teraman sebelum Dobot menjemput balok
        # ---------------------------------------------------------
        sudut_pick, sudut_place = dobot_driver.calculate_smart_grip(pick_r, drop_r)
        
        print("-" * 60)
        print(f">>> Mengeksekusi balok: {block_name}")
        print(f"    Dari : (X: {pick_x:.1f}, Y: {pick_y:.1f}) | Offset Jemput : {sudut_pick} deg")
        print(f"    Ke   : (X: {drop_x:.1f}, Y: {drop_y:.1f}) | Offset Taruh  : {sudut_place} deg")
        
        try:
            dobot_driver.is_busy = True 
            
            print("   [Visi] Memindai meja dengan Kamera IP WGWK...")
            time.sleep(1) 
            
            # Eksekusi penjemputan menggunakan sudut_pick
            sukses_pick = dobot_driver.move_to_target(pick_x, pick_y, target_r=sudut_pick, suck_val=1.0)
            
            if not sukses_pick:
                print(f"   [ERROR] Gagal menjemput balok {block_name} di area suplai.")
                db_handler.mark_target_error(block_name)
                # Jaga-jaga: Matikan vakum kalau-kalau sempat menyala tapi gagal mengangkat
                dobot_driver.set_suction(False)
                continue 
                
            # Eksekusi peletakan menggunakan sudut_place
            sukses_drop = dobot_driver.move_to_target(drop_x, drop_y, target_r=sudut_place, suck_val=0.0)
            
            if sukses_drop:
                db_handler.mark_target_completed(block_name) 
                print(f"   [SUCCESS] Balok {block_name} berhasil dipindahkan!")
            else:
                print(f"   [ERROR] Gagal menaruh balok {block_name}. Jalur terblokir!")
                dobot_driver.clear_alarms()
                
                # ========================================================
                # 2. PROSEDUR MITIGASI PEMBUANGAN (REJECT SEQUENCE)
                # ========================================================
                print("   [MITIGASI] Lengan masih memegang balok! Membuang ke Zona Reject (150, 200)...")
                
                # Amankan Z-Lift terlebih dahulu
                cx, cy, cz, cr = dobot_driver.get_current_pose()
                dobot_driver.move_to_absolute(cx, cy, dobot_driver.DEFAULT_SAFE_Z, cr, is_transit=True)
                
                # Bawa ke pojok meja yang kosong dan jatuhkan baloknya
                dobot_driver.move_to_absolute(150.0, -200.0, 0.0, target_r=0.0, suck_val=0.0)
                
                print(f"   [INFO] Balok {block_name} diamankan di Zona Reject.")
                db_handler.mark_target_error(block_name)
                
        except RuntimeError as e:
            print(f"\n   [FATAL ALARM] Koneksi/Mekanik terganggu: {e}")
            print("   [RECOVERY] Mereset otak Dobot secara otomatis...")
            dobot_driver.clear_alarms()
            
            # Jika hardware crash sepenuhnya, langsung matikan vakum agar balok jatuh di tempat
            dobot_driver.set_suction(False)
            db_handler.mark_target_error(block_name)
            time.sleep(1.5) 
            
            # Naikkan lengan agar tidak menyapu meja saat perulangan berikutnya dimulai
            try:
                cx, cy, cz, cr = dobot_driver.get_current_pose()
                if cz < dobot_driver.DEFAULT_SAFE_Z:
                    dobot_driver.move_to_absolute(cx, cy, dobot_driver.DEFAULT_SAFE_Z, cr, is_transit=True)
            except Exception:
                pass # Abaikan jika bacaan pose juga ikut crash
                
            continue 
            
        finally:
            dobot_driver.is_busy = False

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Program dihentikan secara manual oleh User (Ctrl+C).")
    finally:
        print("Merapikan sisa memori dan koneksi mekanik...")
        try:
            dobot_driver.disconnect()
        except:
            pass
        print("Sistem Dimatikan secara aman.")