"""script de depuracion para iniciar el servidor y capturar errores."""
import subprocess
import sys
import os
import time

os.chdir(r"C:\users\pcmaster\desktop\roxymaster\pcmaster")

print("=== verificando import de server ===")
sys.path.insert(0, r"C:\users\pcmaster\desktop\roxymaster\pcmaster\scripts")
try:
    import server
    print("server importado correctamente")
except Exception as e:
    print(f"ERROR FATAL importando server: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n=== intentando iniciar asyncio manualmente ===")
try:
    import asyncio
    asyncio.run(server.main())
except Exception as e:
    print(f"ERROR FATAL al iniciar: {e}")
    import traceback
    traceback.print_exc()