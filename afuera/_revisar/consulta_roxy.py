import sqlite3, requests, sys

API_KEY = sys.argv[1] if len(sys.argv) > 1 else "8ce112f7ebbb0fba6e9e290194f8e117"
DB_PATH = r"C:\Users\PCMASTER\Desktop\roxymaster\pcmaster\data\roxymaster.db"

# Consultar RoxyBrowser
resp = requests.get("http://127.0.0.1:50000/api/browsers", headers={"x-api-key": API_KEY})
if resp.status_code != 200:
    print("Error al consultar RoxyBrowser:", resp.status_code, resp.text)
    sys.exit(1)
data = resp.json()
print("Respuesta de RoxyBrowser:", data)

# Conectar a BD
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
# Buscar el último perfil insertado (el que acaba de crearse con estado 'consultando')
c.execute("SELECT id FROM perfiles WHERE estado='consultando' ORDER BY id DESC LIMIT 1")
row = c.fetchone()
if not row:
    print("No hay perfil en estado 'consultando'. Ingresa primero la API Key desde el modal.")
    sys.exit(1)
perfil_id = row[0]

workspace = data.get("workspace_id", "")
hash_id = data.get("hash_id", "")
name_id = data.get("name_id", "")
total = data.get("total", len(data.get("browsers", [])))

# Actualizar perfil
c.execute("UPDATE perfiles SET nombre_perfil=?, workspace_id=?, hash_id=?, name_id=?, total_perfiles_roxy=?, estado='activo' WHERE id=?",
          (name_id, workspace, hash_id, name_id, total, perfil_id))
# Insertar perfiles hijos si vienen en 'browsers'
for browser in data.get("browsers", []):
    c.execute("INSERT INTO perfiles_roxy (perfil_id, nombre, estado) VALUES (?, ?, ?)",
              (perfil_id, browser.get("name", ""), browser.get("status", "desconocido")))
conn.commit()
conn.close()
print(f"Perfil {perfil_id} actualizado con datos reales: {total} perfiles.")
