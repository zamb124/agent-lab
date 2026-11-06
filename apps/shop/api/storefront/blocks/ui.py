"""Общие хелперы: esc/photo/icons, цены позиций, метки, qty-контролы.

Блок собирается реестром STOREFRONT_BLOCKS; css/js вставляются
в shell как есть — без экранирования скобок.
"""

JS: str = """const CART_KEY='shopcart:'+S.slug;
const cart=new Map();
function saveCart(){try{localStorage.setItem(CART_KEY,JSON.stringify([...cart.entries()].map(([k,l])=>[k,{pid:l.pid,qty:l.qty,sel:[...l.sel.entries()]}])))}catch(e){}}
function loadCart(){try{const raw=localStorage.getItem(CART_KEY);if(!raw)return;
  for(const[k,l]of JSON.parse(raw)){if(l&&byId(l.pid))cart.set(k,{pid:l.pid,qty:l.qty||1,sel:new Map(l.sel||[])});}}catch(e){}}
const app=document.getElementById('app');
let query='';
window.menuSearch=v=>{query=v.trim().toLowerCase();renderMenu();};
const NEST=S.modifier_nested_groups||{};
const byId=id=>S.products.find(x=>x.id===id);
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function photo(u,cls){return u?`<img class="${cls||''}" src="${IMG(u)}" loading="lazy" alt="" onload="this.classList.add('ld')">`:'';}
const _IC={pin:'M480-480q33 0 56.5-23.5T560-560q0-33-23.5-56.5T480-640q-33 0-56.5 23.5T400-560q0 33 23.5 56.5T480-480Zm0 294q122-112 181-203.5T720-552q0-109-69.5-178.5T480-800q-141 0-210.5 69.5T200-552q0 71 59 162.5T480-186Z',
call:'M798-120q-125 0-247-54.5T329-329Q229-429 174.5-551T120-798q0-18 12-30t30-12h162q14 0 25 9.5t13 22.5l26 140q2 16-1 27t-11 19l-97 98q20 37 47.5 71.5T387-386q31 31 65 57.5t72 48.5l94-94q9-9 23.5-13.5T670-390l138 28q14 4 23 14.5t9 23.5v162q0 18-12 30t-30 12ZM241-600l66-66-17-94h-89q5 41 14 81t26 79Zm358 358q39 17 79.5 27t81.5 13v-88l-94-19-67 67ZM241-600Zm358 358Z',
truck:'M240-160q-50 0-85-35t-35-85H40v-440h80l96-160h384l96 160h224v440h-80q0 50-35 85t-85 35q-50 0-85-35t-35-85H360q0 50-35 85t-85 35Zm0-80q17 0 28.5-11.5T280-280q0-17-11.5-28.5T240-320q-17 0-28.5 11.5T200-280q0 17 11.5 28.5T240-240Zm480 0q17 0 28.5-11.5T760-280q0-17-11.5-28.5T720-320q-17 0-28.5 11.5T680-280q0 17 11.5 28.5T720-240ZM160-360h640v-200H160v200Z',
store:'M160-720v-80h640v80H160Zm0 560v-280h-40v-80l40-200h640l40 200v80h-40v280h-80v-280H560v280H160Zm80-80h240v-200H240v200Zm-30-280h540-540Zm0 0h540l-25-120H235l-25 120Z',
clock:'m612-292 56-56-148-148v-184h-80v216l172 172ZM480-80q-83 0-156-31.5T197-197q-54-54-85.5-127T80-480q0-83 31.5-156T197-763q54-54 127-85.5T480-880q83 0 156 31.5T763-763q54 54 85.5 127T880-480q0 83-31.5 156T763-197q-54 54-127 85.5T480-80Zm0-400Zm0 320q133 0 226.5-93.5T800-480q0-133-93.5-226.5T480-800q-133 0-226.5 93.5T160-480q0 133 93.5 226.5T480-160Z',
restaurant:'M280-600v-240q0-17 11.5-28.5T320-880q17 0 28.5 11.5T360-840v240h40v-240q0-17 11.5-28.5T440-880q17 0 28.5 11.5T480-840v240q0 56-34.5 98T360-446v326q0 17-11.5 28.5T320-80q-17 0-28.5-11.5T280-120v-326q-51-14-85.5-56T160-600v-240q0-17 11.5-28.5T200-880q17 0 28.5 11.5T240-840v240h40Zm400 200h-80q-17 0-28.5-11.5T560-440v-240q0-70 51.5-135T718-880q18 0 30 14t12 33v713q0 17-11.5 28.5T720-80q-17 0-28.5-11.5T680-120v-280Z',
person:'M480-480q-66 0-113-47t-47-113q0-66 47-113t113-47q66 0 113 47t47 113q0 66-47 113t-113 47ZM160-160v-112q0-34 17.5-62.5T224-378q62-31 126-46.5T480-440q66 0 130 15.5T736-378q29 15 46.5 43.5T800-272v112H160Zm80-80h480v-32q0-11-5.5-20T700-306q-54-27-109-40.5T480-360q-56 0-111 13.5T260-306q-9 5-14.5 14t-5.5 20v32Zm240-320q33 0 56.5-23.5T560-640q0-33-23.5-56.5T480-720q-33 0-56.5 23.5T400-640q0 33 23.5 56.5T480-560Zm0-80Zm0 400Z',
lock:'M240-80q-33 0-56.5-23.5T160-160v-400q0-33 23.5-56.5T240-640h40v-80q0-83 58.5-141.5T480-920q83 0 141.5 58.5T680-720v80h40q33 0 56.5 23.5T800-560v400q0 33-23.5 56.5T720-80H240Zm0-80h480v-400H240v400Zm240-120q33 0 56.5-23.5T560-360q0-33-23.5-56.5T480-440q-33 0-56.5 23.5T400-360q0 33 23.5 56.5T480-280ZM240-640h480v-80q0-50-35-85t-85-35q-50 0-85 35t-35 85v80H240Z',
cart:'M280-80q-33 0-56.5-23.5T200-160q0-33 23.5-56.5T280-240q33 0 56.5 23.5T360-160q0 33-23.5 56.5T280-80Zm400 0q-33 0-56.5-23.5T600-160q0-33 23.5-56.5T680-240q33 0 56.5 23.5T760-160q0 33-23.5 56.5T680-80ZM208-800h590q23 0 35 20.5t1 41.5L692-482q-11 20-29.5 31T622-440H324l-44 80h480v80H280q-45 0-68-39.5t-2-78.5l54-98-144-304H40v-80h130l38 80Z'};
const ic=n=>`<svg viewBox="0 -960 960 960"><path d="${_IC[n]}"/></svg>`;
function selHash(sel){return [...sel.entries()].sort().map(([o,q])=>o+'x'+q).join(',');}
function cartQty(pid){let n=0;for(const l of cart.values())if(l.pid===pid)n+=l.qty;return n;}
function unitPrice(p,sel){let abs=0,delta=0;
  const walk=groups=>{for(const g of groups)for(const o of g.options){const q=sel.get(o.id)||0;
    if(!q)continue;
    if(g.price_mode==='absolute')abs+=o.price_minor*q;else delta+=o.price_minor*q;
    if(o.nested_group_id&&NEST[o.nested_group_id])walk([NEST[o.nested_group_id]]);}};
  walk(p.modifier_groups||[]);
  return (abs||p.price_minor)+delta;}
function modsText(p,sel){const names=[];
  const walk=groups=>{for(const g of groups)for(const o of g.options){const q=sel.get(o.id)||0;
    if(!q)continue;names.push(q>1?o.name+' ×'+q:o.name);
    if(o.nested_group_id&&NEST[o.nested_group_id])walk([NEST[o.nested_group_id]]);}};
  walk(p.modifier_groups||[]);return names.join(', ');}
function priceLabel(p){return (p.modifier_groups&&p.modifier_groups.length)?'от '+fmt(p.price_from_minor!=null?p.price_from_minor:p.price_minor):fmt(p.price_minor);}
function promoApplies(a,pid){if(!a)return false;
  const ids=a.product_ids;if(Array.isArray(ids)&&ids.length)return ids.includes(pid);
  if(a.type==='fixed_bundle_price'&&Array.isArray(a.items))return a.items.some(i=>i.product_id===pid);
  return a.type==='n_plus_m_free'||a.type==='percent_items';}
function portionOf(p){return p.portion?`<span class="portion">${esc(p.portion)}</span>`:'';}
const DEFS=S.badge_defs||{};
function tags(p){return (p.badges||[]).map(b=>{const d=DEFS[b];
  return d?`<span class="ptag">${d.icon_path?`<svg viewBox="0 -960 960 960"><path d="${d.icon_path}"/></svg>`:''}${esc(d.label)}</span>`:'';}).join('');}
function badge(pid){const pr=(S.promos||[]).find(x=>promoApplies(x.action,pid));
  return pr?`<span class="pbadge">${esc(pr.name)}</span>`:'';}
function qtyCtl(p){const hasMod=p.modifier_groups&&p.modifier_groups.length;
  const q=cartQty(p.id);
  if(hasMod)return `<button class="add" onclick="customize('${p.id}')">${q?'Выбрать · '+q:'Выбрать'}</button>`;
  const l=cart.get(p.id+'#');const n=l?l.qty:0;
  if(!n)return `<button class="add" onclick="addPlain('${p.id}',1)">В корзину</button>`;
  return `<span class="stepper"><button class="ghost" onclick="addPlain('${p.id}',-1)">−</button><span>${n}</span><button onclick="addPlain('${p.id}',1)">+</button></span>`;}
function refreshQty(pid){document.querySelectorAll(`[data-qty="${pid}"]`).forEach(el=>{el.innerHTML=qtyCtl(byId(pid));});}
const STOP=`onclick="event.stopPropagation()"`;"""
