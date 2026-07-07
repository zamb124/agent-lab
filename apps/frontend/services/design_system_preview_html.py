"""HTML shell for public UI Kit component playground preview."""

from __future__ import annotations

import html
import json

from core.frontend.viewport import PLATFORM_MOBILE_VIEWPORT_CONTENT
from core.types import JsonObject

_IMPORT_MAP_SCRIPT = (
    '<script type="importmap">'
    + json.dumps(
        {
            "imports": {
                "lit": "/static/core/assets/js/lit/lit.min.js",
                "lit/": "/static/core/assets/js/lit/",
                "@platform/lib/": "/static/core/lib/",
            },
        },
        separators=(",", ":"),
    )
    + "</script>"
)


def build_design_system_preview_html(
    *,
    component: str,
    variant_id: str,
    import_path: str,
    props: JsonObject,
    title: str,
) -> str:
    safe_title = html.escape(title, quote=True)
    props_json = json.dumps(props, ensure_ascii=False)
    import_json = json.dumps(import_path, ensure_ascii=False)
    component_json = json.dumps(component, ensure_ascii=False)
    variant_json = json.dumps(variant_id, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ru" data-theme="light">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="{PLATFORM_MOBILE_VIEWPORT_CONTENT}" />
  <meta name="color-scheme" content="light" />
  <title>{safe_title} — UI Kit preview</title>
  <link rel="stylesheet" href="/static/core/assets/css/tokens.css" />
  <style>
    html, body {{
      margin: 0;
      min-height: 100%;
      background: var(--bg-primary, #fff);
      color: var(--text-primary, #111);
    }}
    ui-kit-root {{
      display: block;
      padding: var(--space-6, 24px);
      max-width: 960px;
      margin: 0 auto;
    }}
  </style>
  {_IMPORT_MAP_SCRIPT}
</head>
<body>
  <ui-kit-root data-testid="ui-kit-root">
    <div id="mount"></div>
  </ui-kit-root>
  <script type="module">
    const componentTag = {component_json};
    const importPath = {import_json};
    const props = {props_json};

    await import(importPath);
    const mount = document.querySelector('#mount');
    if (!mount) {{
      throw new Error('ui-kit mount node missing');
    }}

    const el = document.createElement(componentTag);
    for (const [key, value] of Object.entries(props)) {{
      if (value === null || value === undefined) {{
        continue;
      }}
      if (typeof value === 'object') {{
        el[key] = value;
        continue;
      }}
      if (typeof value === 'boolean') {{
        if (value) {{
          el.setAttribute(key, '');
        }}
        continue;
      }}
      el.setAttribute(key, String(value));
    }}
    mount.appendChild(el);
    window.__UI_KIT_PREVIEW__ = {{ component: componentTag, variant: {variant_json}, props }};
  </script>
</body>
</html>
"""
