# -*- coding: utf-8 -*-
import json
import re
import paho.mqtt.client as mqtt
import dobot_driver
import db_handler 

TOP_TOPIC = "IIoT/Labtek_VI/Lab_TF_C/tangram_01/"
TOPIC_MANUAL = TOP_TOPIC + "cmd/action_manual"
TOPIC_TEMPLATE = TOP_TOPIC + "cmd/action_template"
TOPIC_DATABASE = TOP_TOPIC + "cmd/action_database"
TOPIC_VISION = TOP_TOPIC + "telemetry/vision_update"
TOPIC_LOGIN_STATUS = TOP_TOPIC + "state/login_status"

try:
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
except AttributeError:
    mqtt_client = mqtt.Client()


def _extract_operator(text):
    if not isinstance(text, str):
        return "Operator_HMI"
    m = re.match(r"^(?:User\s+)?(\S+)", text)
    return m.group(1) if m else "Operator_HMI"


def on_connect(client, userdata, flags, rc):
    print(f"\n>>> [MQTT] Berhasil terhubung ke Broker Mosquitto (Kode: {rc})")
    db_handler.log_system_event("INFO", "MQTT_Broker", f"Tersambung ke broker dengan kode {rc}")
    
    client.subscribe(TOP_TOPIC + "cmd/#")
    client.subscribe(TOPIC_LOGIN_STATUS)
    print(">>> [MQTT] Telinga Python standby mendengarkan instruksi HMI Node-RED...")

def on_message(client, userdata, msg):
    try:
        payload_mentah = msg.payload.decode("utf-8")
        topik = msg.topic
        
        try:
            data_json = json.loads(payload_mentah)
            pesan = data_json.get("value")
        except Exception:
            pesan = payload_mentah.strip()

        # ==========================================
        # 0. LOGIN / LOGOUT STATUS
        # ==========================================
        if topik == TOPIC_LOGIN_STATUS:
            operator = _extract_operator(pesan)
            db_handler.log_hmi_action(operator, str(pesan))
            print(f"[HMI] Login/Logout tercatat: {pesan}")
            return

        # ==========================================
        # 1. KENDALI MANUAL & PERGERAKAN FISIK
        # ==========================================
        if topik == TOPIC_MANUAL:
            if dobot_driver.is_busy and pesan not in ["clear_alarm", "stop"]:
                print("[HMI-WARNING] DITOLAK! Dobot sedang mode AUTO.")
                return

            if isinstance(pesan, dict):
                db_handler.log_hmi_action("Operator_HMI", f"Jog Absolut X:{pesan.get('x')} Y:{pesan.get('y')}")
                
                print(f"[HMI] Menuju koordinat pasti: X:{pesan.get('x')}, Y:{pesan.get('y')}")
                dobot_driver.move_to_target(pesan.get("x", 0), pesan.get("y", 0), pesan.get("z", 0), pesan.get("r", 0))
            elif isinstance(pesan, str):
                db_handler.log_hmi_action("Operator_HMI", f"Klik Tombol Manual: {pesan}")
                
                if pesan == "grab":
                    dobot_driver.set_suction(True)
                elif pesan == "release":
                    dobot_driver.set_suction(False)
                elif pesan == "clear_alarm":
                    dobot_driver.clear_alarms()
                elif pesan == "reset":
                    dobot_driver.reset_home()
                elif pesan == "acak_kepingan":
                    print("[HMI] Perintah diterima: KEMBALIKAN KEPINGAN!")
                    db_handler.trigger_acak_kepingan()
                elif pesan in ["maju", "mundur", "kiri", "kanan", "atas", "bawah", "rotate_cw", "rotate_ccw", "stop"]:
                    dobot_driver.fast_jog(pesan, step=5.0)

        # ==========================================
        # 2. OTOMASI TEMPLATE & GAME
        # ==========================================
        elif topik == TOPIC_TEMPLATE:
            db_handler.log_hmi_action("Operator_HMI", f"Pilih Template: {pesan}")
            
            if dobot_driver.is_busy:
                print("[HMI-WARNING] DITOLAK! Selesaikan perakitan saat ini terlebih dahulu.")
                return
            print(f"\n[HMI] >>> Memulai rakit template: '{pesan}'")
            db_handler.activate_template(pesan)

        # ==========================================
        # 3. DATABASE ENGINEER (Simpan / Hapus Bentuk)
        # ==========================================
        elif topik == TOPIC_DATABASE:
            if isinstance(pesan, dict):
                aksi = pesan.get("action")
                nama_bentuk = pesan.get("shape_name")
                
                db_handler.log_hmi_action("Operator_HMI", f"Database Engineer: {aksi} - {nama_bentuk}")
                
                if aksi == "tambah_bentuk":
                    if not nama_bentuk:
                        print("[HMI-ERROR] shape_name kosong, dibatalkan.")
                        return
                    blok_kepingan = pesan.get("blocks", [])
                    if not blok_kepingan:
                        print(f"[HMI-ERROR] Blocks kosong untuk '{nama_bentuk}', dibatalkan.")
                        return
                    
                    print(f"\n[HMI] >>> Menerima desain template baru: '{nama_bentuk}'")
                    converted_blocks = []
                    for blk in blok_kepingan:
                        if not all(k in blk for k in ("block_name", "x", "y", "r")):
                            print(f"[HMI-ERROR] Blok tidak lengkap, dilewati: {blk}")
                            continue
                        
                        # [PENTING] Transformasi Ganda telah dihapus di sini! 
                        # Python hanya menerima angka absolut dari algoritma presisi app.js
                        converted_blocks.append({
                            "block_name": blk["block_name"],
                            "x": float(blk["x"]),
                            "y": float(blk["y"]),
                            "r": float(blk["r"])
                        })
                        
                    if converted_blocks:
                        db_handler.save_new_template(nama_bentuk, converted_blocks, pesan.get("hint", ""))
                    else:
                        print(f"[HMI-ERROR] Tidak ada blok valid untuk '{nama_bentuk}', dibatalkan.")
                    
                elif aksi == "hapus_bentuk":
                    if not nama_bentuk:
                        print("[HMI-ERROR] shape_name kosong untuk hapus, dibatalkan.")
                        return
                    db_handler.delete_template(nama_bentuk)
                    
        # ==========================================
        # 4. COMPUTER VISION (Update Posisi Live)
        # ==========================================
        elif topik == TOPIC_VISION:
            if isinstance(pesan, dict) and pesan.get("action") == "update_vision":
                blok_terdeteksi = pesan.get("blocks", [])
                
                if dobot_driver.is_busy:
                    pass 
                else:
                    db_handler.update_live_tracking_from_vision(blok_terdeteksi)

    except Exception as e:
        err_msg = f"Gagal memproses pesan: {e}"
        print(f"[ERROR MQTT] {err_msg}")
        db_handler.log_system_event("ERROR", "MQTT_Listener", err_msg)

_listener_started = False

def start_listener(broker_address="10.6.101.60"):
    global _listener_started
    if _listener_started:
        print("[MQTT] Listener sudah aktif, skip duplikasi.")
        return
    _listener_started = True
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    print(f"Mencoba menyambungkan ke Broker di {broker_address}...")
    mqtt_client.connect(broker_address, 1883, 60)
    mqtt_client.loop_start() 

def publish_telemetry(data_posisi: dict):
    try:
        mqtt_client.publish(TOP_TOPIC + "telemetry/pose", json.dumps(data_posisi))
    except Exception:
        pass

if __name__ == "__main__":
    import time

    start_listener()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()