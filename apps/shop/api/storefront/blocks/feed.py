"""Витринная лента: сторис-баннеры, полки товаров, фон-витраж, апсейл корзины.

Полки и баннеры приезжают в снапшоте уже разрешёнными (product_ids);
``usual``-полка анонимному снапшоту пуста — дорисовывает ``/personal``.
Блок собирается реестром STOREFRONT_BLOCKS; css/js вставляются
в shell как есть — без экранирования скобок.
"""

CSS: str = """.bnrs{display:flex;gap:10px;overflow-x:auto;padding:14px 2px 4px;scrollbar-width:none}
.bnrs::-webkit-scrollbar{display:none}
.bnr{position:relative;flex:0 0 auto;width:min(300px,78vw);aspect-ratio:19/10;border-radius:var(--radius);overflow:hidden;cursor:pointer;background:var(--card2)}
.bnr .bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.bnr .bveil{position:absolute;inset:0;background:linear-gradient(180deg,transparent 32%,rgba(10,9,8,.8) 100%)}
.bnr .btxt{position:absolute;left:14px;right:14px;bottom:12px;display:flex;flex-direction:column;gap:3px}
.bnr .btxt b{font-size:15.5px;font-weight:650;color:#fff;text-shadow:0 1px 8px rgba(0,0,0,.6)}
.bnr .btxt span{font-size:12.5px;color:rgba(255,255,255,.86);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.bnr.nt{cursor:default}
.sh{margin-top:24px;animation:fade .3s ease}
.sh-h{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;padding:0 2px;margin-bottom:6px}
.sh-h h2{font-size:20px;font-weight:650;letter-spacing:-.01em}
.sh-h .sub{font-size:13px;color:var(--muted);margin-top:3px;font-weight:450}
.sh-h .more{font-size:13.5px;font-weight:600;color:var(--afg);white-space:nowrap;cursor:pointer;padding:4px 0}
.rail{display:flex;gap:12px;overflow-x:auto;padding:6px 2px 4px;scrollbar-width:none;scroll-snap-type:x proximity}
.rail::-webkit-scrollbar{display:none}
.shcard{flex:0 0 auto;width:152px;scroll-snap-align:start;cursor:pointer}
.shcard .ph{position:relative;width:100%;aspect-ratio:1/1;border-radius:var(--radius);overflow:hidden;background:var(--card2)}
.shcard .ph img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.shcard h3{font-size:14px;font-weight:600;margin-top:9px;line-height:1.32;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:2.64em}
.shcard .row{display:flex;justify-content:space-between;align-items:center;margin-top:7px;gap:8px}
.shcard .price{font-size:14.5px}
.shcard .add{padding:8px 14px;font-size:13px}
.sh.hero .shcard{width:min(320px,80vw)}
.sh.hero .shcard .ph{aspect-ratio:16/10}
.sh.hero .shcard h3{font-size:15.5px}
.soon{display:inline-block;font-size:12px;font-weight:650;color:var(--warn);background:color-mix(in srgb,var(--warn) 14%,transparent);padding:6px 12px;border-radius:99px;white-space:nowrap}
.na img{filter:saturate(.35) brightness(.82)}
.na h3,.na p{opacity:.55}
.bdrop{position:fixed;inset:0;z-index:-1;pointer-events:none}
body[data-backdrop=blur] .bdrop{background-size:cover;background-position:center 18%;filter:blur(64px) saturate(1.2);opacity:.5}
body[data-backdrop=blur] .bdrop::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,color-mix(in srgb,var(--bg) 34%,transparent) 0%,var(--bg) 72%)}
body[data-backdrop=gradient] .bdrop{background:linear-gradient(180deg,color-mix(in srgb,var(--accent) 24%,var(--bg)) 0%,var(--bg) 480px)}"""

JS: str = """const SHELVES=Array.isArray(S.shelves)?S.shelves:[];
const BANNERS=Array.isArray(S.banners)?S.banners:[];
const SUBS=new Set();
const SHELF_TITLES={new:'Новинки',hits:'Популярное',comeback:'Скоро вернётся',usual:'Как всегда',upsell:'Добавить к заказу'};
function bannerLive(b){const w=b.window||{};const now=Date.now();
  if(w.from&&Date.parse(w.from)>now)return false;
  if(w.to&&Date.parse(w.to)<now)return false;return true;}
window.bannerGo=id=>{const b=BANNERS.find(x=>x.id===id);if(!b)return;const link=b.link||'';
  if(link.startsWith('product:')){openProduct(link.slice(8));}
  else if(link.startsWith('category:')){jump(link.slice(9));}
  else if(link.startsWith('shelf:')){document.getElementById('sh-'+link.slice(6))?.scrollIntoView({behavior:'smooth',block:'start'});}
  else if(link.startsWith('url:')){window.open(link.slice(4),'_blank','noopener');}};
function bannerHtml(b){const t=b.title||'',st=b.subtitle||'';
  return `<div class="bnr${b.link?'':' nt'}" onclick="bannerGo('${b.id}')">${photo(b.image_file_id,'bg','md')}${t||st?`<div class="bveil"></div><div class="btxt">${t?`<b>${esc(t)}</b>`:''}${st?`<span>${esc(st)}</span>`:''}</div>`:''}</div>`;}
function shCard(p){const na=p.is_available===false;
  return `<div class="shcard${na?' na':''}" data-pid="${esc(p.id)}" onclick="openProduct('${p.id}')"><div class="ph">${photo(p.photo_file_id,'','md!sq')}</div><h3>${esc(p.name)}</h3><div class="row" ${STOP}><span class="price">${priceLabel(p)}</span>${na?'<span class="soon">Скоро</span>':`<span data-qty="${p.id}">${qtyCtl(p)}</span>`}</div></div>`;}
function shelfTitle(s){if(s.title)return s.title;
  if(s.kind==='category'&&s.category_id){const c=S.categories.find(x=>x.id===s.category_id);if(c)return c.name;}
  return SHELF_TITLES[s.kind]||'Подборка';}
function shelfHtml(s){const items=(s.product_ids||[]).map(byId).filter(Boolean);
  if(!items.length)return s.kind==='usual'
    ?`<div class="sh" id="sh-${s.id}" hidden></div>`:'';
  const catJump=s.kind==='category'&&s.category_id&&S.categories.some(c=>c.id===s.category_id)
    ?`<span class="more" onclick="jump('${s.category_id}')">Все →</span>`:'';
  const head=`<div class="sh-h"><div><h2>${esc(shelfTitle(s))}</h2>${s.subtitle?`<div class="sub">${esc(s.subtitle)}</div>`:''}</div>${catJump}</div>`;
  let body;
  if(s.layout==='rows')body=rowList(items);
  else if(s.layout==='grid')body=rowGrid(items);
  else body=`<div class="rail">`+items.map(shCard).join('')+`</div>`;
  return `<div class="sh${s.layout==='hero'?' hero':''}" id="sh-${s.id}">${head}${body}</div>`;}
function feedHtml(){const parts=[];
  const bnrs=BANNERS.filter(bannerLive);
  if(bnrs.length)parts.push(`<div class="bnrs">`+bnrs.map(bannerHtml).join('')+`</div>`);
  for(const s of SHELVES)if(s.placement!=='cart'){const h=shelfHtml(s);if(h)parts.push(h);}
  return parts.join('');}
function cartUpsellHtml(){let h='';
  for(const s of SHELVES){if(s.placement!=='cart')continue;
    const items=(s.product_ids||[]).map(byId).filter(p=>p&&p.is_available!==false);
    if(!items.length)continue;
    h+=`<div class="sh"><div class="sh-h"><div><h2>${esc(shelfTitle(s))}</h2>${s.subtitle?`<div class="sub">${esc(s.subtitle)}</div>`:''}</div></div><div class="rail">`+items.map(shCard).join('')+`</div></div>`;}
  return h;}
function mountBackdrop(){const kind=(S.theme&&S.theme.backdrop)||'solid';
  if(kind==='solid')return;
  const d=document.createElement('div');d.className='bdrop';
  if(kind==='blur'&&S.cover_file_id)d.style.backgroundImage=`url("${IMG(S.cover_file_id,'lg')}")`;
  else if(kind==='blur')return;
  document.body.prepend(d);}"""
