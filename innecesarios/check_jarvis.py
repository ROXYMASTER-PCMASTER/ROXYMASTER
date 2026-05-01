import socket

def enviar(cmd):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect(('127.0.0.1', 5007))
    s.sendall((cmd + '\n').encode())
    r = b''
    s.settimeout(5)
    while True:
        try:
            c = s.recv(8192)
            if not c: break
            r += c
        except: break
    s.close()
    return r.decode('utf-8', errors='replace')

print("=== JARVIS (últimos 10) ===")
print(enviar('jarvis 10'))
print("\n=== GRUPOS ===")
print(enviar('grupos'))
print("\n=== COMENTARIOS ACTIVAR ===")
print(enviar('comentarios_activar'))