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
.rail{display:flex;gap:12px;overflow-x:auto;padding:6px 2px 4px;scrollbar-width:none;scroll-snap-type:x proximity}
.rail::-webkit-scrollbar{display:none}
/* Карточка ограничена рамкой: цена и кнопка внутри — соседние элементы
   разных карточек больше не сливаются по близости. */
.shcard{flex:0 0 auto;width:152px;scroll-snap-align:start;cursor:pointer;
  background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  padding:8px;box-shadow:var(--shadow-sm)}
.shcard .ph{position:relative;width:100%;aspect-ratio:1/1;border-radius:calc(var(--radius) - 8px);overflow:hidden;background:var(--card2)}
.shcard .ph img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.shcard h3{font-size:14px;font-weight:600;margin-top:9px;line-height:1.32;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:2.64em}
.shcard .row{display:flex;justify-content:space-between;align-items:center;margin-top:7px;gap:8px}
.shcard .row [data-qty]{flex:1;display:flex}
.shcard .row .add{flex:1;justify-content:space-between}
.shcard .price{font-size:14.5px}
.shcard .add{padding:7px 12px;font-size:13px;gap:6px}
.shcard .add i{font-size:15px}
/* CTA-плитка в конце рельса — вместо ссылки «Все →», которая в вебе
   отваливалась к краю экрана и терялась. */
.railcta{flex:0 0 auto;width:110px;scroll-snap-align:start;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:10px;border:1px solid var(--line);
  border-radius:var(--radius);background:var(--card);color:var(--afg);
  font:600 14px/1.3 inherit;cursor:pointer}
.railcta i{font-style:normal;width:34px;height:34px;border-radius:50%;background:var(--accent);
  color:var(--on-accent);display:grid;place-items:center;font-size:17px;font-weight:800}
.railcta:hover{border-color:color-mix(in srgb,var(--accent) 45%,var(--line))}
.cta-all{margin-top:10px;font:600 14px/1 inherit;padding:12px 20px;border-radius:99px;
  border:1px solid var(--line);background:var(--card);color:var(--afg);cursor:pointer}
.cta-all:hover{border-color:color-mix(in srgb,var(--accent) 45%,var(--line))}
/* Полка hero — рельс широких карточек: без accent-панели (пустое цветное
   пятно читалось как чужеродный блок). Селектор по data-layout: класс
   «hero» занят страничной шапкой. */
.sh[data-layout=hero] .shcard{width:min(300px,78vw);padding:0;overflow:hidden}
.sh[data-layout=hero] .shcard .ph{aspect-ratio:16/10;border-radius:0}
.sh[data-layout=hero] .shcard h3{font-size:15.5px;padding:0 12px;margin-top:11px}
.sh[data-layout=hero] .shcard .row{padding:0 12px 12px}
.soon{display:inline-block;font-size:12px;font-weight:650;color:var(--warn);background:color-mix(in srgb,var(--warn) 14%,transparent);padding:6px 12px;border-radius:99px;white-space:nowrap}
.na img{filter:saturate(.35) brightness(.82)}
.na h3,.na p{opacity:.55}
.fav{position:absolute;top:9px;right:9px;width:36px;height:36px;border-radius:50%;border:0;display:grid;place-items:center;background:rgba(16,15,18,.5);backdrop-filter:blur(10px);color:rgba(255,255,255,.92);cursor:pointer;transition:transform .12s ease,color .15s ease,background .15s;z-index:2}
.fav svg{width:19px;height:19px;fill:currentColor}
.fav:hover{background:rgba(16,15,18,.68)}
.fav:active{transform:scale(.82)}
.fav.on{color:var(--accent)}
.gcard{position:relative}
.gcard .fav{top:10px;right:10px}
.bdrop{position:fixed;inset:0;z-index:-1;pointer-events:none}
body[data-backdrop=blur] .bdrop{background-size:cover;background-position:center 18%;filter:blur(64px) saturate(1.2);opacity:.5}
body[data-backdrop=blur] .bdrop::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,color-mix(in srgb,var(--bg) 34%,transparent) 0%,var(--bg) 72%)}
body[data-backdrop=blur] .sh-h h2,body[data-backdrop=blur] .sh-h .sub,body[data-backdrop=blur] .shcard h3,body[data-backdrop=blur] .shcard .price,body[data-backdrop=blur] .cat.sub,body[data-backdrop=blur] .item h3,body[data-backdrop=blur] .item p,body[data-backdrop=blur] .item .price,body[data-backdrop=blur] .portion{text-shadow:0 1px 12px color-mix(in srgb,var(--bg) 72%,transparent),0 0 4px color-mix(in srgb,var(--bg) 55%,transparent)}
body[data-backdrop=blur] .sh-h .sub,body[data-backdrop=blur] .cat.sub,body[data-backdrop=blur] .item p,body[data-backdrop=blur] .portion{color:color-mix(in srgb,var(--text) 88%,transparent)}"""

JS: str = """const SHELVES=Array.isArray(S.shelves)?S.shelves:[];
const BANNERS=Array.isArray(S.banners)?S.banners:[];
const SUBS=new Set();
const FAVS=new Set();
const FAV_ON=!!(S.features&&S.features.favorites);
const PERSONAL_SHELVES=new Set(['usual','favorites']);
const SHELF_TITLES={new:'Новинки',hits:'Популярное',comeback:'Скоро вернётся',usual:'Как всегда',favorites:'Избранное',upsell:'Добавить к заказу'};
function favBtn(p){return FAV_ON?`<button class="fav${FAVS.has(p.id)?' on':''}" data-fav="${p.id}" onclick="event.stopPropagation();toggleFav('${p.id}')" aria-label="В избранное">${ic('heart')}</button>`:'';}
window.toggleFav=async pid=>{
  const customer=await ensureAuth();if(!customer)return;
  const on=!FAVS.has(pid);
  const r=await fetch(`/shop/api/v1/public/storefront/${S.slug}/favorites`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_id:pid,favorite:on})});
  if(!r.ok)return;
  const d=await r.json();
  if(d.favorite)FAVS.add(pid);else FAVS.delete(pid);
  document.querySelectorAll(`[data-fav="${pid}"]`).forEach(el=>el.classList.toggle('on',d.favorite));
  const favShelf=SHELVES.find(s=>s.kind==='favorites');
  if(favShelf){favShelf.product_ids=[...FAVS];
    const h=document.getElementById('sh-'+favShelf.id);if(h)h.outerHTML=shelfHtml(favShelf);}
  toast(d.favorite?'В избранном':'Убрано из избранного');};
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
  return `<div class="shcard${na?' na':''}" data-pid="${esc(p.id)}" onclick="openProduct('${p.id}')"><div class="ph">${photo(p.photo_file_id,'','md!sq')}${favBtn(p)}</div><h3>${esc(p.name)}</h3><div class="row" ${STOP}>${priceCell(p)}${na?'<span class="soon">Скоро</span>':`<span data-qty="${p.id}">${qtyCtl(p)}</span>`}</div></div>`;}
function shelfTitle(s){if(s.title)return s.title;
  if(s.kind==='category'&&s.category_id){const c=S.categories.find(x=>x.id===s.category_id);if(c)return c.name;}
  return SHELF_TITLES[s.kind]||'Подборка';}
function shelfHtml(s){const items=(s.product_ids||[]).map(byId).filter(Boolean);
  if(!items.length)return PERSONAL_SHELVES.has(s.kind)
    ?`<div class="sh" id="sh-${s.id}" hidden></div>`:'';
  /* CTA «все товары» — плитка в конце рельса (rail/hero) или кнопка под
     сеткой (rows/grid); ссылки у края заголовка больше нет. */
  const catId=s.kind==='category'&&s.category_id&&S.categories.some(c=>c.id===s.category_id)
    ?s.category_id:'';
  const head=`<div class="sh-h"><div><h2>${esc(shelfTitle(s))}</h2>${s.subtitle?`<div class="sub">${esc(s.subtitle)}</div>`:''}</div></div>`;
  const ctaBtn=catId?`<button class="cta-all" onclick="jump('${catId}')">Все товары категории →</button>`:'';
  const ctaTile=catId?`<div class="railcta" onclick="jump('${catId}')"><i>→</i><span>Все товары</span></div>`:'';
  let body;
  if(s.layout==='rows')body=rowList(items)+ctaBtn;
  else if(s.layout==='grid')body=rowGrid(items)+ctaBtn;
  else body=`<div class="rail">`+items.map(shCard).join('')+ctaTile+`</div>`;
  return `<div class="sh" data-layout="${s.layout||'rail'}" id="sh-${s.id}">${head}${body}</div>`;}
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
  if(kind!=='blur'||!S.cover_file_id)return;
  const d=document.createElement('div');d.className='bdrop';
  d.style.backgroundImage=`url("${IMG(S.cover_file_id,'lg')}")`;
  document.body.prepend(d);}"""
