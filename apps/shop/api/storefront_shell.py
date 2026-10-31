"""Storefront shell — HTML-страница витрины с inline-снапшотом.

Отдаётся анонимно на ``/s/{slug}``: снапшот из Redis встраивается в HTML
одним JSON-блоком, клиентский JS рендерит меню и корзину без SPA-сборки.
SSR-lite: первый байт уже содержит всё меню — SEO и скорость из коробки.

Шаблоны витрины (``theme.preset``): ``menu`` — классическое меню списком,
``grid`` — фотоплитка, ``compact`` — плотный список без фото.
"""

from __future__ import annotations

import json
from html import escape

from core.types import JsonObject

_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="{description}">
<style>
:root{{--accent:{accent};--bg:#100e0c;--card:#1b1815;--card2:#241f1a;--text:#f6f1e8;--muted:#a89e90;--line:#2b251e;--radius:18px}}
*{{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}}
body{{font-family:ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}}
.serif{{font-family:ui-serif,Georgia,'Times New Roman',serif}}
.wrap{{max-width:720px;margin:0 auto;padding:0 16px 160px}}
.hero{{position:relative;margin:0 -16px;height:260px;overflow:hidden;background:linear-gradient(165deg,var(--accent) 0%,#221a12 75%)}}
.hero .bg{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.9}}
.hero .veil{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(16,14,12,.15) 20%,rgba(16,14,12,.92) 100%)}}
.hero .head{{position:absolute;left:24px;right:24px;bottom:18px;display:flex;align-items:flex-end;gap:14px}}
.hero .logo{{width:64px;height:64px;border-radius:18px;object-fit:cover;border:2px solid rgba(255,255,255,.35);background:var(--card);flex-shrink:0}}
.hero h1{{font-size:30px;font-weight:650;letter-spacing:-.01em;text-shadow:0 2px 16px rgba(0,0,0,.65)}}
.hero .desc{{font-size:14px;color:#e8ded0;margin-top:4px;text-shadow:0 1px 8px rgba(0,0,0,.7);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.meta{{padding:14px 2px 6px;color:var(--muted);font-size:13.5px;display:flex;gap:14px;flex-wrap:wrap}}
.meta span{{display:inline-flex;align-items:center;gap:6px}}
.tabs{{position:sticky;top:0;z-index:5;display:flex;gap:8px;overflow-x:auto;padding:12px 2px;background:linear-gradient(180deg,var(--bg) 85%,transparent);scrollbar-width:none}}
.tabs::-webkit-scrollbar{{display:none}}
.tabs button{{font:inherit;font-size:14.5px;padding:9px 16px;border-radius:99px;border:1px solid var(--line);color:var(--muted);background:var(--card);cursor:pointer;white-space:nowrap;transition:all .15s}}
.tabs button.on{{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}}
.cat{{font-size:21px;margin:28px 0 6px;letter-spacing:-.01em}}
.item{{display:flex;gap:14px;padding:16px 2px;border-bottom:1px solid var(--line);animation:fade .3s ease}}
@keyframes fade{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1}}}}
.item img{{width:92px;height:92px;border-radius:var(--radius);object-fit:cover;background:var(--card2);flex-shrink:0}}
.item .b{{flex:1;min-width:0}}
.item h3{{font-size:16.5px;font-weight:600}}
.item p{{font-size:13.5px;color:var(--muted);margin-top:4px;line-height:1.5;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}
.item .row{{display:flex;justify-content:space-between;align-items:center;margin-top:10px;gap:10px}}
.price{{font-size:16.5px;font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap}}
.add{{font:inherit;font-size:14px;font-weight:600;padding:9px 18px;border-radius:99px;border:0;background:var(--accent);color:#fff;cursor:pointer;transition:transform .1s}}
.add:active{{transform:scale(.94)}}
.stepper{{display:inline-flex;align-items:center;gap:2px;background:var(--card2);border-radius:99px;padding:3px}}
.stepper button{{width:32px;height:32px;border-radius:99px;border:0;background:var(--accent);color:#fff;font-size:18px;font-weight:700;cursor:pointer;line-height:1}}
.stepper button.ghost{{background:transparent;color:var(--accent)}}
.stepper span{{min-width:26px;text-align:center;font-weight:650;font-variant-numeric:tabular-nums}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding-top:10px}}
.gcard{{background:var(--card);border-radius:var(--radius);overflow:hidden;border:1px solid var(--line);display:flex;flex-direction:column}}
.gcard img{{width:100%;aspect-ratio:4/3;object-fit:cover;background:var(--card2)}}
.gcard .b{{padding:12px;display:flex;flex-direction:column;gap:8px;flex:1}}
.gcard h3{{font-size:15px;font-weight:600}}
.gcard p{{font-size:12.5px;color:var(--muted);line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.gcard .row{{display:flex;justify-content:space-between;align-items:center;margin-top:auto;gap:8px}}
.compact .item{{padding:12px 2px}}
.compact .item img{{display:none}}
.cart{{position:fixed;left:50%;transform:translateX(-50%);bottom:18px;width:min(688px,92vw);background:var(--accent);color:#fff;border:0;font:inherit;font-size:16px;font-weight:650;padding:17px;border-radius:99px;cursor:pointer;display:none;box-shadow:0 10px 40px rgba(0,0,0,.55);z-index:10;letter-spacing:.01em}}
.cart.show{{display:block;animation:pop .25s ease}}
@keyframes pop{{from{{transform:translateX(-50%) translateY(16px);opacity:0}}}}
.sheet{{position:fixed;inset:0;background:rgba(0,0,0,.65);backdrop-filter:blur(4px);display:none;z-index:20}}
.sheet.show{{display:block}}
.panel{{position:absolute;left:50%;transform:translateX(-50%);bottom:0;width:min(720px,100vw);max-height:88vh;overflow:auto;background:var(--card);border-radius:26px 26px 0 0;padding:22px 20px 44px;animation:up .25s ease}}
@keyframes up{{from{{transform:translateX(-50%) translateY(40px)}}}}
.panel h2{{font-size:21px;margin-bottom:16px;letter-spacing:-.01em}}
.cl{{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:9px 0;font-size:15px;border-bottom:1px solid var(--line)}}
.cl .n{{flex:1;min-width:0}}
.cl .s{{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}}
.seg{{display:flex;background:var(--card2);border-radius:14px;padding:4px;margin:14px 0}}
.seg button{{flex:1;font:inherit;font-size:14.5px;font-weight:600;padding:11px;border:0;border-radius:11px;background:transparent;color:var(--muted);cursor:pointer}}
.seg button.on{{background:var(--accent);color:#fff}}
input.f{{width:100%;font:inherit;font-size:15px;padding:14px;margin:6px 0;border-radius:14px;border:1px solid var(--line);background:#12100d;color:var(--text)}}
input.f:focus{{outline:none;border-color:var(--accent)}}
button.big{{width:100%;font:inherit;font-size:16px;font-weight:650;padding:16px;border-radius:16px;border:0;background:var(--accent);color:#fff;cursor:pointer;margin-top:14px;letter-spacing:.01em}}
button.big:disabled{{opacity:.45;cursor:default}}
.minwarn{{font-size:13px;color:#f0b45c;margin-top:10px;text-align:center}}
.done{{text-align:center;padding:64px 20px}}
.done .code{{font-size:36px;font-weight:750;color:var(--accent);margin:16px 0;letter-spacing:.02em}}
.done .st{{font-size:14px;font-weight:650;color:var(--accent);background:color-mix(in srgb,var(--accent) 14%,transparent);display:inline-block;padding:6px 16px;border-radius:99px;margin-bottom:14px}}
.done p{{color:var(--muted);font-size:14.5px;line-height:1.6}}
.empty{{text-align:center;color:var(--muted);padding:60px 20px;font-size:15px}}
@media(max-width:520px){{.hero{{height:210px}}.hero h1{{font-size:26px}}.grid{{grid-template-columns:1fr 1fr;gap:10px}}}}
</style>
</head>
<body class="{body_class}">
<div class="wrap" id="app"></div>
<button class="cart" id="cart" onclick="openSheet()"></button>
<div class="sheet" id="sheet" onclick="if(event.target===this)closeSheet()"><div class="panel" id="panel"></div></div>
<script id="snapshot" type="application/json">{snapshot}</script>
<script>
const S=JSON.parse(document.getElementById('snapshot').textContent);
const PRESET=(S.theme&&S.theme.preset)||'menu';
const fmt=v=>(v/100).toLocaleString('ru-RU')+' ₽';
const IMG=u=>u?`/shop/api/v1/files/download/${{u}}`:'';
const cart=new Map();
const app=document.getElementById('app');
const byId=id=>S.products.find(x=>x.id===id);
function esc(s){{return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}}
function photo(u,cls){{return u?`<img class="${{cls||''}}" src="${{IMG(u)}}" loading="lazy" alt="">`:'';}}
function qtyCtl(p){{const q=cart.get(p.id)||0;
  if(!q)return `<button class="add" onclick="add('${{p.id}}',1)">В корзину</button>`;
  return `<span class="stepper"><button class="ghost" onclick="add('${{p.id}}',-1)">−</button><span>${{q}}</span><button onclick="add('${{p.id}}',1)">+</button></span>`;}}
function rowList(ps){{return ps.map(p=>`<div class="item">${{photo(p.photo_file_id)}}<div class="b"><h3>${{esc(p.name)}}</h3>${{p.description?`<p>${{esc(p.description)}}</p>`:''}}<div class="row"><span class="price">${{fmt(p.price_minor)}}</span><span data-qty="${{p.id}}">${{qtyCtl(p)}}</span></div></div></div>`).join('');}}
function rowGrid(ps){{return `<div class="grid">`+ps.map(p=>`<div class="gcard">${{photo(p.photo_file_id)}}<div class="b"><h3>${{esc(p.name)}}</h3>${{p.description?`<p>${{esc(p.description)}}</p>`:''}}<div class="row"><span class="price">${{fmt(p.price_minor)}}</span><span data-qty="${{p.id}}">${{qtyCtl(p)}}</span></div></div></div>`).join('')+`</div>`;}}
function rowCompact(ps){{return ps.map(p=>`<div class="item"><div class="b"><h3>${{esc(p.name)}}</h3>${{p.description?`<p>${{esc(p.description)}}</p>`:''}}</div><span class="price">${{fmt(p.price_minor)}}</span><span data-qty="${{p.id}}">${{qtyCtl(p)}}</span></div>`).join('');}}
const ITEMS=PRESET==='grid'?rowGrid:(PRESET==='compact'?rowCompact:rowList);
function render(){{
  const cats=S.categories.filter(c=>S.products.some(p=>p.category_id===c.id));
  const other=S.products.filter(p=>!p.category_id);
  let h=`<div class="hero">${{photo(S.cover_file_id,'bg')}}<div class="veil"></div><div class="head">${{photo(S.logo_file_id,'logo')}}<div><h1 class="serif">${{esc(S.name)}}</h1>${{S.description?`<div class="desc">${{esc(S.description)}}</div>`:''}}</div></div></div>
  <div class="meta">${{S.city||S.address?`<span>📍 ${{esc([S.city,S.address].filter(Boolean).join(', '))}}</span>`:''}}${{S.phone?`<span>☎ ${{esc(S.phone)}}</span>`:''}}${{S.delivery_enabled?'<span>🛵 Доставка</span>':''}}${{S.pickup_enabled?'<span>🛍 Самовывоз</span>':''}}</div>`;
  if(!S.products.length){{app.innerHTML=h+`<div class="empty">Меню скоро появится</div>`;return;}}
  h+=`<div class="tabs">${{cats.map(c=>`<button data-cat="${{c.id}}" onclick="jump('${{c.id}}')">${{esc(c.name)}}</button>`).join('')}}${{other.length?`<button data-cat="other" onclick="jump('other')">Ещё</button>`:''}}</div>`;
  for(const c of cats){{h+=`<h2 class="cat serif" id="c-${{c.id}}">${{esc(c.name)}}</h2>`+ITEMS(S.products.filter(p=>p.category_id===c.id));}}
  if(other.length){{h+=`<h2 class="cat serif" id="c-other">Ещё</h2>`+ITEMS(other);}}
  app.innerHTML=h;
}}
window.jump=id=>{{document.getElementById('c-'+id)?.scrollIntoView({{behavior:'smooth',block:'start'}});}};
window.add=(id,d)=>{{const q=(cart.get(id)||0)+d;if(q<=0)cart.delete(id);else cart.set(id,q);
  document.querySelectorAll(`[data-qty="${{id}}"]`).forEach(el=>{{el.innerHTML=qtyCtl(byId(id));}});draw();}};
function total(){{let t=0;for(const [id,q] of cart){{const p=byId(id);if(p)t+=p.price_minor*q;}}return t;}}
function count(){{return [...cart.values()].reduce((a,x)=>a+x,0);}}
function draw(){{const b=document.getElementById('cart');const n=count();
  if(n){{b.textContent=`Корзина · ${{n}} · ${{fmt(total())}} →`;b.classList.add('show');}}else b.classList.remove('show');}}
let dtype='';
window.openSheet=()=>{{
  if(!dtype)dtype=S.delivery_enabled?'delivery':'pickup';
  renderSheet();
  document.getElementById('sheet').classList.add('show');
}};
window.setDtype=t=>{{dtype=t;renderSheet();}};
function renderSheet(){{
  const p=document.getElementById('panel');
  const sub=total();
  const fee=dtype==='delivery'?(S.delivery_fee_minor||0):0;
  const below=S.min_order_minor&&sub<S.min_order_minor;
  const seg=(S.delivery_enabled&&S.pickup_enabled)?`<div class="seg">
    <button class="${{dtype==='delivery'?'on':''}}" onclick="setDtype('delivery')">🛵 Доставка</button>
    <button class="${{dtype==='pickup'?'on':''}}" onclick="setDtype('pickup')">🛍 Самовывоз</button></div>`:'';
  p.innerHTML=`<h2>Ваш заказ</h2>`+[...cart.entries()].map(([id,q])=>{{const x=byId(id);return x?`<div class="cl"><span class="n">${{esc(x.name)}}</span><span class="stepper"><button class="ghost" onclick="add('${{id}}',-1);renderSheet()">−</button><span>${{q}}</span><button onclick="add('${{id}}',1);renderSheet()">+</button></span><b class="s">${{fmt(x.price_minor*q)}}</b></div>`:'';}}).join('')+
  seg+
  (dtype==='delivery'?`<div class="cl"><span>Доставка</span><b class="s">${{fmt(fee)}}</b></div>`:'')+
  `<div class="cl" style="border-bottom:0"><b>Итого</b><b class="s" style="font-size:18px">${{fmt(sub+fee)}}</b></div>
  <input class="f" id="cn" placeholder="Ваше имя"><input class="f" id="cp" type="tel" placeholder="Телефон">
  ${{dtype==='delivery'?'<input class="f" id="ca" placeholder="Адрес доставки">':''}}<input class="f" id="cc" placeholder="Комментарий к заказу">
  ${{below?`<div class="minwarn">Минимальный заказ — ${{fmt(S.min_order_minor)}}</div>`:''}}
  <button class="big" ${{below?'disabled':''}} onclick="submit()">Оформить заказ · ${{fmt(sub+fee)}}</button>`;
}};
window.closeSheet=()=>document.getElementById('sheet').classList.remove('show');
window.submit=async()=>{{
  const body={{items:[...cart.entries()].map(([id,qty])=>({{product_id:id,qty}})),
    customer_name:document.getElementById('cn').value,customer_phone:document.getElementById('cp').value,
    delivery_type:dtype,
    address:dtype==='delivery'?(document.getElementById('ca')?.value||''):'',
    comment:document.getElementById('cc').value,
    idempotency_key:crypto.randomUUID()}};
  const r=await fetch(`/shop/api/v1/public/storefront/${{S.slug}}/orders`,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});
  if(!r.ok){{alert('Не удалось оформить заказ');return;}}
  const d=await r.json();
  cart.clear();draw();
  trackOrder(d.public_code);
}};
const STATUS_LABEL={{new:'Принят',accepted:'Подтверждён',preparing:'Готовится',delivering:'В доставке',done:'Выполнен',cancelled:'Отменён'}};
window.trackOrder=async code=>{{
  const p=document.getElementById('panel');
  const render=st=>{{p.innerHTML=`<div class="done"><h2 class="serif">Заказ принят!</h2><div class="code">#${{code}}</div><div class="st">${{STATUS_LABEL[st]||st}}</div><p>Сохраните номер заказа — по нему можно проверить статус.<br>Мы свяжемся с вами для подтверждения.</p></div>`;}};
  render('new');
  const poll=async()=>{{
    if(!document.getElementById('sheet').classList.contains('show'))return;
    try{{
      const r=await fetch(`/shop/api/v1/public/orders/${{code}}`);
      if(r.ok){{const d=await r.json();render(d.status);if(d.status!=='done'&&d.status!=='cancelled')setTimeout(poll,15000);}}
      else setTimeout(poll,30000);
    }}catch(e){{setTimeout(poll,30000);}}
  }};
  setTimeout(poll,15000);
}};
render();
</script>
</body>
</html>"""


def storefront_html(snapshot: JsonObject) -> str:
    """HTML витрины с inline-снапшотом для SSR-lite рендера."""
    accent = "#e2553f"
    preset = "menu"
    theme = snapshot.get("theme")
    if isinstance(theme, dict):
        accent = str(theme.get("accent_color", accent))
        preset = str(theme.get("preset", preset))
    body_class = "compact" if preset == "compact" else ""
    return _PAGE.format(
        title=escape(str(snapshot.get("name", "Витрина"))),
        description=escape(str(snapshot.get("description", ""))[:200]),
        accent=escape(accent),
        body_class=escape(body_class),
        snapshot=json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/"),
    )
