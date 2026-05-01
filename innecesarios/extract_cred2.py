import ctypes
from ctypes import wintypes

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
advapi32.CredEnumerateW.restype = wintypes.BOOL
advapi32.CredEnumerateW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_void_p)]
advapi32.CredReadW.restype = wintypes.BOOL
advapi32.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
advapi32.CredFree.restype = None
advapi32.CredFree.argtypes = [ctypes.c_void_p]

count = wintypes.DWORD()
pcreds = ctypes.c_void_p()

if advapi32.CredEnumerateW(None, 0, ctypes.byref(count), ctypes.byref(pcreds)):
    num = count.value
    print(f"Found {num} credentials:\n")
    # pcreds is a pointer to an array of PCREDENTIALW pointers
    ptr_size = ctypes.sizeof(ctypes.c_void_p)
    for i in range(num):
        cred_ptr = ctypes.cast(pcreds.value + i * ptr_size, ctypes.POINTER(ctypes.c_void_p)).contents
        cred = ctypes.cast(cred_ptr, ctypes.POINTER(CREDENTIALW)).contents
        target = cred.TargetName
        username = cred.UserName
        ptype = cred.Type
        blob_size = cred.CredentialBlobSize
        try:
            password = ctypes.string_at(cred.CredentialBlob, blob_size).decode('utf-16-le')
        except:
            password = "<binary>"
        print(f"  [{i}] Target: {target}")
        print(f"      User: {username}")
        print(f"      Type: {ptype} (1=GENERIC, 2=DOMAIN_PASSWORD, 3=DOMAIN_CERTIFICATE)")
        print(f"      Pass: {password}")
        print()
    advapi32.CredFree(pcreds)
else:
    err = ctypes.get_last_error()
    print(f"CredEnumerateW failed: {err}")