"""Storefront shell — HTML-страница витрины с inline-снапшотом.

Отдаётся анонимно на ``/s/{slug}``: снапшот из Redis встраивается в HTML
одним JSON-блоком, клиентский JS рендерит меню и корзину без SPA-сборки.
SSR-lite: первый байт уже содержит всё меню — SEO и скорость из коробки.
"""

from __future__ import annotations

import json
from html import escape

from core.types import JsonObject

_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<style>
:root{{--accent:{accent};--bg:#0f0e0c;--card:#1a1815;--text:#f5f1ea;--muted:#a89f93;--radius:18px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:ui-serif,Georgia,'Times New Roman',serif;background:var(--bg);color:var(--text);min-height:100vh}}
.wrap{{max-width:680px;margin:0 auto;padding:0 16px 140px}}
.hero{{position:relative;margin:0 -16px;height:220px;overflow:hidden;background:linear-gradient(160deg,var(--accent) 0%,#2a2118 70%)}}
.hero img{{width:100%;height:100%;object-fit:cover;opacity:.85}}
.hero h1{{position:absolute;bottom:16px;left:24px;font-size:32px;font-weight:600;text-shadow:0 2px 12px rgba(0,0,0,.6)}}
.meta{{padding:16px 0 8px;color:var(--muted);font-size:14px;display:flex;gap:16px;flex-wrap:wrap}}
.tabs{{position:sticky;top:0;z-index:5;display:flex;gap:8px;overflow-x:auto;padding:12px 0;background:var(--bg);scrollbar-width:none}}
.tabs button{{font:inherit;font-size:15px;padding:8px 16px;border-radius:99px;border:1px solid #333;color:var(--muted);background:var(--card);cursor:pointer;white-space:nowrap}}
.tabs button.on{{background:var(--accent);border-color:var(--accent);color:#fff}}
.cat{{font-size:22px;margin:26px 0 12px}}
.item{{display:flex;gap:14px;padding:14px 0;border-bottom:1px solid #262019}}
.item img{{width:86px;height:86px;border-radius:var(--radius);object-fit:cover;background:#241f19}}
.item .b{{flex:1}}
.item h3{{font-size:17px;font-weight:600}}
.item p{{font-size:13.5px;color:var(--muted);margin-top:4px;line-height:1.45}}
.item .row{{display:flex;justify-content:space-between;align-items:center;margin-top:10px}}
.price{{font-size:17px;font-weight:600}}
.add{{font:inherit;font-size:14px;font-weight:600;padding:8px 18px;border-radius:99px;border:0;background:var(--accent);color:#fff;cursor:pointer}}
.add:active{{transform:scale(.96)}}
.cart{{position:fixed;left:50%;transform:translateX(-50%);bottom:18px;width:min(648px,92vw);background:var(--accent);color:#fff;border:0;font:inherit;font-size:16px;font-weight:600;padding:16px;border-radius:99px;cursor:pointer;display:none;box-shadow:0 8px 32px rgba(0,0,0,.5);z-index:10}}
.cart.show{{display:block}}
.sheet{{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;z-index:20}}
.sheet.show{{display:block}}
.panel{{position:absolute;left:50%;transform:translateX(-50%);bottom:0;width:min(680px,100vw);max-height:85vh;overflow:auto;background:var(--card);border-radius:24px 24px 0 0;padding:20px 20px 40px}}
.panel h2{{font-size:20px;margin-bottom:14px}}
.cl{{display:flex;justify-content:space-between;padding:8px 0;font-size:15px}}
.cl input{{width:40px}}
input.f{{width:100%;font:inherit;padding:12px;margin:6px 0;border-radius:12px;border:1px solid #333;background:#12100d;color:var(--text)}}
button.big{{width:100%;font:inherit;font-size:16px;font-weight:600;padding:14px;border-radius:14px;border:0;background:var(--accent);color:#fff;cursor:pointer;margin-top:10px}}
.done{{text-align:center;padding:60px 20px}}
.done .code{{font-size:34px;font-weight:700;color:var(--accent);margin:14px 0}}
</style>
</head>
<body>
<div class="wrap" id="app"></div>
<button class="cart" id="cart" onclick="openSheet()"></button>
<div class="sheet" id="sheet" onclick="if(event.target===this)closeSheet()"><div class="panel" id="panel"></div></div>
<script id="snapshot" type="application/json">{snapshot}</script>
<script>
const S=JSON.parse(document.getElementById('snapshot').textContent);
const fmt=v=>(v/100).toLocaleString('ru-RU')+' ₽';
const cart=new Map();
const app=document.getElementById('app');
function money(u){{return u?`<img src="/api/v1/files/download/${{u}}" loading="lazy" alt="">`:''}}
function render(){{
  let h=`<div class="hero">${{money(S.cover_file_id)}}<h1>${{S.name}}</h1></div>
  <div class="meta">${{S.address?`<span>${{S.address}}</span>`:''}}${{S.phone?`<span>${{S.phone}}</span>`:''}}</div>`;
  const cats=S.categories.filter(c=>S.products.some(p=>p.category_id===c.id));
  const other=S.products.filter(p=>!p.category_id);
  h+=`<div class="tabs">${{cats.map(c=>`<button onclick="location.hash='${{c.id}}'">${{c.name}}</button>`).join('')}}${{other.length?`<button onclick="location.hash='other'">Ещё</button>`:''}}</div>`;
  for(const c of cats){{h+=`<h2 class="cat" id="${{c.id}}">${{c.name}}</h2>`+items(S.products.filter(p=>p.category_id===c.id));}}
  if(other.length){{h+=`<h2 class="cat" id="other">Ещё</h2>`+items(other);}}
  app.innerHTML=h;
}}
function items(ps){{return ps.map(p=>`<div class="item">${{money(p.photo_file_id)}}<div class="b"><h3>${{p.name}}</h3>${{p.description?`<p>${{p.description}}</p>`:''}}<div class="row"><span class="price">${{fmt(p.price_minor)}}</span><button class="add" onclick="add('${{p.id}}')">В корзину</button></div></div></div>`).join('');}}
window.add=(id)=>{{cart.set(id,(cart.get(id)||0)+1);draw();}};
function total(){{let t=0;for(const [id,q] of cart){{const p=S.products.find(x=>x.id===id);if(p)t+=p.price_minor*q;}}return t;}}
function draw(){{const b=document.getElementById('cart');const n=[...cart.values()].reduce((a,x)=>a+x,0);if(n){{b.textContent=`Корзина · ${{fmt(total())}} →`;b.classList.add('show');}}else b.classList.remove('show');}}
window.openSheet=()=>{{
  const p=document.getElementById('panel');
  p.innerHTML=`<h2>Ваш заказ</h2>`+[...cart.entries()].map(([id,q])=>{{const x=S.products.find(i=>i.id===id);return x?`<div class="cl"><span>${{x.name}} × ${{q}}</span><b>${{fmt(x.price_minor*q)}}</b></div>`:'';}}).join('')+
  `<div class="cl"><span>Доставка</span><b>${{fmt(S.delivery_fee_minor)}}</b></div><div class="cl"><b>Итого</b><b>${{fmt(total()+S.delivery_fee_minor)}}</b></div>
  <input class="f" id="cn" placeholder="Имя"><input class="f" id="cp" placeholder="Телефон">
  <input class="f" id="ca" placeholder="Адрес доставки (пусто = самовывоз)"><input class="f" id="cc" placeholder="Комментарий">
  <button class="big" onclick="submit()">Оформить заказ</button>`;
  document.getElementById('sheet').classList.add('show');
}};
window.closeSheet=()=>document.getElementById('sheet').classList.remove('show');
window.submit=async()=>{{
  const body={{items:[...cart.entries()].map(([id,qty])=>({{product_id:id,qty}})),
    customer_name:document.getElementById('cn').value,customer_phone:document.getElementById('cp').value,
    delivery_type:document.getElementById('ca').value?'delivery':'pickup',
    address:document.getElementById('ca').value,comment:document.getElementById('cc').value,
    idempotency_key:crypto.randomUUID()}};
  const r=await fetch(`/shop/api/v1/public/storefront/${{S.slug}}/orders`,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});
  if(!r.ok){{alert('Не удалось оформить заказ');return;}}
  const d=await r.json();
  document.getElementById('panel').innerHTML=`<div class="done"><h2>Заказ принят!</h2><div class="code">#${{d.public_code}}</div><p>Сохраните номер — по нему можно узнать статус.</p></div>`;
  cart.clear();draw();
}};
render();
</script>
</body>
</html>"""


def storefront_html(snapshot: JsonObject) -> str:
    """HTML витрины с inline-снапшотом для SSR-lite рендера."""
    accent = "#e2553f"
    theme = snapshot.get("theme")
    if isinstance(theme, dict):
        accent = str(theme.get("accent_color", accent))
    return _PAGE.format(
        title=escape(str(snapshot.get("name", "Витрина"))),
        description=escape(str(snapshot.get("description", ""))[:200]),
        accent=escape(accent),
        snapshot=json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/"),
    )
