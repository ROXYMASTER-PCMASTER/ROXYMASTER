import ctypes
import ctypes.wintypes
import paramiko
import os
import sys

CRED_TYPE_DOMAIN_PASSWORD = 0x2
advapi32 = ctypes.windll.advapi32

# Usar CredReadW con la estructura correcta para 64-bit
# CREDENTIAL struct layout (64-bit):
#   DWORD Flags;        (4 bytes, offset 0)
#   DWORD Type;         (4 bytes, offset 4)
#   LPWSTR TargetName;  (8 bytes, offset 8)
#   LPWSTR Comment;     (8 bytes, offset 16)
#   FILETIME LastWritten; (8 bytes, offset 24)
#   DWORD CredentialBlobSize; (4 bytes, offset 32)
#   LPBYTE CredentialBlob;    (8 bytes, offset 40)  (align 8?)
#   DWORD Persist;      (4 bytes, offset 48)
#   DWORD AttributeCount; (4 bytes, offset 52)
#   PCREDENTIAL_ATTRIBUTE Attributes; (8 bytes, offset 56)
#   LPWSTR TargetAlias; (8 bytes, offset 64)
#   LPWSTR UserName;    (8 bytes, offset 72)

class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = []

advapi32.CredReadW.argtypes = [
    ctypes.wintypes.LPWSTR,
    ctypes.wintypes.DWORD,
    ctypes.wintypes.DWORD,
    ctypes.POINTER(ctypes.c_void_p)
]
advapi32.CredReadW.restype = ctypes.wintypes.BOOL

def read_password():
    pcred = ctypes.c_void_p()
    target = 'Domain:target=192.168.1.17'
    if not advapi32.CredReadW(target, CRED_TYPE_DOMAIN_PASSWORD, 0, ctypes.byref(pcred)):
        err = ctypes.get_last_error()
        print(f'CredReadW failed with error {err}')
        return None
    
    ptr = pcred.value
    
    # Leer CredentialBlobSize en offset 32 (4 bytes)
    blob_size = ctypes.cast(ptr + 32, ctypes.POINTER(ctypes.c_uint32)).contents.value
    print(f'CredentialBlobSize: {blob_size}')
    
    # Leer CredentialBlob pointer en offset 40 (8 bytes en 64-bit)
    blob_ptr_ptr = ctypes.cast(ptr + 40, ctypes.POINTER(ctypes.c_void_p))
    blob_ptr = blob_ptr_ptr.contents.value
    
    if blob_size == 0 or blob_ptr is None:
        print(f'No blob data: size={blob_size}, ptr={blob_ptr}')
        advapi32.CredFree(pcred)
        return None
    
    # La contraseña es Unicode (WCHAR = 2 bytes por carácter)
    char_count = blob_size // 2
    print(f'Attempting to read {char_count} WCHARs')
    password = ctypes.wstring_at(blob_ptr, char_count)
    
    advapi32.CredFree(pcred)
    return password

password = read_password()
if password:
    print(f'Password obtained ({len(password)} chars)')
    
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect('192.168.1.17', username='PCMASTER', password=password, timeout=10, look_for_keys=False, allow_agent=False)
        print('SSH connected!')
        stdin, stdout, stderr = c.exec_command('whoami && hostname')
        print('STDOUT:', stdout.read().decode().strip())
        err = stderr.read().decode().strip()
        if err:
            print('STDERR:', err)
        c.close()
        
        # Ahora leer server.py remoto
        print('\n--- Leyendo server.py remoto ---')
        c2 = paramiko.SSHClient()
        c2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c2.connect('192.168.1.17', username='PCMASTER', password=password, timeout=10, look_for_keys=False, allow_agent=False)
        sftp = c2.open_sftp()
        remote_path = '/C:/Users/CYBER/Desktop/ROXYMASTER/PCMASTER/scripts/server.py'
        try:
            with sftp.file(remote_path, 'r') as f:
                lines = f.readlines()
                print(f'server.py: {len(lines)} lineas')
                # Print first 60 lines
                for i, line in enumerate(lines[:60]):
                    print(f'{i+1}: {line.rstrip()}')
        except FileNotFoundError:
            # Try different path
            remote_path = '/Users/PCMASTER/Desktop/ROXYMASTER/PCMASTER/scripts/server.py'
            try:
                with sftp.file(remote_path, 'r') as f:
                    lines = f.readlines()
                    print(f'server.py: {len(lines)} lineas')
                    for i, line in enumerate(lines[:60]):
                        print(f'{i+1}: {line.rstrip()}')
            except FileNotFoundError:
                print('server.py NOT FOUND on remote')
                sftp.chdir('/Users/PCMASTER/Desktop')
                print('Files in /Users/PCMASTER/Desktop:')
                for f in sftp.listdir():
                    print(f'  {f}')
        sftp.close()
        c2.close()
        
    except Exception as e:
        print(f'SSH Error: {e}')
        import traceback
        traceback.print_exc()
else:
    print('Failed to obtain password')