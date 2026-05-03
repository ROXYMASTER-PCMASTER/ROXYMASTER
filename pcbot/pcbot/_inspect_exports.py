import ast, sys, os
sys.path.insert(0, r"C:\Users\CYBER\Desktop\roxymaster\pcbot\scripts")

targets = ["config_loader", "auto_detect", "roxybrowser_api", "profile_manager",
           "state_tracker", "token_engine", "ws_client", "http_portal"]

for mod_name in targets:
    fpath = os.path.join(r"C:\Users\CYBER\Desktop\roxymaster\pcbot\scripts", mod_name + ".py")
    if not os.path.exists(fpath):
        print(f"{mod_name}: NOT FOUND")
        continue
    with open(fpath, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    names = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
    print(f"{mod_name}: {names}")