"""Экран после заказа: номер, живой статус по polling.

Блок собирается реестром STOREFRONT_BLOCKS; css/js вставляются
в shell как есть — без экранирования скобок.
"""

CSS: str = """.done{text-align:center;padding:64px 20px}
.done .code{font-size:36px;font-weight:750;color:var(--afg);margin:16px 0;letter-spacing:.02em}
.done .st{font-size:14px;font-weight:650;color:var(--afg);background:color-mix(in srgb,var(--accent) 14%,transparent);display:inline-block;padding:6px 16px;border-radius:99px;margin-bottom:14px}
.done p{color:var(--muted);font-size:14.5px;line-height:1.6}
.pbadge{display:inline-block;margin-left:8px;padding:3px 10px;border-radius:99px;background:var(--accent);color:var(--on-accent);font-size:11px;font-weight:700;vertical-align:middle;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ptag{display:inline-flex;align-items:center;gap:4px;margin-left:6px;padding:3px 9px;border-radius:99px;background:color-mix(in srgb,var(--accent) 13%,transparent);color:var(--afg);font-size:10.5px;font-weight:700;vertical-align:middle;white-space:nowrap}
.ptag svg{width:12px;height:12px;fill:currentColor;flex-shrink:0}
.save{color:var(--success)}
.save b{color:var(--success)}
.empty{text-align:center;color:var(--muted);padding:60px 20px;font-size:15px}"""

JS: str = """window.trackOrder=async(code,created)=>{
  const p=document.getElementById('panel');
  const render=d=>{const hall=d&&d.delivery_type==='onsite'&&d.table_label?`<br>Ваш стол: ${esc(d.table_label)}`:'';
    p.innerHTML=`<div class="done"><h2>Заказ принят!</h2><div class="code">#${code}</div><div class="st">${esc(d.status_label||d.status)}</div><p>Сохраните номер заказа — по нему можно проверить статус.${hall}<br>Мы свяжемся с вами для подтверждения.</p></div>`;};
  render(created);
  const poll=async()=>{
    if(!document.getElementById('sheet').classList.contains('show'))return;
    try{
      const r=await fetch(`/shop/api/v1/public/orders/${code}`);
      if(r.ok){const d=await r.json();render(d);if(d.status!=='done'&&d.status!=='cancelled')setTimeout(poll,15000);}
      else setTimeout(poll,30000);
    }catch(e){setTimeout(poll,30000);}
  };
  setTimeout(poll,15000);
};"""
