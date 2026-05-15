import re
import os

def fix_imports(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    imports = set()
    new_lines = []
    
    for line in lines:
        match = re.match(r'^(\s+)(import |from \S+ import )(.+)', line)
        if match and len(match.group(1)) > 0:
            imports.add(match.group(2) + match.group(3))
            continue
        new_lines.append(line)
        
    if not imports:
        return
        
    last_import_idx = 0
    for i, line in enumerate(new_lines):
        if line.startswith("import ") or line.startswith("from "):
            last_import_idx = i
            
    insert_lines = [imp for imp in sorted(list(imports))]
    
    final_lines = new_lines[:last_import_idx+1] + insert_lines + new_lines[last_import_idx+1:]
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(final_lines)

fix_imports("apps/flows/src/container.py")
