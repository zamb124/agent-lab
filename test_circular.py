import os
import re

def move_imports_to_top(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    lines = content.split('\n')
    new_lines = []
    extracted_imports = []

    for line in lines:
        m = re.match(r'^(\s+)(import |from \S+ import )(.*)', line)
        if m and len(m.group(1)) > 0:
            extracted_imports.append(m.group(2) + m.group(3))
        else:
            new_lines.append(line)

    if not extracted_imports: return

    # find the end of top-level imports
    insert_idx = 0
    for i, line in enumerate(new_lines):
        if line.startswith('import ') or line.startswith('from '):
            insert_idx = i

    insert_idx += 1
    final_lines = new_lines[:insert_idx] + extracted_imports + new_lines[insert_idx:]
    with open(filepath, 'w') as f:
        f.write('\n'.join(final_lines))

move_imports_to_top("apps/flows/src/container.py")
