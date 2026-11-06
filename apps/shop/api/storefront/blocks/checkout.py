"""Оформление: тип выдачи, адрес и зона, подсказки, авторизация, отправка.

Блок собирается реестром STOREFRONT_BLOCKS; css/js вставляются
в shell как есть — без экранирования скобок.
"""

CSS: str = """.seg{display:flex;background:var(--card2);border-radius:14px;padding:4px;margin:14px 0}
.seg button{flex:1;font:inherit;font-size:14.5px;font-weight:600;padding:11px;border:0;border-radius:11px;background:transparent;color:var(--muted);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:8px}
.seg button svg{width:17px;height:17px;fill:currentColor;flex-shrink:0}
.seg button.on{background:var(--accent);color:var(--on-accent);box-shadow:var(--shadow-sm)}
input.f,select.f{width:100%;font:inherit;font-size:15px;padding:14px;margin:6px 0;border-radius:14px;border:1px solid var(--line);background:var(--card2);color:var(--text);transition:border-color .15s,box-shadow .15s}
input.f:focus,select.f:focus{outline:none;border-color:var(--afg);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 22%,transparent)}
input.f::placeholder{color:var(--muted)}
button.big{width:100%;font:inherit;font-size:16px;font-weight:650;padding:16px;border-radius:16px;border:0;background:var(--accent);color:var(--on-accent);cursor:pointer;margin-top:14px;letter-spacing:.01em;transition:transform .1s,box-shadow .15s}
button.big:hover:not(:disabled){box-shadow:0 6px 20px color-mix(in srgb,var(--accent) 42%,transparent)}
button.big:disabled{opacity:.45;cursor:default}
.minwarn{font-size:13px;color:var(--warn);margin-top:10px;text-align:center}
.achips{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 2px}
.achip{font:inherit;font-size:13px;font-weight:600;padding:8px 12px;border-radius:999px;border:1.5px solid var(--line);background:var(--card2);color:var(--text);cursor:pointer;transition:border-color .15s,background .15s}
.achip.on{border-color:var(--accent);background:var(--accent);color:var(--on-accent)}
.zstat{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:600;margin-top:8px;min-height:18px}
.zstat.ok{color:#1f9d55}
.zstat.bad{color:#d24545}
.zstat.wait{color:var(--muted)}
.sug{display:none;margin-top:6px;border:1px solid var(--line);border-radius:12px;background:var(--card);overflow:hidden;box-shadow:0 8px 24px color-mix(in srgb,var(--afg) 14%,transparent)}
.sug.open{display:block}
.sugrow{padding:11px 14px;font-size:14px;font-weight:550;color:var(--text);cursor:pointer;border-bottom:1px solid var(--line);line-height:1.35}
.sugrow:last-child{border-bottom:0}
.sugrow:hover,.sugrow.on{background:color-mix(in srgb,var(--accent) 10%,transparent)}
.sugrow small{display:block;font-size:11.5px;color:var(--muted);font-weight:500}"""

JS: str = """let dtype='';
let tableId=TABLE_ID&&TABLES.some(t=>t.id===TABLE_ID)?TABLE_ID:'';
const DTYPES=[['delivery','truck','Доставка',S.delivery_enabled],['pickup','store','Самовывоз',S.pickup_enabled],['onsite','restaurant','В заведении',S.onsite_enabled&&TABLES.length>0]].filter(d=>d[3]);
window.openSheet=()=>{
  if(!dtype)dtype=(tableId&&S.onsite_enabled)?'onsite':(DTYPES[0]?DTYPES[0][0]:'');
  renderSheet();
  sheetOpen(document.getElementById('sheet'));
};
window.setDtype=t=>{dtype=t;renderSheet();};
window.setTable=t=>{tableId=t;};
function renderSheet(){
  const p=document.getElementById('panel');
  const sub=total();
  const fee=dtype==='delivery'?(S.delivery_fee_minor||0):0;
  const below=S.min_order_minor&&sub<S.min_order_minor;
  const hb=hoursBadge();
  const seg=DTYPES.length>1?`<div class="seg">${DTYPES.map(d=>`<button class="${dtype===d[0]?'on':''}" onclick="setDtype('${d[0]}')">${ic(d[1])}${d[2]}</button>`).join('')}</div>`:'';
  p.innerHTML=`<h2>Ваш заказ</h2>`+[...cart.entries()].map(([key,l])=>{const x=byId(l.pid);if(!x)return'';
    const mods=modsText(x,l.sel);const u=unitPrice(x,l.sel);
    return `<div class="cl">${photo(x.photo_file_id,'climg','sm!sq')}<span class="n">${esc(x.name)}${mods?`<span class="mods">${esc(mods)}</span>`:''}</span><span class="stepper"><button class="ghost" onclick="addLine('${key}',-1);renderSheet()">−</button><span>${l.qty}</span><button onclick="addLine('${key}',1);renderSheet()">+</button></span><b class="s">${fmt(u*l.qty)}</b></div>`;}).join('')+
  seg+
  `<div id="savings"></div>`+
  (dtype==='delivery'?`<div class="cl"><span>Доставка</span><b class="s" id="feeVal">${fmt(fee)}</b></div>`:'')+
  `<div class="cl" style="border-bottom:0"><b>Итого</b><b class="s" id="cartTotal" style="font-size:18px">${fmt(sub+fee)}</b></div>
  <input class="f" id="cn" placeholder="Ваше имя">
  ${dtype==='onsite'?`<select class="f" id="ct" onchange="setTable(this.value)"><option value="">Выберите стол</option>${TABLES.map(t=>`<option value="${t.id}"${t.id===tableId?' selected':''}>${esc(t.label)}</option>`).join('')}</select>`:''}
  ${dtype==='delivery'?`<div class="achips" id="addrChips"></div><input class="f" id="ca" placeholder="Адрес доставки" autocomplete="street-address" oninput="onAddrInput()"><div class="sug" id="caSug"></div><div class="zstat" id="zoneStat"></div>`:''}<input class="f" id="cc" placeholder="Комментарий к заказу">
  ${below?`<div class="minwarn">Минимальный заказ — ${fmt(S.min_order_minor)}</div>`:''}
  ${hb&&!hb.open?`<div class="minwarn">Сейчас закрыто — ${hb.t}</div>`:''}
  <button class="big" id="payBtn" ${(below||(hb&&!hb.open))?'disabled':''} onclick="submit()">Оформить заказ · ${fmt(sub+fee)}</button>`;
  refreshSavings();
  if(dtype==='delivery'){loadAddresses();updatePayBtn();}
};
let priceReq=0;
async function refreshSavings(){
  const my=++priceReq;
  try{
    const body={items:[...cart.values()].map(l=>({product_id:l.pid,qty:l.qty,
      selections:[...l.sel.entries()].map(([option_id,qty])=>({option_id,qty}))})),
      delivery_type:dtype};
    const r=await fetch(`/shop/api/v1/public/storefront/${S.slug}/cart/price`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(my!==priceReq||!r.ok)return;
    const d=await r.json();
    const el=document.getElementById('savings');
    if(el)el.innerHTML=d.discount_minor>0
      ?`<div class="cl save"><span>Выгода${d.applied_promos.length?' · '+esc(d.applied_promos.map(a=>a.name).join(', ')):''}</span><b class="s">−${fmt(d.discount_minor)}</b></div>`:'';
    const fv=document.getElementById('feeVal');
    if(fv&&dtype==='delivery')fv.textContent=fmt(d.delivery_fee_minor);
    const tot=document.getElementById('cartTotal');
    if(tot)tot.textContent=fmt(d.total_minor);
    const btn=document.getElementById('payBtn');
    if(btn&&!btn.disabled)btn.textContent='Оформить заказ · '+fmt(d.total_minor);
  }catch(e){}
}
// ——— Адреса покупателя и зона доставки ———
let savedAddrs=[];        // список сохранённых адресов из customer-auth API
let pickedAddrId='';      // выбранный чип (customer_address_id) или '' — ручной ввод
let zoneOk=null;          // null — зона не проверялась / не требуется; true/false — результат
const zoneRequired=()=>!!(S.delivery_zone&&S.delivery_zone.coordinates&&S.delivery_zone.coordinates.length);
async function loadAddresses(){
  try{
    const r=await fetch('/shop/api/v1/public/customer-auth/addresses',{credentials:'same-origin'});
    if(!r.ok)return;
    const d=await r.json();
    savedAddrs=d.addresses||[];
    renderAddrChips();
  }catch(e){}
}
function renderAddrChips(){
  const el=document.getElementById('addrChips');
  if(!el)return;
  el.innerHTML=savedAddrs.map(a=>
    `<button type="button" class="achip ${pickedAddrId===a.customer_address_id?'on':''}"
      onclick="pickAddr('${a.customer_address_id}')">${esc(a.label||a.address)}</button>`
  ).join('');
}
window.pickAddr=id=>{
  pickedAddrId=pickedAddrId===id?'':id;
  const a=savedAddrs.find(x=>x.customer_address_id===pickedAddrId);
  const inp=document.getElementById('ca');
  if(inp)inp.value=a?a.address:'';
  renderAddrChips();
  // сохранённый адрес уже геокодирован на сервере — зону не дёргаем,
  // но если зона настроена и координат нет — всё равно проверим по тексту.
  if(zoneRequired()){zoneOk=null;clearTimeout(zTimer);zTimer=setTimeout(zoneCheck,150);}
  else{zoneOk=null;updatePayBtn();}
};
let zTimer=0,zReq=0,sugTimer=0,sugReq=0;
function hideSug(){const el=document.getElementById('caSug');if(el)el.classList.remove('open');}
window.pickSug=(i)=>{
  const el=document.getElementById('caSug');
  const row=el?.querySelector(`[data-i="${i}"]`);
  const inp=document.getElementById('ca');
  if(inp&&row)inp.value=row.dataset.name||'';
  hideSug();
  if(pickedAddrId){pickedAddrId='';renderAddrChips();}
  zoneOk=null;clearTimeout(zTimer);zoneCheck();
};
async function addrSuggest(){
  const inp=document.getElementById('ca');
  const el=document.getElementById('caSug');
  const q=(inp?.value||'').trim();
  if(!el)return;
  if(q.length<3){hideSug();return;}
  const my=++sugReq;
  try{
    const r=await fetch(`/shop/api/v1/public/storefront/${S.slug}/address-suggest?q=${encodeURIComponent(q)}`);
    if(my!==sugReq)return;
    const d=await r.json();
    const items=Array.isArray(d.items)?d.items:[];
    if(!items.length){hideSug();return;}
    el.innerHTML=items.map((a,i)=>`<div class="sugrow" data-i="${i}" data-name="${esc(a.display_name||'')}" onclick="pickSug(${i})">${esc(a.display_name||'')}<small>${esc(a.city||'')}</small></div>`).join('');
    el.classList.add('open');
  }catch(e){hideSug();}
}
window.onAddrInput=()=>{
  if(pickedAddrId){pickedAddrId='';renderAddrChips();}
  clearTimeout(zTimer);
  clearTimeout(sugTimer);
  const st=document.getElementById('zoneStat');
  if(st){st.className='zstat';st.textContent='';}
  zoneOk=null;
  zTimer=setTimeout(zoneCheck,600);
  sugTimer=setTimeout(addrSuggest,250);
};
async function zoneCheck(){
  const inp=document.getElementById('ca');
  const q=(inp?.value||'').trim();
  const st=document.getElementById('zoneStat');
  if(q.length<5){zoneOk=null;updatePayBtn();return;}
  const my=++zReq;
  if(st){st.className='zstat wait';st.textContent='Проверяем зону доставки…';}
  try{
    const r=await fetch(`/shop/api/v1/public/storefront/${S.slug}/delivery-check?address=${encodeURIComponent(q)}`);
    if(my!==zReq)return;
    const d=await r.json();
    zoneOk=d.ok===true?true:(d.ok===false?false:null);
    if(st){
      if(zoneOk===true){st.className='zstat ok';
        const eta=d.eta_minutes?` ~${d.eta_minutes} мин`:'';
        st.textContent='Доставим'+eta+(d.inside_zone===false?'':' ✓ '+((d.normalized||'').split(',')[0]));}
      else if(zoneOk===false){st.className='zstat bad';st.textContent=d.reason==='out_of_delivery_zone'?'Адрес вне зоны доставки':'Адрес не удалось проверить';}
      else{st.className='zstat';st.textContent='';}
    }
    updatePayBtn();
  }catch(e){zoneOk=null;updatePayBtn();}
}
function updatePayBtn(){
  const btn=document.getElementById('payBtn');
  if(!btn)return;
  const blocked=zoneRequired()&&dtype==='delivery'&&zoneOk!==true;
  const hb=hoursBadge();
  const closed=!!(hb&&!hb.open);
  const sub=total();
  const below=S.min_order_minor&&sub<S.min_order_minor;
  btn.disabled=!!(below||blocked||closed);
}
async function saveAddress(text){
  try{await fetch('/shop/api/v1/public/customer-auth/addresses',{method:'POST',credentials:'same-origin',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({address:text})});}catch(e){}
}
window.closeSheet=()=>sheetBack(document.getElementById('sheet'));
document.addEventListener('click',e=>{
  const t=e.target;
  if(t&&t.id!=='ca'&&t.id!=='caSug'&&!t.closest?.('#caSug'))hideSug();
});
const authEl=document.createElement('platform-customer-auth');
authEl.setAttribute('api-base','/shop/api/v1/public/customer-auth');
authEl.setAttribute('company-id',S.company_id||'');
document.body.appendChild(authEl);
function ensureAuth(){
  return new Promise(resolve=>{
    const ok=e=>{done();resolve(e.detail);};
    const no=()=>{done();resolve(null);};
    const done=()=>{authEl.removeEventListener('customer-authenticated',ok);authEl.removeEventListener('customer-auth-cancelled',no);};
    authEl.addEventListener('customer-authenticated',ok);
    authEl.addEventListener('customer-auth-cancelled',no);
    authEl.open();
  });
}
window.submit=async()=>{
  const hbSub=hoursBadge();
  if(hbSub&&!hbSub.open){toast('Сейчас закрыто — '+(hbSub?hbSub.t:''));return;}
  if(dtype==='onsite'&&!tableId){toast('Выберите стол');return;}
  if(zoneRequired()&&dtype==='delivery'&&zoneOk!==true){
    if(zoneOk===false){toast('Адрес вне зоны доставки');return;}
    await zoneCheck();
    if(zoneOk!==true){toast(zoneOk===false?'Адрес вне зоны доставки':'Укажите адрес доставки');return;}
  }
  const customer=await ensureAuth();
  if(!customer)return;
  const addrText=dtype==='delivery'?(document.getElementById('ca')?.value||''):'';
  const body={items:[...cart.values()].map(l=>({product_id:l.pid,qty:l.qty,
    selections:[...l.sel.entries()].map(([option_id,qty])=>({option_id,qty}))})),
    customer_name:document.getElementById('cn').value||customer.phone_e164,
    delivery_type:dtype,
    table_id:dtype==='onsite'?tableId:null,
    address:addrText,
    customer_address_id:dtype==='delivery'?pickedAddrId:'',
    comment:document.getElementById('cc').value,
    source:EMBED?'embed':'web',
    idempotency_key:crypto.randomUUID()};
  const r=await fetch(`/shop/api/v1/public/storefront/${S.slug}/orders`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!r.ok){
    let msg='Не удалось оформить заказ';
    try{const e=await r.json();
      const code=e&&(e.error_code||e.detail);
      if(code==='out_of_delivery_zone')msg='Адрес вне зоны доставки';
      else if(code==='shop_closed'){const np=e.error_params&&e.error_params.next_open;msg='Сейчас закрыто'+(np?' — откроемся '+np:'');}
    }catch(_){}
    toast(msg);return;
  }
  const d=await r.json();
  if(dtype==='delivery'&&addrText&&!pickedAddrId)saveAddress(addrText);
  cart.clear();draw();
  trackOrder(d.public_code,d);
};"""
