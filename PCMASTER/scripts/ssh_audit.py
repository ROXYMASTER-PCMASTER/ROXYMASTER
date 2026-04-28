import paramiko
import sys
import os

PASSWORD = r"Abc123$_"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    c.connect('192.168.1.17', username='PCMASTER', password=PASSWORD, timeout=10, look_for_keys=False, allow_agent=False)
    print("SSH_CONNECTED")
    
    # Test basic command
    stdin, stdout, stderr = c.exec_command('whoami && hostname')
    out = stdout.read().decode().strip()
    print(f"REMOTE: {out}")
    
    # Find ROXYMASTER path
    stdin, stdout, stderr = c.exec_command('dir /s /b "%USERPROFILE%\\Desktop\\ROXYMASTER\\PCMASTER\\scripts\\server.py" 2>nul || echo NOT_FOUND')
    server_path = stdout.read().decode().strip()
    print(f"sERVER_PATH: {server_path}")
    
    # Find jarvis
    stdin, stdout, stderr = c.exec_command('dir /s /b "%USERPROFILE%\\Desktop\\ROXYMASTER\\PCMASTER\\scripts\\jarvis*.py" 2>nul || echo NOT_FOUND')
    jarvis_paths = stdout.read().decode().strip()
    print(f"JARVIS_PATHS: {jarvis_paths}")
    
except Exception as e:
    print(f"SSH_ERROR: {e}")
finally:
    c.close()