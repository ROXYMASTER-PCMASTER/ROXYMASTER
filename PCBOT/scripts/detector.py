import socket, os, requests
def detectar_info_sistema():
    hostname = os.environ.get("COMPUTERNAME", "pcbot")
    username = os.environ.get("USERNAME", "")
    ip_local = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_local = s.getsockname()[0]
        s.close()
    except: pass
    return {"hostname": hostname, "username": username, "ip_local": ip_local}

def detectar_roxybrowser():
    try:
        r = requests.get("http://127.0.0.1:50000/api/browsers", timeout=5)
        if r.status_code == 200:
            perfiles = r.json() if isinstance(r.json(), list) else []
            return {"detectado": True, "perfiles": [{"id": p.get("id"), "name": p.get("name")} for p in perfiles]}
    except: pass
    return {"detectado": False, "perfiles": []}