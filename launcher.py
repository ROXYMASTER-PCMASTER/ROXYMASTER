"""launcher para server.py en segundo plano en pcmaster"""
import subprocess
import os

server_script = r"C:\users\pcmaster\desktop\roxymaster\pcmaster\scripts\server.py"
log_file = r"C:\users\pcmaster\desktop\roxymaster\server.log"

subprocess.Popen(
    ["python", server_script],
    stdout=open(log_file, "w"),
    stderr=subprocess.STDOUT,
    creationflags=subprocess.DETACHED_PROCESS,
    close_fds=True,
    cwd=os.path.dirname(server_script)
)
print("ok")