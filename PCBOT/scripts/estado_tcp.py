"""Consulta el estado del servidor via TCP admin (puerto 5007)."""
import socket
import time

def tcp_command(host, port, cmd, timeout=5):
    """Envía un comando al TCP admin y recibe toda la respuesta."""
    s = socket.socket()
    s.settimeout(timeout)
    s.connect((host, port))
    s.sendall((cmd + "\n").encode())

    # Esperar respuesta (el servidor envía en 2 partes para 'estado')
    time.sleep(0.6)
    data = b""
    while True:
        try:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        except:
            break
    s.close()
    return data.decode()

HOST = "192.168.1.17"
PORT = 5007

print("=" * 60)
print("  ESTADO ROXYMASTER")
print("=" * 60)
respuesta = tcp_command(HOST, PORT, "estado")
print(respuesta)

# Consultar perfiles
print("\n" + "-" * 40)
print("  PERFILES")
print("-" * 40)
respuesta = tcp_command(HOST, PORT, "perfiles")
print(respuesta)