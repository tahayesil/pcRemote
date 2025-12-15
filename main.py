import os
import sys
import socket
import threading
import subprocess
import ctypes
import psutil
import pyautogui
import uvicorn
import tkinter as tk
import glob
from tkinter import scrolledtext
from fastapi import FastAPI
from pydantic import BaseModel

# --- AYARLAR ---
app = FastAPI()
UDP_PORT = 50001        
SERVER_PORT = 8000      

pyautogui.FAILSAFE = False

# --- VERİ MODELLERİ ---
class VolumeRequest(BaseModel):
    action: str
    value: float = 0.0

class MouseMoveRequest(BaseModel):
    x: float
    y: float

class LaunchRequest(BaseModel):
    path: str

# --- 1. SİSTEM VE GÜVENLİK ---
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def add_firewall_rule():
    rule_name = "PCRemoteServer_Kotlin"
    exe_path = sys.executable
    cmd = f'netsh advfirewall firewall add rule name="{rule_name}" dir=in action=allow program="{exe_path}" enable=yes profile=any'
    try:
        subprocess.run(f'netsh advfirewall firewall delete rule name="{rule_name}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL)
        log("✅ Güvenlik Duvarı kuralı eklendi.")
    except Exception as e:
        log(f"⚠️ Güvenlik Duvarı Hatası: {e}")

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

# --- 2. GELİŞMİŞ UYGULAMA LİSTELEME ---
def get_installed_apps_from_start_menu():
    """Windows Başlat Menüsündeki tüm kısayolları tarar."""
    apps = []
    
    # 1. Ortak Başlat Menüsü (Tüm Kullanıcılar)
    common_path = os.path.join(os.environ["ProgramData"], r"Microsoft\Windows\Start Menu\Programs")
    # 2. Kullanıcı Başlat Menüsü (Sadece bu kullanıcı)
    user_path = os.path.join(os.environ["AppData"], r"Microsoft\Windows\Start Menu\Programs")
    
    paths = [common_path, user_path]
    
    seen_names = set()

    # Manuel olarak eklemek istediklerin (Favoriler)
    apps.append({"name": "Google Chrome", "path": "chrome"})
    apps.append({"name": "Spotify", "path": "spotify"})
    seen_names.add("Google Chrome")
    seen_names.add("Spotify")

    for root_path in paths:
        if os.path.exists(root_path):
            # Alt klasörleri de gez (os.walk)
            for root, dirs, files in os.walk(root_path):
                for file in files:
                    if file.lower().endswith(".lnk"):
                        name = file[:-4] # .lnk uzantısını sil
                        full_path = os.path.join(root, file)
                        
                        # Gereksiz dosyaları ele (Uninstall, Yardım vb.)
                        if "uninstall" in name.lower() or "kaldır" in name.lower() or "help" in name.lower():
                            continue
                            
                        if name not in seen_names:
                            # Tırnak içine alıyoruz ki dosya yolundaki boşluklar sorun çıkarmasın
                            apps.append({"name": name, "path": f'"{full_path}"'})
                            seen_names.add(name)
    
    # İsme göre alfabetik sırala
    apps.sort(key=lambda x: x['name'])
    return apps

# --- 3. UDP KEŞİF SERVİSİ ---
def start_udp_listener():
    try:
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(('0.0.0.0', UDP_PORT))
        log(f"📡 UDP Keşif servisi {UDP_PORT} portunda dinleniyor...")
        
        while True:
            data, addr = udp.recvfrom(1024)
            message = data.decode('utf-8')
            
            if "PC_CONTROLLER_DISCOVER" in message:
                log(f"🔎 Tarama isteği geldi: {addr[0]}")
                # Android'e cevap ver
                response = f"PC_SERVER_HERE:{socket.gethostname()}".encode('utf-8')
                udp.sendto(response, addr)
    except Exception as e:
        log(f"❌ UDP Hatası: {e}")

# --- 4. API ENDPOINTLERİ ---

@app.get("/")
def check_connection():
    return {"status": "connected"}

@app.get("/stats")
def get_stats():
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    return {
        "cpu": cpu,
        "ram_percent": ram.percent,
        "ram_used": round(ram.used / (1024**3), 2),
        "ram_total": round(ram.total / (1024**3), 2)
    }

@app.get("/apps")
def get_apps():
    return get_installed_apps_from_start_menu()

@app.post("/open-app")
def launch_app(req: LaunchRequest):
    try:
        # start komutu cmd üzerinden çalıştırılır, path tırnak içindeyse boşluk sorunu olmaz
        # Windows'ta start "" "path" formatı güvenlidir
        os.system(f'start "" {req.path}')
        log(f"🚀 Uygulama açıldı: {req.path}")
        return {"status": "success"}
    except Exception as e:
        log(f"Hata: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/volume")
def control_volume(req: VolumeRequest):
    if req.action == "up": pyautogui.press("volumeup")
    elif req.action == "down": pyautogui.press("volumedown")
    elif req.action == "mute": pyautogui.press("volumemute")
    return {"status": "success"}

@app.post("/mouse/move")
def move_mouse(req: MouseMoveRequest):
    try: pyautogui.moveRel(req.x, req.y)
    except: pass 
    return {"status": "moved"}

@app.post("/mouse/click")
def click_mouse():
    pyautogui.click()
    return {"status": "clicked"}

@app.post("/system/shutdown")
def shutdown_pc():
    log("⚠️ Bilgisayar kapatılıyor...")
    os.system("shutdown /s /t 5") 
    return {"status": "shutdown_initiated"}

@app.post("/system/restart")
def restart_pc():
    log("⚠️ Bilgisayar yeniden başlatılıyor...")
    os.system("shutdown /r /t 5")
    return {"status": "restart_initiated"}

# --- 5. ARAYÜZ (GUI) ---
log_area = None
def log(message):
    print(message)
    if log_area:
        try:
            log_area.config(state='normal')
            log_area.insert(tk.END, message + "\n")
            log_area.see(tk.END)
            log_area.config(state='disabled')
        except: pass

def start_gui():
    global log_area
    window = tk.Tk()
    window.title("PC Remote Server v1.1")
    window.geometry("500x450")
    
    tk.Label(window, text="PC Sunucusu Aktif", font=("Segoe UI", 16, "bold"), fg="#2E7D32").pack(pady=10)
    
    ip = get_local_ip()
    tk.Label(window, text=f"IP: {ip} | Port: {SERVER_PORT}", font=("Consolas", 12)).pack()
    tk.Label(window, text="Otomatik bulma için telefon ve PC aynı Wi-Fi'da olmalı.", fg="gray").pack()
    
    log_area = scrolledtext.ScrolledText(window, width=55, height=15, state='disabled', font=("Consolas", 9))
    log_area.pack(pady=10)
    
    log("✅ Sunucu başlatıldı.")
    log(f"📡 API Hazır: http://{ip}:{SERVER_PORT}")

    window.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))
    window.mainloop()

if __name__ == "__main__":
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()
    
    add_firewall_rule()
    threading.Thread(target=lambda: uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="error"), daemon=True).start()
    threading.Thread(target=start_udp_listener, daemon=True).start()
    start_gui()