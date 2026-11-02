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
<meta name="theme-color" content="{accent}">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
{seo_head}
<style>
:root{{--accent:{accent};--on-accent:{on_accent};--afg:{afg_dark};--bg:#131110;--card:#1e1a17;--card2:#2a241f;--text:#f7f3ec;--muted:#a39a8d;--line:#2e2823;--radius:18px;--overlay:rgba(10,9,8,.62);--on-hero:#fff;--success:#4ade80;--warn:#f0b45c;--shadow-sm:0 1px 2px rgba(0,0,0,.4);--shadow-lg:0 14px 44px rgba(0,0,0,.55);color-scheme:dark}}
*{{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}}
::selection{{background:color-mix(in srgb,var(--accent) 32%,transparent)}}
:focus-visible{{outline:2px solid var(--afg);outline-offset:2px}}
img{{background:var(--card2);transition:opacity .35s ease}}
img:not(.ld){{opacity:0}}
body.lock{{overflow:hidden}}
body{{font-family:ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overscroll-behavior:none;touch-action:manipulation;overflow-x:hidden;overflow-x:clip;text-rendering:optimizeLegibility;-webkit-font-smoothing:antialiased}}
.serif{{font-family:ui-serif,Georgia,'Times New Roman',serif}}
.wrap{{max-width:720px;margin:0 auto;padding:0 16px calc(150px + env(safe-area-inset-bottom))}}
.hero{{position:relative;margin:0 -16px;height:260px;overflow:hidden;background:linear-gradient(160deg,var(--accent) 0%,color-mix(in srgb,var(--accent) 42%,#171310) 52%,#171310 100%)}}
.hero .bg{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.9}}
.hero .veil{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(16,14,12,.15) 20%,rgba(16,14,12,.92) 100%)}}
.hero .head{{position:absolute;left:24px;right:24px;bottom:18px;display:flex;align-items:flex-end;gap:14px}}
.hero .logo{{width:64px;height:64px;border-radius:18px;object-fit:cover;border:2px solid rgba(255,255,255,.4);background:var(--card);flex-shrink:0;box-shadow:0 4px 18px rgba(0,0,0,.35)}}
.hero h1{{font-size:32px;font-weight:650;letter-spacing:-.01em;color:var(--on-hero);text-shadow:0 2px 18px rgba(0,0,0,.7)}}
.hero .desc{{font-size:14px;color:color-mix(in srgb,var(--on-hero) 86%,transparent);margin-top:4px;text-shadow:0 1px 8px rgba(0,0,0,.7);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.meta{{padding:14px 2px 6px;color:var(--muted);font-size:13.5px;display:flex;gap:14px;flex-wrap:wrap}}
.meta span{{display:inline-flex;align-items:center;gap:6px}}
.meta svg{{width:15px;height:15px;fill:currentColor;flex-shrink:0;opacity:.85}}
.ob-open,.ob-closed{{font-weight:650}}
.ob-open{{color:var(--success)}}
.ob-closed{{color:var(--warn)}}
.tabs{{position:sticky;top:env(safe-area-inset-top);z-index:5;display:flex;gap:8px;overflow-x:auto;padding:12px 2px;background:linear-gradient(180deg,var(--bg) 85%,transparent);scrollbar-width:none}}
.msearch{{display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--line);border-radius:99px;padding:10px 18px;margin:10px 0 2px;transition:border-color .15s,box-shadow .15s}}
.msearch:focus-within{{border-color:var(--afg);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 22%,transparent)}}
.msearch svg{{opacity:.5;flex-shrink:0}}
.msearch input{{flex:1;min-width:0;font:inherit;font-size:15px;background:transparent;border:0;color:var(--text);outline:none}}
.msearch input::placeholder{{color:var(--muted)}}
.tabs::-webkit-scrollbar{{display:none}}
.tabs button{{font:inherit;font-size:14.5px;padding:9px 16px;border-radius:99px;border:1px solid var(--line);color:var(--muted);background:var(--card);cursor:pointer;white-space:nowrap;transition:all .15s}}
.tabs button:hover{{color:var(--text);border-color:color-mix(in srgb,var(--text) 25%,var(--line))}}
.tabs button.on{{background:var(--accent);border-color:var(--accent);color:var(--on-accent);font-weight:600}}
.cat{{font-size:21px;margin:28px 0 6px;letter-spacing:-.01em}}
.cat.sub{{font-size:17px;margin:18px 0 4px;color:var(--muted);font-weight:600}}
.mchunk{{animation:fade .3s ease}}
.msk{{height:96px;border-radius:var(--radius);margin:14px 0;background:linear-gradient(100deg,var(--card2) 40%,var(--card) 50%,var(--card2) 60%);background-size:200% 100%;animation:shimmer 1.4s infinite linear}}
@keyframes shimmer{{from{{background-position:120% 0}}to{{background-position:-80% 0}}}}
.cart.pop{{animation:pop .28s ease}}
@keyframes pop{{0%{{transform:translateX(-50%) scale(1)}}40%{{transform:translateX(-50%) scale(1.06)}}100%{{transform:translateX(-50%) scale(1)}}}}
.item,.gcard{{cursor:pointer}}
.phero{{width:100%;aspect-ratio:16/10;object-fit:cover;border-radius:var(--radius);margin-bottom:12px}}
.pdesc{{color:var(--muted);font-size:14px;line-height:1.55;margin:4px 0 14px}}
.item{{display:flex;gap:14px;padding:16px 2px;border-bottom:1px solid var(--line);animation:fade .3s ease}}
.flash{{animation:flashRing 2.6s ease}}
@keyframes flashRing{{0%,55%{{box-shadow:0 0 0 3px var(--accent);border-radius:14px}}100%{{box-shadow:0 0 0 0 transparent}}}}
@keyframes fade{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1}}}}
.item img{{width:92px;height:92px;border-radius:var(--radius);object-fit:cover;background:var(--card2);flex-shrink:0}}
.item .b{{flex:1;min-width:0}}
.item h3{{font-size:16.5px;font-weight:600;letter-spacing:-.005em}}
.portion{{font-size:13px;font-weight:500;color:var(--muted);margin-left:6px;white-space:nowrap}}
.item p{{font-size:13.5px;color:var(--muted);margin-top:4px;line-height:1.55;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}
.item .row{{display:flex;justify-content:space-between;align-items:center;margin-top:10px;gap:10px}}
.price{{font-size:16.5px;font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap}}
.add{{font:inherit;font-size:14px;font-weight:600;padding:9px 18px;border-radius:99px;border:0;background:var(--accent);color:var(--on-accent);cursor:pointer;transition:transform .1s,box-shadow .15s}}
.add:hover{{box-shadow:0 2px 12px color-mix(in srgb,var(--accent) 45%,transparent)}}
.add:active{{transform:scale(.94)}}
.stepper{{display:inline-flex;align-items:center;gap:2px;background:var(--card2);border-radius:99px;padding:3px}}
.stepper button{{width:32px;height:32px;border-radius:99px;border:0;background:var(--accent);color:var(--on-accent);font-size:18px;font-weight:700;cursor:pointer;line-height:1}}
.stepper button.ghost{{background:transparent;color:var(--afg)}}
.stepper span{{min-width:26px;text-align:center;font-weight:650;font-variant-numeric:tabular-nums}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding-top:10px}}
.gcard{{background:var(--card);border-radius:var(--radius);overflow:hidden;border:1px solid var(--line);display:flex;flex-direction:column;box-shadow:var(--shadow-sm)}}
.gcard img{{width:100%;aspect-ratio:4/3;object-fit:cover;background:var(--card2)}}
.gcard .b{{padding:12px;display:flex;flex-direction:column;gap:8px;flex:1}}
.gcard h3{{font-size:15px;font-weight:600;letter-spacing:-.005em}}
.gcard p{{font-size:12.5px;color:var(--muted);line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.gcard .row{{display:flex;justify-content:space-between;align-items:center;margin-top:auto;gap:8px}}
.compact .item{{padding:12px 2px}}
.compact .item img{{display:none}}
.cart{{position:fixed;left:50%;transform:translateX(-50%);bottom:calc(18px + env(safe-area-inset-bottom));width:min(688px,92vw);background:var(--accent);color:var(--on-accent);border:0;font:inherit;font-size:16px;font-weight:650;padding:17px;border-radius:99px;cursor:pointer;display:none;box-shadow:var(--shadow-lg);z-index:10;letter-spacing:.01em}}
.cart.show{{display:block;animation:pop .25s ease}}
@keyframes pop{{from{{transform:translateX(-50%) translateY(16px);opacity:0}}}}
.sheet{{position:fixed;inset:0;background:var(--overlay);backdrop-filter:blur(4px);display:none;z-index:20}}
.sheet.show{{display:block}}
.panel{{position:absolute;left:50%;transform:translateX(-50%);bottom:0;width:min(720px,100vw);max-height:88vh;overflow:auto;background:var(--card);border-radius:26px 26px 0 0;padding:10px 20px calc(44px + env(safe-area-inset-bottom));animation:up .25s ease;transition:transform .18s ease;box-shadow:var(--shadow-lg)}}
.panel.drag{{transition:none}}
.grab{{width:38px;height:5px;border-radius:99px;background:var(--line);margin:0 auto 12px;touch-action:none}}
@keyframes up{{from{{transform:translateX(-50%) translateY(40px)}}}}
.panel h2{{font-size:21px;margin-bottom:16px;letter-spacing:-.01em}}
.pshare{{position:absolute;top:14px;right:14px;width:38px;height:38px;border-radius:50%;background:rgba(18,18,20,.55);backdrop-filter:blur(8px);color:#fff;display:grid;place-items:center;z-index:2}}
.pshare svg{{width:18px;height:18px;fill:currentColor}}
.toast{{position:fixed;left:50%;transform:translateX(-50%) translateY(12px);bottom:calc(90px + env(safe-area-inset-bottom));background:#1c1c20;color:#fff;padding:10px 18px;border-radius:999px;border:1px solid rgba(255,255,255,.08);font-size:13.5px;opacity:0;pointer-events:none;transition:.25s ease;z-index:40;box-shadow:0 8px 24px rgba(0,0,0,.3)}}
.toast.show{{opacity:1;transform:translateX(-50%) translateY(0)}}
.cl{{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:9px 0;font-size:15px;border-bottom:1px solid var(--line)}}
.cl .n{{flex:1;min-width:0}}
.cl .mods{{display:block;font-size:12.5px;color:var(--muted);margin-top:3px;line-height:1.45}}
.cl .s{{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}}
.mg{{margin:16px 0}}
.mg.nest{{margin:12px 0 4px 14px;padding-left:12px;border-left:2px solid var(--line)}}
.mg-h{{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:10px}}
.mg-h b{{font-size:15px}}
.mg-r{{font-size:12px;color:var(--warn);white-space:nowrap}}
.mg-r.ok{{color:var(--muted)}}
.opts{{display:flex;flex-wrap:wrap;gap:8px}}
.opt{{font:inherit;font-size:14px;padding:10px 14px;border-radius:12px;border:1px solid var(--line);background:var(--card2);color:var(--text);cursor:pointer;display:inline-flex;align-items:center;gap:8px;transition:all .12s}}
.opt:hover{{border-color:color-mix(in srgb,var(--text) 28%,var(--line))}}
.opt.on{{background:var(--accent);border-color:var(--accent);color:var(--on-accent);font-weight:600}}
.opt.dis{{opacity:.45;filter:saturate(.4);cursor:default}}
.opt i{{font-style:normal;font-size:12.5px;opacity:.85}}
.opt .stepper{{padding:2px}}
.opt .stepper button{{width:24px;height:24px;font-size:15px}}
.crow{{display:flex;justify-content:flex-end;margin-top:18px}}
.seg{{display:flex;background:var(--card2);border-radius:14px;padding:4px;margin:14px 0}}
.seg button{{flex:1;font:inherit;font-size:14.5px;font-weight:600;padding:11px;border:0;border-radius:11px;background:transparent;color:var(--muted);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:8px}}
.seg button svg{{width:17px;height:17px;fill:currentColor;flex-shrink:0}}
.seg button.on{{background:var(--accent);color:var(--on-accent);box-shadow:var(--shadow-sm)}}
input.f,select.f{{width:100%;font:inherit;font-size:15px;padding:14px;margin:6px 0;border-radius:14px;border:1px solid var(--line);background:var(--card2);color:var(--text);transition:border-color .15s,box-shadow .15s}}
input.f:focus,select.f:focus{{outline:none;border-color:var(--afg);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 22%,transparent)}}
input.f::placeholder{{color:var(--muted)}}
button.big{{width:100%;font:inherit;font-size:16px;font-weight:650;padding:16px;border-radius:16px;border:0;background:var(--accent);color:var(--on-accent);cursor:pointer;margin-top:14px;letter-spacing:.01em;transition:transform .1s,box-shadow .15s}}
button.big:hover:not(:disabled){{box-shadow:0 6px 20px color-mix(in srgb,var(--accent) 42%,transparent)}}
button.big:disabled{{opacity:.45;cursor:default}}
.minwarn{{font-size:13px;color:var(--warn);margin-top:10px;text-align:center}}
.done{{text-align:center;padding:64px 20px}}
.done .code{{font-size:36px;font-weight:750;color:var(--afg);margin:16px 0;letter-spacing:.02em}}
.done .st{{font-size:14px;font-weight:650;color:var(--afg);background:color-mix(in srgb,var(--accent) 14%,transparent);display:inline-block;padding:6px 16px;border-radius:99px;margin-bottom:14px}}
.done p{{color:var(--muted);font-size:14.5px;line-height:1.6}}
.pbadge{{display:inline-block;margin-left:8px;padding:3px 10px;border-radius:99px;background:var(--accent);color:var(--on-accent);font-size:11px;font-weight:700;vertical-align:middle;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.ptag{{display:inline-flex;align-items:center;gap:4px;margin-left:6px;padding:3px 9px;border-radius:99px;background:color-mix(in srgb,var(--accent) 13%,transparent);color:var(--afg);font-size:10.5px;font-weight:700;vertical-align:middle;white-space:nowrap}}
.ptag svg{{width:12px;height:12px;fill:currentColor;flex-shrink:0}}
.save{{color:var(--success)}}
.save b{{color:var(--success)}}
.empty{{text-align:center;color:var(--muted);padding:60px 20px;font-size:15px}}
body.light{{--bg:#f5f4f2;--card:#ffffff;--card2:#eeebe7;--text:#1d1a16;--muted:#6e665a;--line:#e5e1da;--overlay:rgba(24,20,15,.45);--success:#15803d;--warn:#b45309;--afg:{afg_light};--shadow-sm:0 1px 2px rgba(24,20,15,.07),0 2px 8px rgba(24,20,15,.05);--shadow-lg:0 16px 44px rgba(24,20,15,.16);color-scheme:light}}
@media(min-width:1024px){{
.wrap{{max-width:1240px;padding:0 24px calc(140px + env(safe-area-inset-bottom))}}
.hero{{margin:0 calc(50% - 50vw);height:340px}}
.hero .head{{left:50%;right:auto;transform:translateX(-50%);width:min(1240px,100%);bottom:28px;padding:0 24px}}
.hero .logo{{width:84px;height:84px;border-radius:22px}}
.hero h1{{font-size:40px}}
.hero .desc{{font-size:15.5px;-webkit-line-clamp:3;max-width:680px}}
.meta{{padding:16px 2px 8px;font-size:14px;gap:18px}}
.msearch{{margin:14px 0 4px;max-width:460px}}
#msw{{margin-left:262px}}
#app.flat #msw{{margin-left:0}}
#menu{{display:grid;grid-template-columns:230px minmax(0,1fr);gap:0 32px;align-items:start;margin-top:10px}}
#menu>:not(.tabs){{grid-column:2}}
#app.flat #menu{{display:block}}
.tabs{{grid-column:1;grid-row:1;position:sticky;top:24px;z-index:5;flex-direction:column;align-items:stretch;gap:4px;padding:0;background:none;overflow-x:visible;overflow-y:auto;max-height:calc(100vh - 40px);scrollbar-width:thin}}
#app.flat .tabs{{display:none}}
.tabs button{{text-align:left;border:0;border-radius:12px;background:transparent;padding:11px 14px}}
.tabs button:hover{{color:var(--text);background:color-mix(in srgb,var(--text) 6%,transparent)}}
.tabs button.on{{background:color-mix(in srgb,var(--accent) 15%,transparent);color:var(--afg);font-weight:650}}
.cat{{font-size:24px;margin:34px 0 10px}}
.cat.sub{{font-size:18px}}
#mbody>.mchunk:first-child>.cat{{margin-top:0}}
body[data-preset=menu] .mchunk,body[data-preset=compact] .mchunk{{display:grid;grid-template-columns:1fr 1fr;column-gap:40px}}
body[data-preset=menu] .mchunk>.cat,body[data-preset=compact] .mchunk>.cat{{grid-column:1/-1}}
body[data-preset=grid] .grid{{grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:18px}}
.gcard{{transition:transform .15s ease,border-color .15s ease,box-shadow .15s ease}}
.gcard:hover{{transform:translateY(-2px);border-color:color-mix(in srgb,var(--accent) 45%,var(--line));box-shadow:var(--shadow-lg)}}
.item{{border-radius:12px;padding-left:12px;padding-right:12px;margin-left:-12px;margin-right:-12px;transition:background .15s ease}}
body[data-preset=compact] .item{{padding-left:12px;padding-right:12px}}
.item:hover{{background:color-mix(in srgb,var(--text) 4%,transparent)}}
.cart{{left:auto;right:32px;transform:none;width:min(360px,30vw);bottom:28px}}
.cart.show{{animation:cartIn .25s ease}}
.cart.pop{{animation:cartPop .28s ease}}
@keyframes cartIn{{from{{transform:translateY(16px);opacity:0}}}}
@keyframes cartPop{{0%{{transform:scale(1)}}40%{{transform:scale(1.05)}}100%{{transform:scale(1)}}}}
.grab{{display:none}}
#sheet .panel{{left:auto;right:0;top:0;bottom:0;transform:none;width:min(470px,94vw);height:100%;max-height:none;border-radius:0;padding:18px 24px calc(28px + env(safe-area-inset-bottom));display:flex;flex-direction:column;animation:drawerIn .24s ease}}
#sheet .panel #panel{{display:flex;flex-direction:column;flex:1}}
#sheet .panel .big{{margin-top:auto}}
@keyframes drawerIn{{from{{transform:translateX(56px);opacity:.5}}}}
#csheet.show{{display:grid;place-items:center}}
#csheet .panel{{position:relative;inset:auto;transform:none;width:min(620px,94vw);max-height:88vh;border-radius:26px;padding:18px 24px 30px;animation:zoomIn .2s ease}}
@keyframes zoomIn{{from{{transform:scale(.95) translateY(14px);opacity:0}}}}
.toast{{bottom:44px}}
}}
@media(max-width:520px){{.hero{{height:210px}}.hero h1{{font-size:26px}}.grid{{grid-template-columns:1fr 1fr;gap:10px}}}}
</style>
</head>
<body class="{body_class}" data-preset="{preset}">
<div class="wrap" id="app"></div>
<button class="cart" id="cart" onclick="openSheet()"></button>
<div class="sheet" id="sheet" onclick="if(event.target===this)closeSheet()"><div class="panel"><div class="grab"></div><div id="panel"></div></div></div>
<div class="sheet" id="csheet" onclick="if(event.target===this)closeCust()"><div class="panel"><div class="grab"></div><div id="cpanel"></div></div></div>
<div class="toast" id="toast"></div>
<script id="snapshot" type="application/json">{snapshot}</script>
<script>
const S=JSON.parse(document.getElementById('snapshot').textContent);
const PRESET=(S.theme&&S.theme.preset)||'menu';
const EMBED=new URLSearchParams(location.search).has('embed');
const TABLE_ID=new URLSearchParams(location.search).get('table')||'';
const TABLES=Array.isArray(S.tables)?S.tables:[];
const fmt=v=>(v/100).toLocaleString('ru-RU')+' ₽';
const IMG=u=>u?`/shop/api/v1/files/download/${{u}}`:'';
const DAYS=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
function hoursBadge(){{
  const wh=S.working_hours||{{}};
  if(!Object.keys(wh).length)return null;
  const tz=S.timezone||'Europe/Moscow';
  let now;
  try{{now=new Date(new Date().toLocaleString('en-US',{{timeZone:tz}}));}}catch(e){{now=new Date();}}
  const day=(now.getDay()+6)%7;
  const mins=now.getHours()*60+now.getMinutes();
  const hm=v=>{{const p=v.split(':');return (+p[0])*60+(+p[1]||0);}};
  const range=v=>{{if(typeof v!=='string')return null;const p=v.split('-');return p.length<2?null:{{o:p[0],c:p[1],om:hm(p[0]),cm:hm(p[1])}};}};
  const today=range(wh[String(day)]);
  if(today){{
    if(mins>=today.om&&mins<today.cm)return{{t:'Открыто · до '+today.c,open:true}};
    if(mins<today.om)return{{t:'Откроемся в '+today.o,open:false}};
  }}
  for(let d=1;d<=7;d++){{
    const nd=(day+d)%7,tr=range(wh[String(nd)]);
    if(tr)return{{t:'Откроемся '+DAYS[nd]+' в '+tr.o,open:false}};
  }}
  return null;
}}
const CART_KEY='shopcart:'+S.slug;
const cart=new Map();
function saveCart(){{try{{localStorage.setItem(CART_KEY,JSON.stringify([...cart.entries()].map(([k,l])=>[k,{{pid:l.pid,qty:l.qty,sel:[...l.sel.entries()]}}])))}}catch(e){{}}}}
function loadCart(){{try{{const raw=localStorage.getItem(CART_KEY);if(!raw)return;
  for(const[k,l]of JSON.parse(raw)){{if(l&&byId(l.pid))cart.set(k,{{pid:l.pid,qty:l.qty||1,sel:new Map(l.sel||[])}});}}}}catch(e){{}}}}
const app=document.getElementById('app');
let query='';
window.menuSearch=v=>{{query=v.trim().toLowerCase();renderMenu();}};
const NEST=S.modifier_nested_groups||{{}};
const byId=id=>S.products.find(x=>x.id===id);
function esc(s){{return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}}
function photo(u,cls){{return u?`<img class="${{cls||''}}" src="${{IMG(u)}}" loading="lazy" alt="" onload="this.classList.add('ld')">`:'';}}
const _IC={{pin:'M480-480q33 0 56.5-23.5T560-560q0-33-23.5-56.5T480-640q-33 0-56.5 23.5T400-560q0 33 23.5 56.5T480-480Zm0 294q122-112 181-203.5T720-552q0-109-69.5-178.5T480-800q-141 0-210.5 69.5T200-552q0 71 59 162.5T480-186Z',
call:'M798-120q-125 0-247-54.5T329-329Q229-429 174.5-551T120-798q0-18 12-30t30-12h162q14 0 25 9.5t13 22.5l26 140q2 16-1 27t-11 19l-97 98q20 37 47.5 71.5T387-386q31 31 65 57.5t72 48.5l94-94q9-9 23.5-13.5T670-390l138 28q14 4 23 14.5t9 23.5v162q0 18-12 30t-30 12ZM241-600l66-66-17-94h-89q5 41 14 81t26 79Zm358 358q39 17 79.5 27t81.5 13v-88l-94-19-67 67ZM241-600Zm358 358Z',
truck:'M240-160q-50 0-85-35t-35-85H40v-440h80l96-160h384l96 160h224v440h-80q0 50-35 85t-85 35q-50 0-85-35t-35-85H360q0 50-35 85t-85 35Zm0-80q17 0 28.5-11.5T280-280q0-17-11.5-28.5T240-320q-17 0-28.5 11.5T200-280q0 17 11.5 28.5T240-240Zm480 0q17 0 28.5-11.5T760-280q0-17-11.5-28.5T720-320q-17 0-28.5 11.5T680-280q0 17 11.5 28.5T720-240ZM160-360h640v-200H160v200Z',
store:'M160-720v-80h640v80H160Zm0 560v-280h-40v-80l40-200h640l40 200v80h-40v280h-80v-280H560v280H160Zm80-80h240v-200H240v200Zm-30-280h540-540Zm0 0h540l-25-120H235l-25 120Z',
clock:'m612-292 56-56-148-148v-184h-80v216l172 172ZM480-80q-83 0-156-31.5T197-197q-54-54-85.5-127T80-480q0-83 31.5-156T197-763q54-54 127-85.5T480-880q83 0 156 31.5T763-763q54 54 85.5 127T880-480q0 83-31.5 156T763-197q-54 54-127 85.5T480-80Zm0-400Zm0 320q133 0 226.5-93.5T800-480q0-133-93.5-226.5T480-800q-133 0-226.5 93.5T160-480q0 133 93.5 226.5T480-160Z',
restaurant:'M280-600v-240q0-17 11.5-28.5T320-880q17 0 28.5 11.5T360-840v240h40v-240q0-17 11.5-28.5T440-880q17 0 28.5 11.5T480-840v240q0 56-34.5 98T360-446v326q0 17-11.5 28.5T320-80q-17 0-28.5-11.5T280-120v-326q-51-14-85.5-56T160-600v-240q0-17 11.5-28.5T200-880q17 0 28.5 11.5T240-840v240h40Zm400 200h-80q-17 0-28.5-11.5T560-440v-240q0-70 51.5-135T718-880q18 0 30 14t12 33v713q0 17-11.5 28.5T720-80q-17 0-28.5-11.5T680-120v-280Z'}};
const ic=n=>`<svg viewBox="0 -960 960 960"><path d="${{_IC[n]}}"/></svg>`;
function selHash(sel){{return [...sel.entries()].sort().map(([o,q])=>o+'x'+q).join(',');}}
function cartQty(pid){{let n=0;for(const l of cart.values())if(l.pid===pid)n+=l.qty;return n;}}
function unitPrice(p,sel){{let abs=0,delta=0;
  const walk=groups=>{{for(const g of groups)for(const o of g.options){{const q=sel.get(o.id)||0;
    if(!q)continue;
    if(g.price_mode==='absolute')abs+=o.price_minor*q;else delta+=o.price_minor*q;
    if(o.nested_group_id&&NEST[o.nested_group_id])walk([NEST[o.nested_group_id]]);}}}};
  walk(p.modifier_groups||[]);
  return (abs||p.price_minor)+delta;}}
function modsText(p,sel){{const names=[];
  const walk=groups=>{{for(const g of groups)for(const o of g.options){{const q=sel.get(o.id)||0;
    if(!q)continue;names.push(q>1?o.name+' ×'+q:o.name);
    if(o.nested_group_id&&NEST[o.nested_group_id])walk([NEST[o.nested_group_id]]);}}}};
  walk(p.modifier_groups||[]);return names.join(', ');}}
function priceLabel(p){{return (p.modifier_groups&&p.modifier_groups.length)?'от '+fmt(p.price_from_minor!=null?p.price_from_minor:p.price_minor):fmt(p.price_minor);}}
function promoApplies(a,pid){{if(!a)return false;
  const ids=a.product_ids;if(Array.isArray(ids)&&ids.length)return ids.includes(pid);
  if(a.type==='fixed_bundle_price'&&Array.isArray(a.items))return a.items.some(i=>i.product_id===pid);
  return a.type==='n_plus_m_free'||a.type==='percent_items';}}
function portionOf(p){{return p.portion?`<span class="portion">${{esc(p.portion)}}</span>`:'';}}
const DEFS=S.badge_defs||{{}};
function tags(p){{return (p.badges||[]).map(b=>{{const d=DEFS[b];
  return d?`<span class="ptag">${{d.icon_path?`<svg viewBox="0 -960 960 960"><path d="${{d.icon_path}}"/></svg>`:''}}${{esc(d.label)}}</span>`:'';}}).join('');}}
function badge(pid){{const pr=(S.promos||[]).find(x=>promoApplies(x.action,pid));
  return pr?`<span class="pbadge">${{esc(pr.name)}}</span>`:'';}}
function qtyCtl(p){{const hasMod=p.modifier_groups&&p.modifier_groups.length;
  const q=cartQty(p.id);
  if(hasMod)return `<button class="add" onclick="customize('${{p.id}}')">${{q?'Выбрать · '+q:'Выбрать'}}</button>`;
  const l=cart.get(p.id+'#');const n=l?l.qty:0;
  if(!n)return `<button class="add" onclick="addPlain('${{p.id}}',1)">В корзину</button>`;
  return `<span class="stepper"><button class="ghost" onclick="addPlain('${{p.id}}',-1)">−</button><span>${{n}}</span><button onclick="addPlain('${{p.id}}',1)">+</button></span>`;}}
function refreshQty(pid){{document.querySelectorAll(`[data-qty="${{pid}}"]`).forEach(el=>{{el.innerHTML=qtyCtl(byId(pid));}});}}
const STOP=`onclick="event.stopPropagation()"`;
function rowList(ps){{return ps.map(p=>`<div class="item" data-pid="${{esc(p.id)}}" onclick="openProduct('${{p.id}}')">${{photo(p.photo_file_id)}}<div class="b"><h3>${{esc(p.name)}}${{badge(p.id)}}${{tags(p)}}${{portionOf(p)}}</h3>${{p.description?`<p>${{esc(p.description)}}</p>`:''}}<div class="row" ${{STOP}}><span class="price">${{priceLabel(p)}}</span><span data-qty="${{p.id}}">${{qtyCtl(p)}}</span></div></div></div>`).join('');}}
function rowGrid(ps){{return `<div class="grid">`+ps.map(p=>`<div class="gcard" data-pid="${{esc(p.id)}}" onclick="openProduct('${{p.id}}')">${{photo(p.photo_file_id)}}<div class="b"><h3>${{esc(p.name)}}${{badge(p.id)}}${{tags(p)}}${{portionOf(p)}}</h3>${{p.description?`<p>${{esc(p.description)}}</p>`:''}}<div class="row" ${{STOP}}><span class="price">${{priceLabel(p)}}</span><span data-qty="${{p.id}}">${{qtyCtl(p)}}</span></div></div></div>`).join('')+`</div>`;}}
function rowCompact(ps){{return ps.map(p=>`<div class="item" data-pid="${{esc(p.id)}}" onclick="openProduct('${{p.id}}')"><div class="b"><h3>${{esc(p.name)}}${{badge(p.id)}}${{tags(p)}}${{portionOf(p)}}</h3>${{p.description?`<p>${{esc(p.description)}}</p>`:''}}</div><span class="price">${{priceLabel(p)}}</span><span data-qty="${{p.id}}" ${{STOP}}>${{qtyCtl(p)}}</span></div>`).join('');}}
const ITEMS=PRESET==='grid'?rowGrid:(PRESET==='compact'?rowCompact:rowList);
function render(){{
  const hb=hoursBadge();
  let h=`<div class="hero">${{photo(S.cover_file_id,'bg')}}<div class="veil"></div><div class="head">${{photo(S.logo_file_id,'logo')}}<div><h1 class="serif">${{esc(S.name)}}</h1>${{S.description?`<div class="desc">${{esc(S.description)}}</div>`:''}}</div></div></div>
  <div class="meta">${{hb?`<span class="${{hb.open?'ob-open':'ob-closed'}}">${{ic('clock')}}${{hb.t}}</span>`:''}}${{S.city||S.address?`<span>${{ic('pin')}}${{esc([S.city,S.address].filter(Boolean).join(', '))}}</span>`:''}}${{S.phone?`<span>${{ic('call')}}${{esc(S.phone)}}</span>`:''}}${{S.delivery_enabled?`<span>${{ic('truck')}}Доставка</span>`:''}}${{S.pickup_enabled?`<span>${{ic('store')}}Самовывоз</span>`:''}}${{S.onsite_enabled?`<span>${{ic('restaurant')}}В заведении</span>`:''}}</div>`;
  if(!S.products.length){{app.innerHTML=h+`<div class="empty">Меню скоро появится</div>`;return;}}
  h+=`<div id="msw"></div><div id="menu"></div>`;
  app.innerHTML=h;
  if(S.products.length>=6){{document.getElementById('msw').innerHTML=`<div class="msearch"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input type="search" placeholder="Поиск по меню" autocomplete="off" oninput="menuSearch(this.value)"></div>`;}}
  renderMenu();
}}
let queue=[],spyIO=null,moreIO=null;
function spy(root){{if(!spyIO)return;
  root.querySelectorAll('.cat[id]:not([data-spy])').forEach(h=>{{h.dataset.spy='1';spyIO.observe(h);}});}}
function activate(id){{document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('on',b.dataset.cat===id));
  const t=document.querySelector(`.tabs button[data-cat="${{CSS.escape(id)}}"]`);
  t?.scrollIntoView({{inline:'center',block:'nearest'}});}}
function chunkHtml(b){{const t=b.depth?3:2;
  return `<div class="mchunk">${{b.name?`<h${{t}} class="cat serif${{b.depth?' sub':''}}"${{b.id?` id="${{b.id}}" data-root="${{b.root}}"`:""}}${{b.depth?` style="margin-left:${{Math.min(b.depth,4)*16}}px"`:''}}>${{esc(b.name)}}</h${{t}}>`:''}}${{ITEMS(b.items)}}</div>`;}}
function renderMenu(){{
  const menu=document.getElementById('menu');if(!menu)return;
  spyIO?.disconnect();moreIO?.disconnect();queue=[];
  const other=S.products.filter(p=>!p.category_id);
  if(query){{
    app.classList.add('flat');
    const hits=S.products.filter(p=>p.name.toLowerCase().includes(query)||(p.description||'').toLowerCase().includes(query));
    menu.innerHTML=hits.length?ITEMS(hits):`<div class="empty">По запросу «${{esc(query)}}» ничего не нашлось</div>`;
    return;
  }}
  // Прогрессивный рендер: табы сразу, тело дорисовывается чанками по мере скролла —
  // все данные уже в снапшоте, поэтому подгрузка мгновенная и бесшовная.
  // Дерево категорий: секции в depth-first порядке; категория видна, когда в её
  // поддереве есть товары; узел с родителем вне снапшота считается корнем.
  const CH=12,blocks=[],byId={{}};
  for(const c of S.categories)byId[c.id]=c;
  const prods=cid=>S.products.filter(p=>p.category_id===cid);
  const kids=p=>S.categories.filter(c=>((c.parent_id&&byId[c.parent_id])?c.parent_id:null)===p).sort((a,b)=>a.sort-b.sort);
  const subHas=c=>prods(c.id).length>0||kids(c.id).some(subHas);
  const roots=kids(null).filter(subHas);
  app.classList.toggle('flat',roots.length+(other.length?1:0)<=1);
  const push=(id,name,depth,root,items)=>{{
    if(!items.length){{blocks.push({{id:'c-'+id,name,depth,root,items:[]}});return;}}
    for(let i=0;i<items.length;i+=CH)
      blocks.push({{id:i===0?'c-'+id:'',name:i===0?name:'',depth,root,items:items.slice(i,i+CH)}});}};
  for(const r of roots){{const walk=(c,depth)=>{{push(c.id,c.name,depth,r.id,prods(c.id));
    for(const k of kids(c.id))if(subHas(k))walk(k,depth+1);}};walk(r,0);}}
  if(other.length)push('other','Ещё',0,'other',other);
  menu.innerHTML=`<div class="tabs">${{roots.map(c=>`<button data-cat="${{c.id}}" onclick="jump('${{c.id}}')">${{esc(c.name)}}</button>`).join('')}}${{other.length?`<button data-cat="other" onclick="jump('other')">Ещё</button>`:''}}</div><div id="mbody"></div><div id="msent"><div class="msk"></div><div class="msk"></div></div>`;
  const body=menu.querySelector('#mbody'),sent=menu.querySelector('#msent');
  queue=blocks;
  const flush=()=>{{const b=queue.shift();
    if(!b){{sent.remove();moreIO?.disconnect();return;}}
    body.insertAdjacentHTML('beforeend',chunkHtml(b));
    spy(body);}};
  const first=roots[0]?.id||(other.length?'other':'');
  if(first)activate(first);
  for(let i=0;i<3&&queue.length;i++)flush();
  spyIO=new IntersectionObserver(es=>{{for(const e of es)if(e.isIntersecting)activate(e.target.dataset.root);}},{{rootMargin:'-30% 0px -60% 0px'}});
  spy(body);
  moreIO=new IntersectionObserver(es=>{{if(es[0].isIntersecting)for(let i=0;i<2&&queue.length;i++)flush();}},{{rootMargin:'1000px 0px'}});
  if(queue.length)moreIO.observe(sent);else sent.remove();
}}
window.jump=id=>{{
  let el=document.getElementById('c-'+id);
  const m=document.getElementById('mbody'),sent=document.getElementById('msent');
  while(!el&&queue.length&&m&&sent){{
    const b=queue.shift();
    m.insertAdjacentHTML('beforeend',chunkHtml(b));
    spy(m);
    if(!queue.length)sent.remove();
    el=document.getElementById('c-'+id);
  }}
  el?.scrollIntoView({{behavior:'smooth',block:'start'}});}};
window.haptic=()=>{{if(navigator.vibrate)navigator.vibrate(8);}};
window.addPlain=(pid,d)=>{{const key=pid+'#';const l=cart.get(key)||{{pid,sel:new Map(),qty:0}};
  l.qty+=d;if(l.qty<=0)cart.delete(key);else cart.set(key,l);if(d>0)haptic();refreshQty(pid);draw();}};
window.addLine=(key,d)=>{{const l=cart.get(key);if(!l)return;l.qty+=d;
  if(l.qty<=0)cart.delete(key);else cart.set(key,l);refreshQty(l.pid);draw();}};
function total(){{let t=0;for(const l of cart.values()){{const p=byId(l.pid);if(p)t+=unitPrice(p,l.sel)*l.qty;}}return t;}}
function count(){{let n=0;for(const l of cart.values())n+=l.qty;return n;}}
function draw(){{const b=document.getElementById('cart');const n=count();saveCart();
  if(n){{b.textContent=`Корзина · ${{n}} · ${{fmt(total())}} →`;b.classList.add('show');
    if(n>(b._n||0)){{b.classList.remove('pop');void b.offsetWidth;b.classList.add('pop');}}}}else b.classList.remove('show');
  b._n=n;}}
let dtype='';
let tableId=TABLE_ID&&TABLES.some(t=>t.id===TABLE_ID)?TABLE_ID:'';
const DTYPES=[['delivery','truck','Доставка',S.delivery_enabled],['pickup','store','Самовывоз',S.pickup_enabled],['onsite','restaurant','В заведении',S.onsite_enabled&&TABLES.length>0]].filter(d=>d[3]);
window.openSheet=()=>{{
  if(!dtype)dtype=(tableId&&S.onsite_enabled)?'onsite':(DTYPES[0]?DTYPES[0][0]:'');
  renderSheet();
  sheetOpen(document.getElementById('sheet'));
}};
window.setDtype=t=>{{dtype=t;renderSheet();}};
window.setTable=t=>{{tableId=t;}};
function renderSheet(){{
  const p=document.getElementById('panel');
  const sub=total();
  const fee=dtype==='delivery'?(S.delivery_fee_minor||0):0;
  const below=S.min_order_minor&&sub<S.min_order_minor;
  const hb=hoursBadge();
  const seg=DTYPES.length>1?`<div class="seg">${{DTYPES.map(d=>`<button class="${{dtype===d[0]?'on':''}}" onclick="setDtype('${{d[0]}}')">${{ic(d[1])}}${{d[2]}}</button>`).join('')}}</div>`:'';
  p.innerHTML=`<h2>Ваш заказ</h2>`+[...cart.entries()].map(([key,l])=>{{const x=byId(l.pid);if(!x)return'';
    const mods=modsText(x,l.sel);const u=unitPrice(x,l.sel);
    return `<div class="cl"><span class="n">${{esc(x.name)}}${{mods?`<span class="mods">${{esc(mods)}}</span>`:''}}</span><span class="stepper"><button class="ghost" onclick="addLine('${{key}}',-1);renderSheet()">−</button><span>${{l.qty}}</span><button onclick="addLine('${{key}}',1);renderSheet()">+</button></span><b class="s">${{fmt(u*l.qty)}}</b></div>`;}}).join('')+
  seg+
  `<div id="savings"></div>`+
  (dtype==='delivery'?`<div class="cl"><span>Доставка</span><b class="s" id="feeVal">${{fmt(fee)}}</b></div>`:'')+
  `<div class="cl" style="border-bottom:0"><b>Итого</b><b class="s" id="cartTotal" style="font-size:18px">${{fmt(sub+fee)}}</b></div>
  <input class="f" id="cn" placeholder="Ваше имя"><input class="f" id="cp" type="tel" placeholder="${{dtype==='onsite'?'Телефон (необязательно)':'Телефон'}}">
  ${{dtype==='onsite'?`<select class="f" id="ct" onchange="setTable(this.value)"><option value="">Выберите стол</option>${{TABLES.map(t=>`<option value="${{t.id}}"${{t.id===tableId?' selected':''}}>${{esc(t.label)}}</option>`).join('')}}</select>`:''}}
  ${{dtype==='delivery'?'<input class="f" id="ca" placeholder="Адрес доставки">':''}}<input class="f" id="cc" placeholder="Комментарий к заказу">
  ${{below?`<div class="minwarn">Минимальный заказ — ${{fmt(S.min_order_minor)}}</div>`:''}}
  ${{hb&&!hb.open?`<div class="minwarn">Сейчас закрыто — оформите предзаказ, примем к открытию</div>`:''}}
  <button class="big" id="payBtn" ${{below?'disabled':''}} onclick="submit()">Оформить заказ · ${{fmt(sub+fee)}}</button>`;
  refreshSavings();
}};
let priceReq=0;
async function refreshSavings(){{
  const my=++priceReq;
  try{{
    const body={{items:[...cart.values()].map(l=>({{product_id:l.pid,qty:l.qty,
      selections:[...l.sel.entries()].map(([option_id,qty])=>({{option_id,qty}}))}})),
      delivery_type:dtype}};
    const r=await fetch(`/shop/api/v1/public/storefront/${{S.slug}}/cart/price`,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});
    if(my!==priceReq||!r.ok)return;
    const d=await r.json();
    const el=document.getElementById('savings');
    if(el)el.innerHTML=d.discount_minor>0
      ?`<div class="cl save"><span>Выгода${{d.applied_promos.length?' · '+esc(d.applied_promos.map(a=>a.name).join(', ')):''}}</span><b class="s">−${{fmt(d.discount_minor)}}</b></div>`:'';
    const fv=document.getElementById('feeVal');
    if(fv&&dtype==='delivery')fv.textContent=fmt(d.delivery_fee_minor);
    const tot=document.getElementById('cartTotal');
    if(tot)tot.textContent=fmt(d.total_minor);
    const btn=document.getElementById('payBtn');
    if(btn&&!btn.disabled)btn.textContent='Оформить заказ · '+fmt(d.total_minor);
  }}catch(e){{}}
}}
window.closeSheet=()=>sheetBack(document.getElementById('sheet'));
window.submit=async()=>{{
  if(dtype==='onsite'&&!tableId){{toast('Выберите стол');return;}}
  if(dtype!=='onsite'&&document.getElementById('cp').value.trim().length<5){{toast('Укажите телефон');return;}}
  const body={{items:[...cart.values()].map(l=>({{product_id:l.pid,qty:l.qty,
    selections:[...l.sel.entries()].map(([option_id,qty])=>({{option_id,qty}}))}})),
    customer_name:document.getElementById('cn').value,customer_phone:document.getElementById('cp').value,
    delivery_type:dtype,
    table_id:dtype==='onsite'?tableId:null,
    address:dtype==='delivery'?(document.getElementById('ca')?.value||''):'',
    comment:document.getElementById('cc').value,
    source:EMBED?'embed':'web',
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
  const render=(st,d)=>{{const hall=d&&d.delivery_type==='onsite'&&d.table_label?`<br>Ваш стол: ${{esc(d.table_label)}}`:'';
    p.innerHTML=`<div class="done"><h2 class="serif">Заказ принят!</h2><div class="code">#${{code}}</div><div class="st">${{STATUS_LABEL[st]||st}}</div><p>Сохраните номер заказа — по нему можно проверить статус.${{hall}}<br>Мы свяжемся с вами для подтверждения.</p></div>`;}};
  render('new');
  const poll=async()=>{{
    if(!document.getElementById('sheet').classList.contains('show'))return;
    try{{
      const r=await fetch(`/shop/api/v1/public/orders/${{code}}`);
      if(r.ok){{const d=await r.json();render(d.status,d);if(d.status!=='done'&&d.status!=='cancelled')setTimeout(poll,15000);}}
      else setTimeout(poll,30000);
    }}catch(e){{setTimeout(poll,30000);}}
  }};
  setTimeout(poll,15000);
}};
let cust=null;
function findGroup(pid,gid){{const p=byId(pid);
  for(const g of p.modifier_groups||[])if(g.id===gid)return g;
  for(const k in NEST)if(NEST[k].id===gid)return NEST[k];return null;}}
function applyDefaults(pid){{const p=byId(pid);
  const walk=groups=>{{for(const g of groups)for(const o of g.options){{if(o.is_default)cust.sel.set(o.id,1);
    if(o.is_default&&o.nested_group_id&&NEST[o.nested_group_id])walk([NEST[o.nested_group_id]]);}}}};
  walk(p.modifier_groups||[]);}}
window.customize=pid=>{{cust={{pid,sel:new Map(),qty:1}};applyDefaults(pid);
  renderCust();sheetOpen(document.getElementById('csheet'));}};
window.openProduct=pid=>customize(pid);
window.closeCust=()=>sheetBack(document.getElementById('csheet'));
const SHARE_ICON='<svg viewBox="0 -960 960 960"><path d="M720-80q-50 0-85-35t-35-85q0-7 1-14.5t3-13.5L322-392q-17 15-38 23.5t-44 8.5q-50 0-85-35t-35-85 35-85 85-35q23 0 44 8.5t38 23.5l282-164q-2-6-3-13.5t-1-14.5q0-50 35-85t85-35 85 35 35 85-35 85-85 35q-23 0-44-8.5T638-672L356-508q2 6 3 13.5t1 14.5-1 14.5-3 13.5l282 164q17-15 38-23.5t44-8.5q50 0 85 35t35 85-35 85-85 35Z"/></svg>';
let toastTimer=0;
window.toast=msg=>{{const t=document.getElementById('toast');if(!t)return;
  t.textContent=msg;t.classList.add('show');
  clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('show'),2200);}};
window.shareProduct=pid=>{{const url=location.origin+location.pathname+'?p='+pid;
  if(navigator.share)navigator.share({{url}}).catch(()=>{{}});
  else if(navigator.clipboard)navigator.clipboard.writeText(url).then(()=>toast('Ссылка скопирована'),()=>{{}});
  else toast(url);}};
document.addEventListener('keydown',e=>{{if(e.key==='Escape'){{closeCust();closeSheet();}}}});
let sheetDepth=0,popGuard=0;
function syncLock(){{document.body.classList.toggle('lock',!!document.querySelector('.sheet.show'));}}
function sheetOpen(el){{el.classList.add('show');sheetDepth++;history.pushState({{sh:1}},'');syncLock();}}
function sheetBack(el){{if(!el.classList.contains('show'))return;
  el.classList.remove('show');if(sheetDepth>0){{sheetDepth--;popGuard++;history.back();}}syncLock();}}
window.addEventListener('popstate',()=>{{if(popGuard>0){{popGuard--;return;}}
  const list=document.querySelectorAll('.sheet.show');const s=list[list.length-1];
  if(s){{s.classList.remove('show');sheetDepth=Math.max(0,sheetDepth-1);syncLock();}}}});
let dragY=null,dragEl=null;
document.addEventListener('touchstart',e=>{{const p=e.target.closest('.panel');if(!p)return;
  if(matchMedia('(min-width:1024px)').matches)return;
  if(e.touches[0].clientY-p.getBoundingClientRect().top>46)return;
  dragY=e.touches[0].clientY;dragEl=p;p.classList.add('drag');}},{{passive:true}});
document.addEventListener('touchmove',e=>{{if(dragY==null)return;
  const dy=Math.max(0,e.touches[0].clientY-dragY);
  if(dy>0)e.preventDefault();
  dragEl.style.transform=`translateX(-50%) translateY(${{dy}}px)`;}},{{passive:false}});
document.addEventListener('touchend',e=>{{if(dragY==null)return;
  const dy=Math.max(0,e.changedTouches[0].clientY-dragY);
  const p=dragEl;p.classList.remove('drag');p.style.transform='';dragY=dragEl=null;
  if(dy>90)sheetBack(p.parentElement);}});
function groupSelectedQty(g){{let n=0;for(const o of g.options)n+=cust.sel.get(o.id)||0;return n;}}
window.optToggle=(pid,gid,oid)=>{{const g=findGroup(pid,gid);if(!g)return;
  if(g.selection_mode==='single'){{for(const o of g.options)cust.sel.delete(o.id);cust.sel.set(oid,1);}}
  else if(cust.sel.has(oid))cust.sel.delete(oid);
  else{{const n=groupSelectedQty(g);if(g.max_selected!=null&&n>=g.max_selected)return;cust.sel.set(oid,1);}}
  renderCust();}};
window.optQty=(pid,gid,oid,d)=>{{const g=findGroup(pid,gid);if(!g)return;
  const o=g.options.find(x=>x.id===oid);if(!o)return;
  const q=(cust.sel.get(oid)||0)+d;
  if(q<=0)cust.sel.delete(oid);
  else{{if(q>o.max_per_option)return;
    if(d>0&&g.max_selected!=null&&groupSelectedQty(g)>=g.max_selected&&!cust.sel.has(oid))return;
    if(d>0&&g.max_selected!=null&&groupSelectedQty(g)>=g.max_selected&&q>(cust.sel.get(oid)||0))return;
    cust.sel.set(oid,q);}}
  renderCust();}};
window.custQty=d=>{{cust.qty=Math.max(1,(cust.qty||1)+d);renderCust();}};
function selValid(p){{const check=groups=>{{
    for(const g of groups){{const n=groupSelectedQty(g);
      if(n<(g.min_selected||0))return false;
      if(g.selection_mode==='single'&&n>1)return false;
      if(g.max_selected!=null&&n>g.max_selected)return false;
      for(const o of g.options){{const q=cust.sel.get(o.id)||0;
        if(q>(o.max_per_option||1))return false;
        if(q>0&&o.nested_group_id&&NEST[o.nested_group_id]&&!check([NEST[o.nested_group_id]]))return false;}}}}
    return true;}};
  return check(p.modifier_groups||[]);}}
function groupHtml(p,g,depth){{const n=groupSelectedQty(g);const req=g.min_selected>0;
  const lim=g.max_selected!=null?`до ${{g.max_selected}}`:'';
  const okSel=n>=(g.min_selected||0);
  let h=`<div class="mg${{depth?' nest':''}}"><div class="mg-h"><b>${{esc(g.name)}}</b><span class="mg-r${{okSel?' ok':''}}">${{req?(lim?`обязательно · ${{lim}}`:'обязательно'):lim}}</span></div><div class="opts">`;
  for(const o of g.options){{const q=cust.sel.get(o.id)||0;
    const pr=o.price_minor?`<i>${{g.price_mode==='absolute'?fmt(o.price_minor):'+'+fmt(o.price_minor)}}</i>`:'';
    const maxed=g.max_selected!=null&&n>=g.max_selected&&!q;
    if(o.max_per_option>1&&q)
      h+=`<span class="opt on"><span class="stepper"><button class="ghost" onclick="optQty('${{p.id}}','${{g.id}}','${{o.id}}',-1)">−</button><span>${{q}}</span><button onclick="optQty('${{p.id}}','${{g.id}}','${{o.id}}',1)">+</button></span>${{esc(o.name)}}${{pr}}</span>`;
    else
      h+=`<button class="opt${{q?' on':''}}${{maxed?' dis':''}}" onclick="optToggle('${{p.id}}','${{g.id}}','${{o.id}}')">${{esc(o.name)}}${{pr}}</button>`;}}
  h+='</div>';
  for(const o of g.options){{const q=cust.sel.get(o.id)||0;
    if(q&&o.nested_group_id&&NEST[o.nested_group_id])h+=groupHtml(p,NEST[o.nested_group_id],depth+1);}}
  return h+'</div>';}}
function renderCust(){{if(!cust)return;const p=byId(cust.pid);if(!p)return;
  const ok=selValid(p);const u=unitPrice(p,cust.sel);
  document.getElementById('cpanel').innerHTML=
    `<button class="pshare" onclick="shareProduct('${{p.id}}')" aria-label="Поделиться">${{SHARE_ICON}}</button>`+
    `${{photo(p.photo_file_id,'phero')}}<h2>${{esc(p.name)}}${{tags(p)}}${{portionOf(p)}}</h2>`+
    `${{p.description?`<p class="pdesc">${{esc(p.description)}}</p>`:''}}`+
    (p.modifier_groups||[]).map(g=>groupHtml(p,g,0)).join('')+
    `<div class="crow"><span class="stepper"><button class="ghost" onclick="custQty(-1)">−</button><span>${{cust.qty}}</span><button onclick="custQty(1)">+</button></span></div>`+
    `<button class="big"${{ok?'':' disabled'}} onclick="addCustom()">В корзину · ${{fmt(u*cust.qty)}}</button>`;}}
window.addCustom=()=>{{if(!cust)return;const p=byId(cust.pid);
  if(!p||!selValid(p))return;
  const key=cust.pid+'#'+selHash(cust.sel);
  const l=cart.get(key)||{{pid:cust.pid,sel:new Map(cust.sel),qty:0}};
  l.qty+=cust.qty;cart.set(key,l);
  cust=null;closeCust();refreshQty(p.id);draw();}};
render();
loadCart();for(const l of cart.values())refreshQty(l.pid);draw();
const deeplink=new URLSearchParams(location.search).get('p');
if(deeplink){{const el=document.querySelector('[data-pid="'+CSS.escape(deeplink)+'"]');
  if(el){{el.classList.add('flash');setTimeout(()=>el.scrollIntoView({{behavior:'smooth',block:'center'}}),200);}}}}
</script>
</body>
</html>"""


_JSONLD_TYPES: dict[str, str] = {
    "restaurant": "Restaurant",
    "cafe": "CafeOrCoffeeShop",
    "bakery": "Bakery",
    "shop": "Store",
}
_DAYS: tuple[str, ...] = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")

_DEFAULT_ACCENT = "#e2553f"

_Rgb = tuple[int, int, int]
# Фоны тем из CSS — производные accent-токены считаются под конкретный фон.
_BG_DARK: _Rgb = (0x13, 0x11, 0x10)
_BG_LIGHT: _Rgb = (0xF5, 0xF4, 0xF2)
_TEXT_DARK: _Rgb = (0xF7, 0xF3, 0xEC)
_TEXT_LIGHT: _Rgb = (0x1D, 0x1A, 0x16)


def hex_rgb(value: str) -> _Rgb:
    """'#rgb'/'#rrggbb' → (r,g,b); невалидный ввод — rgb дефолтного accent."""
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    try:
        if len(s) != 6:
            raise ValueError(value)
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return (0xE2, 0x55, 0x3F)


def rel_luminance(rgb: _Rgb) -> float:
    """Относительная яркость WCAG 2.x."""

    def lin(channel: int) -> float:
        c = channel / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2])


def contrast_ratio(a: _Rgb, b: _Rgb) -> float:
    hi = max(rel_luminance(a), rel_luminance(b))
    lo = min(rel_luminance(a), rel_luminance(b))
    return (hi + 0.05) / (lo + 0.05)


def to_hex(rgb: _Rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def mix_rgb(a: _Rgb, b: _Rgb, t: float) -> _Rgb:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def on_accent(accent: _Rgb) -> str:
    """Текст на accent-кнопке: белый, пока контраст ≥3; иначе тёмный."""
    return "#fff" if contrast_ratio(accent, (255, 255, 255)) >= 3.0 else "#1d1a16"


def accent_fg(accent: _Rgb, bg: _Rgb, text: _Rgb) -> str:
    """Accent для текста/иконок на фоне: доводится смесью к text до контраста 4.5."""
    for step in range(0, 21):
        cand = mix_rgb(accent, text, step / 20)
        if contrast_ratio(cand, bg) >= 4.5:
            return to_hex(cand)
    return to_hex(text)


def accent_vars(accent: str) -> dict[str, str]:
    """Производные токены accent для шаблона: --on-accent и --afg под каждую тему."""
    rgb = hex_rgb(accent)
    return {
        "on_accent": on_accent(rgb),
        "afg_dark": accent_fg(rgb, _BG_DARK, _TEXT_DARK),
        "afg_light": accent_fg(rgb, _BG_LIGHT, _TEXT_LIGHT),
    }


def _opening_hours(snapshot: JsonObject) -> list[JsonObject]:
    """working_hours {day: 'HH:MM-HH:MM'} → schema.org openingHoursSpecification."""
    raw = snapshot.get("working_hours")
    if not isinstance(raw, dict):
        return []
    specs: list[JsonObject] = []
    for day, hours in raw.items():
        if not isinstance(hours, str):
            continue
        if not day.isdigit() or not (0 <= int(day) <= 6) or "-" not in hours:
            continue
        opens, _, closes = hours.partition("-")
        specs.append(
            {
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": _DAYS[int(day)],
                "opens": opens.strip(),
                "closes": closes.strip(),
            }
        )
    return specs


def _menu_items(snapshot: JsonObject) -> list[JsonObject]:
    """Позиции каталога → hasMenu/hasMenuItem с offers для rich-результатов."""
    raw = snapshot.get("products")
    if not isinstance(raw, list):
        return []
    items: list[JsonObject] = []
    for product in raw[:50]:
        if not isinstance(product, dict) or not isinstance(product.get("name"), str):
            continue
        item: JsonObject = {"@type": "MenuItem", "name": product["name"]}
        price = product.get("price_minor")
        currency = snapshot.get("currency")
        if isinstance(price, int) and price > 0 and isinstance(currency, str):
            item["offers"] = {
                "@type": "Offer",
                "price": f"{price / 100:.2f}",
                "priceCurrency": currency,
            }
        description = product.get("description")
        if isinstance(description, str) and description:
            item["description"] = description
        items.append(item)
    return items


def _storefront_jsonld(snapshot: JsonObject, canonical_url: str, image_url: str) -> JsonObject:
    """LocalBusiness-граф витрины: тип по kind, адрес, часы, меню."""
    kind = snapshot.get("kind")
    doc: JsonObject = {
        "@context": "https://schema.org",
        "@type": _JSONLD_TYPES.get(str(kind), "LocalBusiness"),
        "name": snapshot.get("name", ""),
        "url": canonical_url,
    }
    description = snapshot.get("description")
    if isinstance(description, str) and description:
        doc["description"] = description
    if image_url:
        doc["image"] = image_url
    phone = snapshot.get("phone")
    if isinstance(phone, str) and phone:
        doc["telephone"] = phone
    city = snapshot.get("city")
    address = snapshot.get("address")
    if (isinstance(city, str) and city) or (isinstance(address, str) and address):
        doc["address"] = {
            "@type": "PostalAddress",
            **({"addressLocality": city} if isinstance(city, str) and city else {}),
            **({"streetAddress": address} if isinstance(address, str) and address else {}),
        }
    specs = _opening_hours(snapshot)
    if specs:
        doc["openingHoursSpecification"] = specs
    items = _menu_items(snapshot)
    if items:
        doc["hasMenu"] = {"@type": "Menu", "hasMenuItem": items}
    return doc


def _seo_head(
    *,
    title: str,
    description: str,
    canonical_url: str,
    image_url: str,
    jsonld: JsonObject,
) -> str:
    """OG/Twitter мета + canonical + JSON-LD — шаринг и rich snippets."""
    tags = [
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{escape(title)}">',
        f'<meta property="og:description" content="{escape(description)}">',
        '<meta property="og:locale" content="ru_RU">',
        '<meta name="twitter:card" content="summary_large_image">',
    ]
    if canonical_url:
        tags.append(f'<link rel="canonical" href="{escape(canonical_url)}">')
        tags.append(f'<meta property="og:url" content="{escape(canonical_url)}">')
    if image_url:
        tags.append(f'<meta property="og:image" content="{escape(image_url)}">')
    ld = json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/")
    tags.append(f'<script type="application/ld+json">{ld}</script>')
    return "\n".join(tags)


def storefront_html(snapshot: JsonObject, *, canonical_url: str = "", image_url: str = "") -> str:
    """HTML витрины с inline-снапшотом для SSR-lite рендера."""
    accent = _DEFAULT_ACCENT
    preset = "menu"
    mode = "dark"
    theme = snapshot.get("theme")
    if isinstance(theme, dict):
        accent = str(theme.get("accent_color", accent))
        preset = str(theme.get("preset", preset))
        mode = str(theme.get("mode", mode))
    tokens = accent_vars(accent)
    body_class = " ".join(
        part
        for part in (
            "compact" if preset == "compact" else "",
            "light" if mode == "light" else "",
        )
        if part
    )
    title = str(snapshot.get("name", "Витрина"))
    description = str(snapshot.get("description", ""))[:200]
    return _PAGE.format(
        title=escape(title),
        description=escape(description),
        seo_head=_seo_head(
            title=title,
            description=description,
            canonical_url=canonical_url,
            image_url=image_url,
            jsonld=_storefront_jsonld(snapshot, canonical_url, image_url),
        ),
        accent=escape(accent),
        on_accent=tokens["on_accent"],
        afg_dark=tokens["afg_dark"],
        afg_light=tokens["afg_light"],
        body_class=escape(body_class),
        preset=escape(preset),
        snapshot=json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/"),
    )
