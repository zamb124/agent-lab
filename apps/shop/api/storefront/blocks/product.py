"""Карточка товара и модификаторы: кастомизатор, группы опций, валидация.

Блок собирается реестром STOREFRONT_BLOCKS; css/js вставляются
в shell как есть — без экранирования скобок.
"""

CSS: str = """.cl{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:9px 0;font-size:15px;border-bottom:1px solid var(--line)}
.cl .n{flex:1;min-width:0}
.cl .mods{display:block;font-size:12.5px;color:var(--muted);margin-top:3px;line-height:1.45}
.cl .s{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.mg{margin:16px 0}
.mg.nest{margin:12px 0 4px 14px;padding-left:12px;border-left:2px solid var(--line)}
.mg-h{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:10px}
.mg-h b{font-size:15px}
.mg-r{font-size:12px;color:var(--warn);white-space:nowrap}
.mg-r.ok{color:var(--muted)}
.opts{display:flex;flex-wrap:wrap;gap:8px}
.opt{font:inherit;font-size:14px;padding:10px 14px;border-radius:12px;border:1px solid var(--line);background:var(--card2);color:var(--text);cursor:pointer;display:inline-flex;align-items:center;gap:8px;transition:all .12s}
.opt:hover{border-color:color-mix(in srgb,var(--text) 28%,var(--line))}
.opt.on{background:var(--accent);border-color:var(--accent);color:var(--on-accent);font-weight:600}
.opt.dis{opacity:.45;filter:saturate(.4);cursor:default}
.opt i{font-style:normal;font-size:12.5px;opacity:.85}
.opt .stepper{padding:2px}
.opt .stepper button{width:24px;height:24px;font-size:15px}
.crow{display:flex;justify-content:flex-end;margin-top:18px}"""

JS: str = """let cust=null;
function findGroup(pid,gid){const p=byId(pid);
  for(const g of p.modifier_groups||[])if(g.id===gid)return g;
  for(const k in NEST)if(NEST[k].id===gid)return NEST[k];return null;}
function applyDefaults(pid){const p=byId(pid);
  const walk=groups=>{for(const g of groups)for(const o of g.options){if(o.is_default)cust.sel.set(o.id,1);
    if(o.is_default&&o.nested_group_id&&NEST[o.nested_group_id])walk([NEST[o.nested_group_id]]);}};
  walk(p.modifier_groups||[]);}
window.customize=pid=>{cust={pid,sel:new Map(),qty:1};applyDefaults(pid);
  renderCust();sheetOpen(document.getElementById('csheet'));};
window.openProduct=pid=>customize(pid);
window.closeCust=()=>sheetBack(document.getElementById('csheet'));
const SHARE_ICON='<svg viewBox="0 -960 960 960"><path d="M720-80q-50 0-85-35t-35-85q0-7 1-14.5t3-13.5L322-392q-17 15-38 23.5t-44 8.5q-50 0-85-35t-35-85 35-85 85-35q23 0 44 8.5t38 23.5l282-164q-2-6-3-13.5t-1-14.5q0-50 35-85t85-35 85 35 35 85-35 85-85 35q-23 0-44-8.5T638-672L356-508q2 6 3 13.5t1 14.5-1 14.5-3 13.5l282 164q17-15 38-23.5t44-8.5q50 0 85 35t35 85-35 85-85 35Z"/></svg>';
let toastTimer=0;
window.toast=msg=>{const t=document.getElementById('toast');if(!t)return;
  t.textContent=msg;t.classList.add('show');
  clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('show'),2200);};
window.shareProduct=pid=>{const url=location.origin+location.pathname+'?p='+pid;
  if(navigator.share)navigator.share({url}).catch(()=>{});
  else if(navigator.clipboard)navigator.clipboard.writeText(url).then(()=>toast('Ссылка скопирована'),()=>{});
  else toast(url);};
function groupSelectedQty(g){let n=0;for(const o of g.options)n+=cust.sel.get(o.id)||0;return n;}
window.optToggle=(pid,gid,oid)=>{const g=findGroup(pid,gid);if(!g)return;
  if(g.selection_mode==='single'){for(const o of g.options)cust.sel.delete(o.id);cust.sel.set(oid,1);}
  else if(cust.sel.has(oid))cust.sel.delete(oid);
  else{const n=groupSelectedQty(g);if(g.max_selected!=null&&n>=g.max_selected)return;cust.sel.set(oid,1);}
  renderCust();};
window.optQty=(pid,gid,oid,d)=>{const g=findGroup(pid,gid);if(!g)return;
  const o=g.options.find(x=>x.id===oid);if(!o)return;
  const q=(cust.sel.get(oid)||0)+d;
  if(q<=0)cust.sel.delete(oid);
  else{if(q>o.max_per_option)return;
    if(d>0&&g.max_selected!=null&&groupSelectedQty(g)>=g.max_selected&&!cust.sel.has(oid))return;
    if(d>0&&g.max_selected!=null&&groupSelectedQty(g)>=g.max_selected&&q>(cust.sel.get(oid)||0))return;
    cust.sel.set(oid,q);}
  renderCust();};
window.custQty=d=>{cust.qty=Math.max(1,(cust.qty||1)+d);renderCust();};
function selValid(p){const check=groups=>{
    for(const g of groups){const n=groupSelectedQty(g);
      if(n<(g.min_selected||0))return false;
      if(g.selection_mode==='single'&&n>1)return false;
      if(g.max_selected!=null&&n>g.max_selected)return false;
      for(const o of g.options){const q=cust.sel.get(o.id)||0;
        if(q>(o.max_per_option||1))return false;
        if(q>0&&o.nested_group_id&&NEST[o.nested_group_id]&&!check([NEST[o.nested_group_id]]))return false;}}
    return true;};
  return check(p.modifier_groups||[]);}
function groupHtml(p,g,depth){const n=groupSelectedQty(g);const req=g.min_selected>0;
  const lim=g.max_selected!=null?`до ${g.max_selected}`:'';
  const okSel=n>=(g.min_selected||0);
  let h=`<div class="mg${depth?' nest':''}"><div class="mg-h"><b>${esc(g.name)}</b><span class="mg-r${okSel?' ok':''}">${req?(lim?`обязательно · ${lim}`:'обязательно'):lim}</span></div><div class="opts">`;
  for(const o of g.options){const q=cust.sel.get(o.id)||0;
    const pr=o.price_minor?`<i>${g.price_mode==='absolute'?fmt(o.price_minor):'+'+fmt(o.price_minor)}</i>`:'';
    const maxed=g.max_selected!=null&&n>=g.max_selected&&!q;
    if(o.max_per_option>1&&q)
      h+=`<span class="opt on"><span class="stepper"><button class="ghost" onclick="optQty('${p.id}','${g.id}','${o.id}',-1)">−</button><span>${q}</span><button onclick="optQty('${p.id}','${g.id}','${o.id}',1)">+</button></span>${esc(o.name)}${pr}</span>`;
    else
      h+=`<button class="opt${q?' on':''}${maxed?' dis':''}" onclick="optToggle('${p.id}','${g.id}','${o.id}')">${esc(o.name)}${pr}</button>`;}
  h+='</div>';
  for(const o of g.options){const q=cust.sel.get(o.id)||0;
    if(q&&o.nested_group_id&&NEST[o.nested_group_id])h+=groupHtml(p,NEST[o.nested_group_id],depth+1);}
  return h+'</div>';}
function renderCust(){if(!cust)return;const p=byId(cust.pid);if(!p)return;
  const ok=selValid(p);const u=unitPrice(p,cust.sel);
  document.getElementById('cpanel').innerHTML=
    `<button class="pshare" onclick="shareProduct('${p.id}')" aria-label="Поделиться">${SHARE_ICON}</button>`+
    `${photo(p.photo_file_id,'phero')}<h2>${esc(p.name)}${tags(p)}${portionOf(p)}</h2>`+
    `${p.description?`<p class="pdesc">${esc(p.description)}</p>`:''}`+
    (p.modifier_groups||[]).map(g=>groupHtml(p,g,0)).join('')+
    `<div class="crow"><span class="stepper"><button class="ghost" onclick="custQty(-1)">−</button><span>${cust.qty}</span><button onclick="custQty(1)">+</button></span></div>`+
    `<button class="big"${ok?'':' disabled'} onclick="addCustom()">В корзину · ${fmt(u*cust.qty)}</button>`;}
window.addCustom=()=>{if(!cust)return;const p=byId(cust.pid);
  if(!p||!selValid(p))return;
  const key=cust.pid+'#'+selHash(cust.sel);
  const l=cart.get(key)||{pid:cust.pid,sel:new Map(cust.sel),qty:0};
  l.qty+=cust.qty;cart.set(key,l);
  cust=null;closeCust();refreshQty(p.id);draw();};"""
