import ast, os

base = r"C:\Users\CYBER\Desktop\roxymaster\pcbot\scripts"
mods = {
    os.path.join("api", "roxybrowser_api.py"): "RoxyBrowserAPI",
    os.path.join("api", "ws_client.py"): "WSClient",
    os.path.join("core", "profile_manager.py"): "ProfileManager",
    os.path.join("core", "state_tracker.py"): "StateTracker",
    os.path.join("core", "token_engine.py"): "TokenEngine",
    "http_portal.py": "PortalServer",
    "auto_detect.py": "AutoDetect",
    "shs.py": "",
}

for fname, expected in mods.items():
    fpath = os.path.join(base, fname)
    if not os.path.exists(fpath):
        print(f"{fname}: NOT FOUND")
        continue
    with open(fpath, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    funcs = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    vars_ = [t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)]
    print(f"{fname}: classes={classes}, funcs={funcs[:6]}, vars={vars_[:6]}")