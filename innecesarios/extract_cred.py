import ctypes
from ctypes import wintypes
import sys

class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ('Flags', wintypes.DWORD),
        ('Type', wintypes.DWORD),
        ('TargetName', wintypes.LPWSTR),
        ('Comment', wintypes.LPWSTR),
        ('LastWritten', ctypes.c_ulonglong),
        ('CredentialBlobSize', wintypes.DWORD),
        ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)),
        ('Persist', wintypes.DWORD),
        ('AttributeCount', wintypes.DWORD),
        ('Attributes', ctypes.c_void_p),
        ('TargetAlias', wintypes.LPWSTR),
        ('UserName', wintypes.LPWSTR),
    ]

advapi32 = ctypes.windll.advapi32
advapi32.CredReadW.restype = wintypes.BOOL
advapi32.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]

# Try both target formats
targets = [
    'Domain:target=192.168.1.17',
    '192.168.1.17',
    'Domain:target=TERMSRV/192.168.1.17',
    'TERMSRV/192.168.1.17',
]

for target in targets:
    pcred = ctypes.c_void_p()
    result = advapi32.CredReadW(target, 1, 0, ctypes.byref(pcred))
    if result:
        cred = ctypes.cast(pcred, ctypes.POINTER(CREDENTIALW)).contents
        username = cred.UserName
        blob_size = cred.CredentialBlobSize
        try:
            password = ctypes.string_at(cred.CredentialBlob, blob_size).decode('utf-16-le')
        except:
            password = "BINARY_DATA"
        print(f"TARGET: {target}")
        print(f"USER: {username}")
        print(f"PASS: {password}")
        print("---")
        advapi32.CredFree(pcred)
    else:
        err = ctypes.get_last_error()
        print(f"TARGET: {target} -> ERROR: {err}")