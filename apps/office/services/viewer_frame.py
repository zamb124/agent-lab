"""HTML bridge для viewer iframe (image/media/text/binary)."""

from __future__ import annotations

import html

from core.documents.viewer.models import OfficeViewerStreamTokenClaims


def render_viewer_frame_html(
    *,
    claims: OfficeViewerStreamTokenClaims,
    stream_url: str,
    save_url: str,
    title: str,
) -> str:
    handler = claims.handler
    safe_title = html.escape(title)
    safe_stream = html.escape(stream_url, quote=True)
    if handler == "image":
        body = f"""
        <style>
          html, body {{ margin: 0; height: 100%; background: #0f172a; display: flex; align-items: center; justify-content: center; }}
          img {{ max-width: 100%; max-height: 100%; object-fit: contain; }}
        </style>
        <img src="{safe_stream}" alt="{safe_title}" />
        """
    elif handler == "media":
        if claims.content_type.startswith("video/"):
            body = f"""
            <style>html, body {{ margin: 0; height: 100%; background: #000; }}
            video {{ width: 100%; height: 100%; }}</style>
            <video controls src="{safe_stream}"></video>
            """
        else:
            body = f"""
            <style>html, body {{ margin: 0; height: 100%; display: flex; align-items: center; justify-content: center; background: #111827; }}
            audio {{ width: min(640px, 92vw); }}</style>
            <audio controls src="{safe_stream}"></audio>
            """
    elif handler == "text":
        if claims.edit_mode and save_url:
            body = f"""
            <style>
              html, body {{ margin: 0; height: 100%; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
              #toolbar {{ padding: 8px 12px; border-bottom: 1px solid #334155; background: #1e293b; display: flex; gap: 8px; }}
              #editor {{ width: 100%; height: calc(100% - 49px); border: 0; padding: 12px; box-sizing: border-box; resize: none; }}
              button {{ background: #6284e8; color: #fff; border: 0; border-radius: 6px; padding: 6px 12px; cursor: pointer; }}
            </style>
            <div id="toolbar"><button type="button" id="save">Save</button><span id="status"></span></div>
            <textarea id="editor"></textarea>
            <script>
              const streamUrl = {json_string(stream_url)};
              const saveUrl = {json_string(save_url)};
              const editor = document.getElementById('editor');
              const statusEl = document.getElementById('status');
              fetch(streamUrl).then(r => r.text()).then(t => {{ editor.value = t; }});
              document.getElementById('save').addEventListener('click', async () => {{
                statusEl.textContent = 'Saving...';
                const resp = await fetch(saveUrl, {{ method: 'POST', headers: {{ 'Content-Type': 'text/plain; charset=utf-8' }}, body: editor.value }});
                if (!resp.ok) {{ statusEl.textContent = 'Save failed'; return; }}
                statusEl.textContent = 'Saved';
              }});
            </script>
            """
        else:
            body = f"""
            <style>
              html, body {{ margin: 0; height: 100%; }}
              pre {{ margin: 0; padding: 12px; height: 100%; box-sizing: border-box; overflow: auto; white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
            </style>
            <pre id="content"></pre>
            <script>
              fetch({json_string(stream_url)}).then(r => r.text()).then(t => {{ document.getElementById('content').textContent = t; }});
            </script>
            """
    elif handler == "binary":
        body = f"""
        <style>
          html, body {{ margin: 0; height: 100%; font-family: system-ui, sans-serif; background: #f8fafc; color: #0f172a; }}
          .wrap {{ display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 16px; padding: 24px; box-sizing: border-box; text-align: center; }}
          a {{ background: #6284e8; color: #fff; text-decoration: none; border-radius: 8px; padding: 10px 16px; }}
        </style>
        <div class="wrap">
          <h1>{safe_title}</h1>
          <p>{html.escape(claims.content_type)}</p>
          <a href="{html.escape(stream_url, quote=True)}" download>Download</a>
        </div>
        """
    else:
        raise ValueError(f"Unsupported viewer frame handler: {handler}")
    return f"<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>{safe_title}</title></head><body>{body}</body></html>"


def json_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
    return f"'{escaped}'"
