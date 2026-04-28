import paramiko

PASSWORD = r"Abc123$_"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('192.168.1.17', username='PCMASTER', password=PASSWORD, timeout=10, look_for_keys=False, allow_agent=False)

sftp = c.open_sftp()

# Download server.py
remote_server = '/Users/PCMASTER/Desktop/ROXYMASTER/PCMASTER/scripts/server.py'
local_server = r'C:\Users\CYBER\Desktop\server_remote.py'
sftp.get(remote_server, local_server)
print(f"Downloaded server.py ({sftp.stat(remote_server).st_size} bytes)")

# Download jarvis.py
remote_jarvis = '/Users/PCMASTER/Desktop/ROXYMASTER/PCMASTER/scripts/jarvis.py'
local_jarvis = r'C:\Users\CYBER\Desktop\jarvis_remote.py'
sftp.get(remote_jarvis, local_jarvis)
print(f"Downloaded jarvis.py ({sftp.stat(remote_jarvis).st_size} bytes)")

sftp.close()
c.close()
print("DONE")