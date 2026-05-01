import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
s.connect(('127.0.0.1', 5007))
s.sendall(b'estado\n')
r = b''
s.settimeout(5)
while True:
    try:
        c = s.recv(8192)
        if not c: break
        r += c
    except: break
s.close()
print("ESTADO:", r.decode('utf-8', errors='replace'))