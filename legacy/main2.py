# Nama File: main.py
import paho.mqtt.client as mqtt
import time
import json
import db_handler2 as db_handler 
import dobot_driver2 as dobot_driver

# === SETUP MQTT BROKER ===
BROKER_ADDRESS = "10.6.101.60" 

TOP_TOPIC = "IIoT/Labtek_VI/Lab_TF_C/tangram_01/"
TOPIC_MANUAL = TOP_TOPIC + "cmd/action_manual"
TOPIC_TEMPLATE = TOP_TOPIC + "cmd/action_template"
TOPIC_DATABASE = TOP_TOPIC + "cmd/action_database"

def on_connect(client, userdata, flags, rc):
    print("Yay! Berhasil connect ke MQTT Broker dengan kode:", rc)
    client.subscribe(TOPIC_MANUAL)
    client.subscribe(TOPIC_TEMPLATE)
    client.subscribe(TOPIC_DATABASE)

def on_message(client, userdata, msg):
    topik = msg.topic
    payload_mentah = msg.payload.decode("utf-8")
    
    try:
        data_json = json.loads(payload_mentah)
        pesan = data_json.get("value")
    except Exception:
        pesan = payload_mentah.strip()

    print(f"\nDapat pesan di {topik}: {pesan}")
    step = 5 

    if topik == TOPIC_MANUAL:
        try:
            if isinstance(pesan, dict):
                print(f"Menuju koordinat spesifik: {pesan}")
                dobot_driver.move_to_target(
                    pesan.get('x', 0), 
                    pesan.get('y', 0), 
                    pesan.get('z', 0), 
                    pesan.get('r', 0), 
                    wait=False
                )
            
            elif pesan == "reset":
                print("Kembali ke posisi awal (Reset)...")
                dobot_driver.reset_home()
            
            elif pesan == "clear_alarm":
                print("Memaksa reset alarm merah dobot ke hijau...")
                dobot_driver.clear_alarms()
                print("Alarm berhasil di-reset!")

            elif pesan in ["maju", "mundur", "kiri", "kanan", "atas", "bawah", "rotate_cw", "rotate_ccw"]:
                # langsung serahkan eksekusi ke fungsi driver yang baru
                dobot_driver.fast_jog(pesan, step=step)

            elif pesan == "stop":
                print("Berhenti mengirimkan perintah step")
                # pastikan perintah stop juga masuk ke driver agar antrean gerak dibersihkan
                dobot_driver.fast_jog("stop")

            elif pesan == "grab":
                print("Grabbing!")
                dobot_driver.set_suction(True)
                
            elif pesan == "release":
                print("Releasing!")
                dobot_driver.set_suction(False)

            elif pesan == "acak_kepingan":
                dobot_driver.acak_kepingan()

        except Exception as e:
            print(f"Terjadi eror sistem: {e}")

    elif topik == TOPIC_TEMPLATE:
        print(f"=== Memulai sistem otomasi perakitan bentuk: {pesan} ===")
        
        PICK_X = 150.0
        PICK_Y = 150.0
        Z_PICK = -10.0
        Z_DROP = -20.0
        Z_SAFE = 50.0 

        while True:
            target = db_handler.get_pending_target()
            
            if target is None:
                print("Misi Selesai! Semua balok tangram telah dirakit.")
                dobot_driver.reset_home()
                break
                
            target_id, block_name, target_x, target_y = target
            print(f">>> Menargetkan balok: {block_name} ke (X: {target_x:.1f}, Y: {target_y:.1f})")
            
            print("Memindai meja dengan Kamera IP WGWK...")
            time.sleep(1)
            
            print(f"Menjemput balok di titik supply ({PICK_X}, {PICK_Y})...")
            dobot_driver.move_to_target(PICK_X, PICK_Y, Z_SAFE, wait=True)
            dobot_driver.move_to_target(PICK_X, PICK_Y, Z_PICK, wait=True)
            dobot_driver.suck(True)
            time.sleep(0.5) 
            dobot_driver.move_to_target(PICK_X, PICK_Y, Z_SAFE, wait=True)
            
            print(f"Membawa balok {block_name} ke titik rakit ({target_x:.1f}, {target_y:.1f})...")
            dobot_driver.move_to_target(target_x, target_y, Z_SAFE, wait=True)
            dobot_driver.move_to_target(target_x, target_y, Z_DROP, wait=True)
            dobot_driver.suck(False)
            time.sleep(0.5) 
            dobot_driver.move_to_target(target_x, target_y, Z_SAFE, wait=True)
            
            db_handler.mark_target_completed(target_id)
            print(f"Balok {block_name} terpasang! Status di-update ke completed.")

    elif topik == TOPIC_DATABASE:
        print("=== Menerima Data Database dari HMI Engineer ===")
        if isinstance(pesan, dict):
            action = pesan.get("action")
            shape_name = pesan.get("shape_name")
            
            if action == "tambah_bentuk":
                blocks = pesan.get("blocks", [])
                print(f">>> Menambahkan template baru: {shape_name}")
                # panggil fungsi nulis db yang baru kita bikin tadi
                db_handler.add_new_shape(shape_name, blocks)
            
            elif action == "hapus_bentuk":
                print(f">>> Menghapus template: {shape_name}")
                # panggil fungsi hapus db
                db_handler.delete_shape(shape_name)

def main():
    print("=== Sistem HMI Coquette Dobot Dimulai ===")
    
    # 1. Inisialisasi Koneksi Mekanik
    koneksi_sukses = dobot_driver.connect()
    if not koneksi_sukses:
        print("[FATAL] Tidak dapat terhubung ke Dobot. Program dihentikan.")
        return

    # 2. Inisialisasi Koneksi Jaringan
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    print("Mencoba menyambungkan ke Broker...")
    client.connect(BROKER_ADDRESS, 1883, 60)

    try:
        print("Sistem stand-by. Menunggu perintah dari HMI Coquette...")
        client.loop_start() # Jalankan penerima pesan di background
        
        # Loop utama untuk memancarkan (telemetry) koordinat live
        while True:
            if dobot_driver.is_connected():
                try:
                    # Tarik data asli dari mesin
                    pose = dobot_driver.get_current_pose_payload()
                    data_posisi = {
                        "x": round(pose["x_mm"], 1),
                        "y": round(pose["y_mm"], 1),
                        "z": round(pose["z_mm"], 1),
                        "r": round(pose["r_deg"], 1)
                    }
                    # Pancarkan ke topik khusus pose
                    client.publish(TOP_TOPIC + "telemetry/pose", json.dumps(data_posisi))
                except Exception as e:
                    pass # Abaikan kalau gagal baca sensor sedetik
            
            time.sleep(0.5) # Update layar setiap 0.5 detik
            
    except KeyboardInterrupt:
        print("\nProgram dihentikan secara manual oleh User (Ctrl+C).")
    finally:
        dobot_driver.disconnect()
        client.disconnect()
        print("Sistem dimatikan secara aman.")

if __name__ == "__main__":
    main()