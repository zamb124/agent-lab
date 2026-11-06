"""Каталог: пресеты строк/сетки/compact, рендер меню, скролл-спай категорий.

Блок собирается реестром STOREFRONT_BLOCKS; css/js вставляются
в shell как есть — без экранирования скобок.
"""

CSS: str = """.tabs{position:sticky;top:env(safe-area-inset-top);z-index:5;display:flex;gap:8px;overflow-x:auto;padding:12px 2px;background:linear-gradient(180deg,var(--bg) 85%,transparent);scrollbar-width:none}
.msearch{display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--line);border-radius:99px;padding:10px 18px;margin:10px 0 2px;transition:border-color .15s,box-shadow .15s}
.msearch:focus-within{border-color:var(--afg);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 22%,transparent)}
.msearch svg{opacity:.5;flex-shrink:0}
.msearch input{flex:1;min-width:0;font:inherit;font-size:15px;background:transparent;border:0;color:var(--text);outline:none}
.msearch input::placeholder{color:var(--muted)}
.tabs::-webkit-scrollbar{display:none}
.tabs button{font:inherit;font-size:14.5px;padding:9px 16px;border-radius:99px;border:1px solid var(--line);color:var(--muted);background:var(--card);cursor:pointer;white-space:nowrap;transition:all .15s}
.tabs button:hover{color:var(--text);border-color:color-mix(in srgb,var(--text) 25%,var(--line))}
.tabs button.on{background:var(--accent);border-color:var(--accent);color:var(--on-accent);font-weight:600}
.cat{font-size:21px;margin:28px 0 6px;letter-spacing:-.01em}
.cat.sub{font-size:17px;margin:18px 0 4px;color:var(--muted);font-weight:600}
.mchunk{animation:fade .3s ease}
.msk{height:96px;border-radius:var(--radius);margin:14px 0;background:linear-gradient(100deg,var(--card2) 40%,var(--card) 50%,var(--card2) 60%);background-size:200% 100%;animation:shimmer 1.4s infinite linear}
@keyframes shimmer{from{background-position:120% 0}to{background-position:-80% 0}}
.cart.pop{animation:pop .28s ease}
@keyframes pop{0%{transform:translateX(-50%) scale(1)}40%{transform:translateX(-50%) scale(1.06)}100%{transform:translateX(-50%) scale(1)}}
.item,.gcard{cursor:pointer}
.phero{width:100%;aspect-ratio:16/10;object-fit:cover;border-radius:var(--radius);margin-bottom:12px}
.pdesc{color:var(--muted);font-size:14px;line-height:1.55;margin:4px 0 14px}
.item{display:flex;gap:14px;padding:16px 2px;border-bottom:1px solid var(--line);animation:fade .3s ease}
.flash{animation:flashRing 2.6s ease}
@keyframes flashRing{0%,55%{box-shadow:0 0 0 3px var(--accent);border-radius:14px}100%{box-shadow:0 0 0 0 transparent}}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1}}
.item img{width:92px;height:92px;border-radius:var(--radius);object-fit:cover;background:var(--card2);flex-shrink:0}
.item .b{flex:1;min-width:0}
.item h3{font-size:16.5px;font-weight:600;letter-spacing:-.005em}
.portion{font-size:13px;font-weight:500;color:var(--muted);margin-left:6px;white-space:nowrap}
.item p{font-size:13.5px;color:var(--muted);margin-top:4px;line-height:1.55;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.item .row{display:flex;justify-content:space-between;align-items:center;margin-top:10px;gap:10px}
.price{font-size:16.5px;font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap}
.add{font:inherit;font-size:14px;font-weight:600;padding:9px 18px;border-radius:99px;border:0;background:var(--accent);color:var(--on-accent);cursor:pointer;transition:transform .1s,box-shadow .15s}
.add:hover{box-shadow:0 2px 12px color-mix(in srgb,var(--accent) 45%,transparent)}
.add:active{transform:scale(.94)}
.stepper{display:inline-flex;align-items:center;gap:2px;background:var(--card2);border-radius:99px;padding:3px}
.stepper button{width:32px;height:32px;border-radius:99px;border:0;background:var(--accent);color:var(--on-accent);font-size:18px;font-weight:700;cursor:pointer;line-height:1}
.stepper button.ghost{background:transparent;color:var(--afg)}
.stepper span{min-width:26px;text-align:center;font-weight:650;font-variant-numeric:tabular-nums}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding-top:10px}
.gcard{background:var(--card);border-radius:var(--radius);overflow:hidden;border:1px solid var(--line);display:flex;flex-direction:column;box-shadow:var(--shadow-sm)}
.gcard img{width:100%;aspect-ratio:4/3;object-fit:cover;background:var(--card2)}
.gcard .b{padding:12px;display:flex;flex-direction:column;gap:8px;flex:1}
.gcard h3{font-size:15px;font-weight:600;letter-spacing:-.005em}
.gcard p{font-size:12.5px;color:var(--muted);line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.gcard .row{display:flex;justify-content:space-between;align-items:center;margin-top:auto;gap:8px}
.compact .item{padding:12px 2px}
.compact .item img{display:none}"""

JS: str = """function rowList(ps){return ps.map(p=>`<div class="item" data-pid="${esc(p.id)}" onclick="openProduct('${p.id}')">${photo(p.photo_file_id)}<div class="b"><h3>${esc(p.name)}${badge(p.id)}${tags(p)}${portionOf(p)}</h3>${p.description?`<p>${esc(p.description)}</p>`:''}<div class="row" ${STOP}><span class="price">${priceLabel(p)}</span><span data-qty="${p.id}">${qtyCtl(p)}</span></div></div></div>`).join('');}
function rowGrid(ps){return `<div class="grid">`+ps.map(p=>`<div class="gcard" data-pid="${esc(p.id)}" onclick="openProduct('${p.id}')">${photo(p.photo_file_id)}<div class="b"><h3>${esc(p.name)}${badge(p.id)}${tags(p)}${portionOf(p)}</h3>${p.description?`<p>${esc(p.description)}</p>`:''}<div class="row" ${STOP}><span class="price">${priceLabel(p)}</span><span data-qty="${p.id}">${qtyCtl(p)}</span></div></div></div>`).join('')+`</div>`;}
function rowCompact(ps){return ps.map(p=>`<div class="item" data-pid="${esc(p.id)}" onclick="openProduct('${p.id}')"><div class="b"><h3>${esc(p.name)}${badge(p.id)}${tags(p)}${portionOf(p)}</h3>${p.description?`<p>${esc(p.description)}</p>`:''}</div><span class="price">${priceLabel(p)}</span><span data-qty="${p.id}" ${STOP}>${qtyCtl(p)}</span></div>`).join('');}
const ITEMS=PRESET==='grid'?rowGrid:(PRESET==='compact'?rowCompact:rowList);
function render(){
  const hb=hoursBadge();
  let h=`<div class="hero">${photo(S.cover_file_id,'bg')}<div class="veil"></div><div class="head">${photo(S.logo_file_id,'logo')}<div><h1 class="serif">${esc(S.name)}</h1>${S.description?`<div class="desc">${esc(S.description)}</div>`:''}</div></div></div>
  <div class="meta">${hb?`<span class="${hb.open?'ob-open':'ob-closed'}">${ic('clock')}${hb.t}</span>`:''}${S.city||S.address?`<span>${ic('pin')}${esc([S.city,S.address].filter(Boolean).join(', '))}</span>`:''}${S.phone?`<span>${ic('call')}${esc(S.phone)}</span>`:''}${S.delivery_enabled?`<span>${ic('truck')}Доставка</span>`:''}${S.pickup_enabled?`<span>${ic('store')}Самовывоз</span>`:''}${S.onsite_enabled?`<span>${ic('restaurant')}В заведении</span>`:''}</div>`;
  if(!S.products.length){app.innerHTML=h+`<div class="empty">Меню скоро появится</div>`;return;}
  h+=`<div id="msw"></div><div id="menu"></div>`;
  app.innerHTML=h;
  if(S.products.length>=6){document.getElementById('msw').innerHTML=`<div class="msearch"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input type="search" placeholder="Поиск по меню" autocomplete="off" oninput="menuSearch(this.value)"></div>`;}
  renderMenu();
}
let queue=[],spyIO=null,moreIO=null;
function spy(root){if(!spyIO)return;
  root.querySelectorAll('.cat[id]:not([data-spy])').forEach(h=>{h.dataset.spy='1';spyIO.observe(h);});}
function activate(id){document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('on',b.dataset.cat===id));
  const t=document.querySelector(`.tabs button[data-cat="${CSS.escape(id)}"]`);
  t?.scrollIntoView({inline:'center',block:'nearest'});}
function chunkHtml(b){const t=b.depth?3:2;
  return `<div class="mchunk">${b.name?`<h${t} class="cat serif${b.depth?' sub':''}"${b.id?` id="${b.id}" data-root="${b.root}"`:""}${b.depth?` style="margin-left:${Math.min(b.depth,4)*16}px"`:''}>${esc(b.name)}</h${t}>`:''}${ITEMS(b.items)}</div>`;}
function renderMenu(){
  const menu=document.getElementById('menu');if(!menu)return;
  spyIO?.disconnect();moreIO?.disconnect();queue=[];
  const other=S.products.filter(p=>!p.category_id);
  if(query){
    app.classList.add('flat');
    const hits=S.products.filter(p=>p.name.toLowerCase().includes(query)||(p.description||'').toLowerCase().includes(query));
    menu.innerHTML=hits.length?ITEMS(hits):`<div class="empty">По запросу «${esc(query)}» ничего не нашлось</div>`;
    return;
  }
  // Прогрессивный рендер: табы сразу, тело дорисовывается чанками по мере скролла —
  // все данные уже в снапшоте, поэтому подгрузка мгновенная и бесшовная.
  // Дерево категорий: секции в depth-first порядке; категория видна, когда в её
  // поддереве есть товары; узел с родителем вне снапшота считается корнем.
  const CH=12,blocks=[],byId={};
  for(const c of S.categories)byId[c.id]=c;
  const prods=cid=>S.products.filter(p=>p.category_id===cid);
  const kids=p=>S.categories.filter(c=>((c.parent_id&&byId[c.parent_id])?c.parent_id:null)===p).sort((a,b)=>a.sort-b.sort);
  const subHas=c=>prods(c.id).length>0||kids(c.id).some(subHas);
  const roots=kids(null).filter(subHas);
  app.classList.toggle('flat',roots.length+(other.length?1:0)<=1);
  const push=(id,name,depth,root,items)=>{
    if(!items.length){blocks.push({id:'c-'+id,name,depth,root,items:[]});return;}
    for(let i=0;i<items.length;i+=CH)
      blocks.push({id:i===0?'c-'+id:'',name:i===0?name:'',depth,root,items:items.slice(i,i+CH)});};
  for(const r of roots){const walk=(c,depth)=>{push(c.id,c.name,depth,r.id,prods(c.id));
    for(const k of kids(c.id))if(subHas(k))walk(k,depth+1);};walk(r,0);}
  if(other.length)push('other','Ещё',0,'other',other);
  menu.innerHTML=`<div class="tabs">${roots.map(c=>`<button data-cat="${c.id}" onclick="jump('${c.id}')">${esc(c.name)}</button>`).join('')}${other.length?`<button data-cat="other" onclick="jump('other')">Ещё</button>`:''}</div><div id="mbody"></div><div id="msent"><div class="msk"></div><div class="msk"></div></div>`;
  const body=menu.querySelector('#mbody'),sent=menu.querySelector('#msent');
  queue=blocks;
  const flush=()=>{const b=queue.shift();
    if(!b){sent.remove();moreIO?.disconnect();return;}
    body.insertAdjacentHTML('beforeend',chunkHtml(b));
    spy(body);};
  const first=roots[0]?.id||(other.length?'other':'');
  if(first)activate(first);
  for(let i=0;i<3&&queue.length;i++)flush();
  spyIO=new IntersectionObserver(es=>{for(const e of es)if(e.isIntersecting)activate(e.target.dataset.root);},{rootMargin:'-30% 0px -60% 0px'});
  spy(body);
  moreIO=new IntersectionObserver(es=>{if(es[0].isIntersecting)for(let i=0;i<2&&queue.length;i++)flush();},{rootMargin:'1000px 0px'});
  if(queue.length)moreIO.observe(sent);else sent.remove();
}
window.jump=id=>{
  let el=document.getElementById('c-'+id);
  const m=document.getElementById('mbody'),sent=document.getElementById('msent');
  while(!el&&queue.length&&m&&sent){
    const b=queue.shift();
    m.insertAdjacentHTML('beforeend',chunkHtml(b));
    spy(m);
    if(!queue.length)sent.remove();
    el=document.getElementById('c-'+id);
  }
  el?.scrollIntoView({behavior:'smooth',block:'start'});};"""
