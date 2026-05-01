import socket, time, sys

def enviar(cmd):
    try:
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
            except:
                break
        s.close()
        return r.decode('utf-8', errors='replace')
    except Exception as e:
        return f'[ERROR] {e}'

comandos = ['perfiles', 'estado', 'grupos', 'ayuda']
for cmd in comandos:
    print(f'\n=== COMANDO: {cmd} ===')
    print(enviar(cmd))
    time.sleep(0.3)

# Asignar kick
print('\n=== ASIGNANDO A KICK.COM/PAYASITAZING ===')
print(enviar('asignar 2 url https://kick.com/payasitazing duracion 5 nivel alto'))
time.sleep(2)

print('\n=== VERIFICANDO GRUPOS ===')
print(enviar('grupos'))
time.sleep(1)

# Monitorear 60 segundos (3 checks de 20s)
for i in range(3):
    time.sleep(20)
    r = enviar('estado')
    for line in r.split('\n'):
        if 'comentarios' in line.lower() or 'jarvis' in line.lower() or 'envio' in line.lower():
            print(f'  [min {i+1}] {line.strip()}')

print('\n=== ESTADO FINAL ===')
print(enviar('estado'))
print('\nPRUEBA COMPLETA.')