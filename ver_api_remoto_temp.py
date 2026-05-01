import sys
sys.path.insert(0, r"C:\users\pcmaster\desktop\roxymaster\pcmaster\scripts")
import api_endpoints
import inspect

try:
    src = inspect.getsource(api_endpoints.register)
    print("=== FUNCION register ===")
    print(src)
except Exception as e:
    print("ERROR register:", e)

try:
    print("=== auth.registrar_usuario signature ===")
    import auth
    print(inspect.signature(auth.registrar_usuario))
except Exception as e:
    print("ERROR auth:", e)