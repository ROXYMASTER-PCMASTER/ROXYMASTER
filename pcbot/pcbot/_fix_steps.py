"""fix steps 2 y 3: sys.path en main.py + ip tailscale en ws_client.py"""
import re, os

base = r'c:\Users\CYBER\Desktop\roxymaster\pcbot\scripts'

# --- paso 2: añadir sys.path.insert en main.py ---
path_main = os.path.join(base, 'main.py')
with open(path_main, 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
insert_at = 0
for i, line in enumerate(lines):
    if line.startswith('import ') or line.startswith('from '):
        insert_at = i + 1
    elif line.strip() and not line.startswith('#'):
        break

sys_lines = [
    'import sys, os',
    'sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))',
]
for sl in sys_lines:
    if sl not in content:
        lines.insert(insert_at, sl)
        insert_at += 1

new_content = '\n'.join(lines)
with open(path_main, 'w', encoding='utf-8', newline='') as f:
    f.write(new_content)
print('paso 2: sys.path.insert añadido a main.py')

# --- paso 3: cambiar ip en ws_client.py ---
path_ws = os.path.join(base, 'api', 'ws_client.py')
with open(path_ws, 'r', encoding='utf-8') as f:
    ws_content = f.read()

ips_found = re.findall(r'ws://[\d.]+:\d+', ws_content)
print(f'ips ws actuales: {ips_found}')

old_ip = '192.168.1.17'
new_ip = '100.111.179.65'
if old_ip in ws_content:
    ws_content = ws_content.replace(old_ip, new_ip)
    with open(path_ws, 'w', encoding='utf-8', newline='') as f:
        f.write(ws_content)
    print(f'paso 3: ip cambiada {old_ip} -> {new_ip}')
elif new_ip in ws_content:
    print(f'paso 3: ip tailscale {new_ip} ya configurada')
else:
    all_ws = re.findall(r'ws://[^:]+:\d+', ws_content)
    print(f'paso 3: otras ips: {all_ws}')
    if all_ws:
        for ip in set(all_ws):
            ws_content = ws_content.replace(ip, f'ws://{new_ip}:5006')
        with open(path_ws, 'w', encoding='utf-8', newline='') as f:
            f.write(ws_content)
        print(f'paso 3: ips reemplazadas por {new_ip}')
    else:
        print('paso 3: no se encontro ninguna ip ws')

print('done - pasos 2 y 3 completados')