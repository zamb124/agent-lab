"""Market shell — публичная страница агрегатора по всем витринам.

Отдаётся анонимно на ``/shop/api/v1/public/market``: снапшот опубликованных
магазинов встроен в HTML, поиск товаров идёт в ``/aggregate/search`` без
перезагрузки. Та же SSR-lite модель, что и у storefront_shell.
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
{seo_head}
<style>
:root{{--accent:{accent};--bg:#100e0c;--card:#1b1815;--card2:#241f1a;--text:#f6f1e8;--muted:#a89e90;--line:#2b251e;--radius:18px}}
*{{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}}
body{{font-family:ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}}
.serif{{font-family:ui-serif,Georgia,'Times New Roman',serif}}
.wrap{{max-width:960px;margin:0 auto;padding:0 16px 120px}}
.hero{{position:relative;margin:0 -16px;padding:96px 24px 72px;text-align:center;background:radial-gradient(120% 140% at 50% 0%,color-mix(in srgb,var(--accent) 26%,transparent) 0%,var(--bg) 68%);overflow:hidden}}
.hero h1{{font-size:clamp(30px,6vw,46px);font-weight:700;letter-spacing:-.02em}}
.hero .sub{{margin-top:12px;color:var(--muted);font-size:15.5px;max-width:520px;margin-left:auto;margin-right:auto;line-height:1.55}}
.search{{position:sticky;top:10px;z-index:5;max-width:560px;margin:26px auto 0;display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--line);border-radius:99px;padding:8px 8px 8px 20px;box-shadow:0 12px 40px rgba(0,0,0,.4)}}
.search svg{{flex-shrink:0;opacity:.55}}
.search input{{flex:1;min-width:0;font:inherit;font-size:16px;background:transparent;border:0;color:var(--text);outline:none}}
.search input::placeholder{{color:var(--muted)}}
.search .go{{font:inherit;font-size:14.5px;font-weight:650;padding:10px 20px;border-radius:99px;border:0;background:var(--accent);color:#fff;cursor:pointer}}
.sec{{margin-top:40px}}
.sec h2{{font-size:21px;letter-spacing:-.01em;margin-bottom:14px}}
.filters{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}}
.chip{{font:inherit;font-size:13.5px;font-weight:600;padding:8px 16px;border-radius:99px;border:1px solid var(--line);background:var(--card);color:var(--muted);cursor:pointer;transition:all .15s ease}}
.chip:hover{{border-color:color-mix(in srgb,var(--accent) 50%,var(--line));color:var(--text)}}
.chip.on{{background:var(--accent);border-color:var(--accent);color:#fff}}
.shops{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}}
.shop{{display:block;background:var(--card);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;text-decoration:none;color:var(--text);transition:transform .15s ease,border-color .15s ease}}
.shop:hover{{transform:translateY(-2px);border-color:color-mix(in srgb,var(--accent) 55%,var(--line))}}
.shop .cover{{height:110px;background:linear-gradient(150deg,color-mix(in srgb,var(--accent) 30%,var(--card2)),var(--card2));position:relative}}
.shop .cover img{{width:100%;height:100%;object-fit:cover}}
.shop .b{{padding:12px 14px 14px;display:flex;gap:10px;align-items:flex-start}}
.shop .logo{{width:40px;height:40px;border-radius:12px;object-fit:cover;background:var(--card2);flex-shrink:0}}
.shop h3{{font-size:15px;font-weight:650}}
.shop .meta{{font-size:12.5px;color:var(--muted);margin-top:3px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;line-height:1.45}}
.results{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}}
.pcard{{display:block;background:var(--card);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;text-decoration:none;color:var(--text);animation:fade .25s ease}}
@keyframes fade{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1}}}}
.pcard img{{width:100%;aspect-ratio:4/3;object-fit:cover;background:var(--card2)}}
.pcard .b{{padding:11px 13px 13px}}
.pcard h3{{font-size:14.5px;font-weight:600}}
.pcard .price{{margin-top:6px;font-size:15px;font-weight:650;font-variant-numeric:tabular-nums}}
.pcard .from{{margin-top:6px;font-size:12px;color:var(--muted);display:inline-block;background:var(--card2);border-radius:99px;padding:3px 10px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.empty{{text-align:center;color:var(--muted);padding:56px 20px;font-size:15px}}
.foot{{margin-top:64px;text-align:center;color:var(--muted);font-size:12.5px;line-height:1.7}}
.foot b{{color:var(--text)}}
@media(max-width:520px){{.hero{{padding:64px 20px 48px}}.shops{{grid-template-columns:1fr 1fr}}.results{{grid-template-columns:1fr 1fr}}}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1 class="serif">{headline}</h1>
    <div class="sub">{subline}</div>
    <form class="search" onsubmit="return runSearch()">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      <input id="q" type="search" placeholder="{search_placeholder}" autocomplete="off" oninput="debounced()">
      <button class="go" type="submit">Найти</button>
    </form>
  </div>
  <div id="hits" class="sec" style="display:none"><h2 id="hitsTitle"></h2><div class="results" id="hitsGrid"></div></div>
  <div class="sec" id="shopsSec">
    <h2>{shops_title}</h2>
    <div class="filters" id="kindChips"></div>
    <div class="filters" id="cityChips"></div>
    <div class="shops" id="shops"></div>
  </div>
  <div class="foot">Сделано на <b>{brand}</b> — собери свою витрину и продавай без комиссий агрегаторов</div>
</div>
<script id="snapshot" type="application/json">{snapshot}</script>
<script>
const S=JSON.parse(document.getElementById('snapshot').textContent);
const fmt=v=>(v/100).toLocaleString('ru-RU')+' ₽';
const IMG=u=>u?`/shop/api/v1/files/download/${{u}}`:'';
const LINK=s=>`/shop/api/v1/public/s/${{s}}`;
function esc(s){{return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}}
const KIND={{restaurant:'Ресторан',cafe:'Кафе',bakery:'Пекарня',shop:'Магазин',other:'Заведение'}};
function shopCard(s){{return `<a class="shop" href="${{LINK(s.slug)}}">
  <span class="cover">${{s.cover_file_id?`<img src="${{IMG(s.cover_file_id)}}" loading="lazy" alt="">`:''}}</span>
  <span class="b">${{s.logo_file_id?`<img class="logo" src="${{IMG(s.logo_file_id)}}" alt="">`:''}}<span>
    <h3>${{esc(s.name)}}</h3>
    <span class="meta">${{esc([KIND[s.kind]||KIND.other,s.city].filter(Boolean).join(' · '))}}${{s.description?`<br>${{esc(s.description)}}`:''}}</span>
  </span></span></a>`;}}
let fKind='',fCity='';
function renderShops(){{
  const list=S.shops.filter(s=>(!fKind||s.kind===fKind)&&(!fCity||s.city===fCity));
  document.getElementById('shops').innerHTML=list.length?list.map(shopCard).join(''):`<div class="empty">Под фильтр ничего не подходит</div>`;
}}
function chips(elId,values,cur,set){{
  const el=document.getElementById(elId);
  if(values.length<2){{el.style.display='none';return;}}
  el.innerHTML=values.map(v=>`<button class="chip${{v.k===cur?' on':''}}" data-v="${{esc(v.k)}}">${{esc(v.t)}}</button>`).join('');
  el.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{{set(c.dataset.v===cur?'':c.dataset.v);renderChips();renderShops();runSearch();}});
}}
function renderChips(){{
  const kinds=[...new Set(S.shops.map(s=>s.kind))].map(k=>({{k,t:KIND[k]||KIND.other}}));
  const cities=[...new Set(S.shops.map(s=>s.city).filter(Boolean))].sort().map(c=>({{k:c,t:c}}));
  chips('kindChips',[{{k:'',t:'Все'}},...kinds],fKind,v=>fKind=v);
  chips('cityChips',[{{k:'',t:'Все города'}},...cities],fCity,v=>fCity=v);
}}
renderChips();renderShops();
let timer=0,req=0;
function debounced(){{clearTimeout(timer);timer=setTimeout(runSearch,350);}}
async function runSearch(){{
  const q=document.getElementById('q').value.trim();
  const sec=document.getElementById('hits');
  if(!q){{sec.style.display='none';return false;}}
  const my=++req;
  try{{
    let url=`/shop/api/v1/public/aggregate/search?q=${{encodeURIComponent(q)}}&limit=24`;
    if(fKind)url+=`&kind=${{fKind}}`;if(fCity)url+=`&city=${{encodeURIComponent(fCity)}}`;
    const r=await fetch(url);
    if(my!==req||!r.ok)return false;
    const d=await r.json();
    document.getElementById('hitsTitle').textContent=`«${{q}}» — найдено ${{d.total}}`;
    document.getElementById('hitsGrid').innerHTML=d.items.length?d.items.map(p=>`<a class="pcard" href="${{LINK(p.shop_slug)}}?p=${{esc(p.product_id)}}">
      ${{p.photo_file_id?`<img src="${{IMG(p.photo_file_id)}}" loading="lazy" alt="">`:''}}
      <span class="b"><h3>${{esc(p.name)}}</h3><div class="price">${{fmt(p.price_minor)}}</div><span class="from">${{esc(p.shop_name)}}</span></span></a>`).join('')
      :`<div class="empty">Ничего не нашлось — попробуйте другое название</div>`;
    sec.style.display='block';
    document.getElementById('hits').scrollIntoView({{behavior:'smooth',block:'start'}});
  }}catch(e){{}}
  return false;
}}
</script>
</body>
</html>"""


def _market_jsonld(snapshot: JsonObject, canonical_url: str) -> JsonObject:
    """ItemList опубликованных витрин для rich-результатов агрегатора."""
    raw = snapshot.get("shops")
    shops = raw if isinstance(raw, list) else []
    items = [
        {
            "@type": "ListItem",
            "position": index + 1,
            "url": shop.get("url", ""),
            "name": shop.get("name", ""),
        }
        for index, shop in enumerate(shops)
        if isinstance(shop, dict) and isinstance(shop.get("name"), str)
    ]
    doc: JsonObject = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": snapshot.get("title", ""),
        "url": canonical_url,
        "mainEntity": {"@type": "ItemList", "itemListElement": items},
    }
    description = snapshot.get("description")
    if isinstance(description, str) and description:
        doc["description"] = description
    return doc


def market_html(snapshot: JsonObject, *, brand: str, canonical_url: str = "") -> str:
    """HTML агрегатора с inline-снапшотом магазинов."""
    title = str(snapshot.get("title", "Витрины рядом"))
    description = str(
        snapshot.get(
            "description",
            "Единая витрина ресторанов и магазинов — заказ напрямую, без комиссий",
        )
    )[:200]
    tags = [
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{escape(title)}">',
        f'<meta property="og:description" content="{escape(description)}">',
        '<meta property="og:locale" content="ru_RU">',
        '<meta name="twitter:card" content="summary">',
    ]
    if canonical_url:
        tags.append(f'<link rel="canonical" href="{escape(canonical_url)}">')
        tags.append(f'<meta property="og:url" content="{escape(canonical_url)}">')
    ld = json.dumps(_market_jsonld(snapshot, canonical_url), ensure_ascii=False).replace(
        "</", "<\\/"
    )
    tags.append(f'<script type="application/ld+json">{ld}</script>')
    return _PAGE.format(
        title=escape(title),
        description=escape(description),
        seo_head="\n".join(tags),
        headline=escape(str(snapshot.get("headline", "Закажите у лучших мест рядом"))),
        subline=escape(
            str(
                snapshot.get(
                    "subline",
                    "Единая витрина ресторанов и магазинов — заказ напрямую, без комиссий",
                )
            )
        ),
        search_placeholder=escape(str(snapshot.get("search_placeholder", "Пицца, суши, цветы…"))),
        shops_title=escape(str(snapshot.get("shops_title", "Витрины"))),
        accent=escape(str(snapshot.get("accent", "#e2553f"))),
        brand=escape(brand),
        snapshot=json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/"),
    )
