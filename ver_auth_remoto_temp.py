import sys
sys.path.insert(0, r"C:\users\pcmaster\desktop\roxymaster\pcmaster\scripts")
import auth
import inspect
src = inspect.getsource(auth.registrar_usuario)
print(src)
print("---")
src2 = inspect.getsource(auth.AuthManager.registrar)
print(src2)