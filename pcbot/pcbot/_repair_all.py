import os, sys, subprocess, ast

BASE = r"C:\Users\CYBER\Desktop\roxymaster\pcbot\scripts"

def check_file(fpath):
    """Returns True if file compiles, False + error if broken."""
    try:
        with open(fpath, encoding="utf-8") as f:
            source = f.read()
        ast.parse(source)
        return True, ""
    except SyntaxError as e:
        return False, str(e)

def find_broken():
    broken = []
    for root, dirs, files in os.walk(BASE):
        for f in files:
            if f.endswith(".py"):
                fpath = os.path.join(root, f)
                ok, err = check_file(fpath)
                if not ok:
                    broken.append((fpath, err))
    return broken

if __name__ == "__main__":
    broken = find_broken()
    if broken:
        print(f"{len(broken)} archivos rotos:")
        for fp, err in broken:
            print(f"  {fp}")
            print(f"    {err}")
    else:
        print("Todos los .py compilan sin errores.")