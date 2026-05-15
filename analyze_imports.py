import ast
import os
from collections import Counter

def find_local_imports(directory):
    local_imports = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    tree = ast.parse(content, filename=filepath)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            for child in ast.walk(node):
                                if isinstance(child, (ast.Import, ast.ImportFrom)):
                                    module_name = child.module if isinstance(child, ast.ImportFrom) else [n.name for n in child.names][0]
                                    local_imports.append({
                                        "file": filepath,
                                        "line": child.lineno,
                                        "module": module_name
                                    })
                except Exception as e:
                    pass
    return local_imports

all_local = find_local_imports("core") + find_local_imports("apps")
files_counter = Counter([item["file"] for item in all_local])
module_counter = Counter([str(item["module"]) for item in all_local])

print(f"Total local imports: {len(all_local)}")
print("\nTop 20 files with most local imports:")
for f, count in files_counter.most_common(20):
    print(f"{f}: {count}")

print("\nTop 20 most locally imported modules:")
for m, count in module_counter.most_common(20):
    print(f"{m}: {count}")
