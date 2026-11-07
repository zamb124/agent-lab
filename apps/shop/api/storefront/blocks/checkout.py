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
.sug{display:none;margin-top:6px;border:1px solid var(--line);border-radius:12px;background:var(--card);overflow:hidden auto;max-height:288px;box-shadow:0 8px 24px color-mix(in srgb,var(--afg) 14%,transparent);overscroll-behavior:contain}
.sug.open{display:block}
.sugrow{padding:11px 14px;font-size:14px;font-weight:550;color:var(--text);cursor:pointer;border-bottom:1px solid var(--line);line-height:1.35}
.sugrow:last-child{border-bottom:0}
.sugrow:hover,.sugrow.on{background:color-mix(in srgb,var(--accent) 10%,transparent)}
.sugrow b{font-weight:800}
.sugrow small{display:block;font-size:11.5px;color:var(--muted);font-weight:500}
.sugrow.sugempty{cursor:default;color:var(--muted);font-weight:500}
.sugrow.sugempty:hover{background:transparent}
.zstat svg{width:16px;height:16px;fill:currentColor;flex-shrink:0}
.aaddr{display:flex;gap:8px;align-items:stretch;margin:6px 0}
.aaddr input.f{margin:0;flex:1;min-width:0}
.amapbtn{flex-shrink:0;width:54px;border-radius:14px;border:1px solid var(--line);background:var(--card2);color:var(--text);cursor:pointer;display:grid;place-items:center;transition:border-color .15s,color .15s}
.amapbtn svg{width:20px;height:20px;fill:currentColor}
.amapbtn:hover{border-color:var(--afg);color:var(--afg)}
.dgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:8px}
.dgrid input.f{margin:0;padding:12px 10px;font-size:13.5px;text-align:center}
@media (max-width:480px){.dgrid{grid-template-columns:repeat(2,1fr)}}
.cl.loy{cursor:pointer;user-select:none;border-radius:12px;margin:4px -6px;padding:8px 6px;transition:background .15s}
.cl.loy:hover{background:color-mix(in srgb,var(--accent) 7%,transparent)}
.cl.loy .n{display:flex;align-items:center;gap:9px}
.cl.loy .n>svg{width:19px;height:19px;fill:var(--afg);flex-shrink:0}
.cl.loy .loysub{color:var(--afg)}
.lswt{flex-shrink:0;width:44px;height:26px;border-radius:13px;background:color-mix(in srgb,var(--text) 16%,transparent);position:relative;transition:background .18s}
.lswt i{position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:transform .18s;box-shadow:0 1px 3px rgba(0,0,0,.3)}
.lswt.on{background:var(--accent)}
.lswt.on i{transform:translateX(18px)}
.cl.loysave span{color:var(--afg)}
.cl.loyhint{cursor:default;opacity:.85}
.cl.loyhint .n>svg{width:17px;height:17px;fill:var(--muted);flex-shrink:0}
.cl.loyhint .loyhintt{font-size:13px;color:var(--muted)}"""

JS: str = """let dtype='';
let tableId=TABLE_ID&&TABLES.some(t=>t.id===TABLE_ID)?TABLE_ID:'';
const DTYPES=[['delivery','truck','Доставка',S.delivery_enabled],['pickup','store','Самовывоз',S.pickup_enabled],['onsite','restaurant','В заведении',S.onsite_enabled&&TABLES.length>0]].filter(d=>d[3]);
/* Меню без заказов: все выдачи выключены — прячем корзину и лист оформления. */
if(!DTYPES.length)document.documentElement.classList.add('no-order');
/* Лояльность: undefined — personal ещё не грузили; null — нет сессии/фичи. */
let LOYALTY=undefined,useLoyalty=false;
const LOY_ON=(S.features||{}).loyalty===true;
async function ensureLoyalty(){
  if(!LOY_ON)return;
  try{const r=await fetch(`/shop/api/v1/public/storefront/${S.slug}/personal`,{credentials:'same-origin'});
    LOYALTY=r.ok?((await r.json()).loyalty||null):null;}catch(e){LOYALTY=null;}
  if(!(LOYALTY&&LOYALTY.rewards_available>0))useLoyalty=false;
}
function loyaltyRow(){
  const l=LOYALTY;
  if(l===undefined)return'';
  if(l&&l.rewards_available>0){
    const lbl=l.reward_kind==='discount_percent'?('−'+l.reward_value+'%'):('−'+fmt(l.reward_value));
    return `<div class="cl loy${useLoyalty?' on':''}" id="loyRow" onclick="toggleLoyalty()">
      <span class="n">${ic('reward')}<span>Награда лояльности<span class="mods loysub">${useLoyalty?'Применена · '+esc(lbl):'Доступна '+esc(lbl)+' — нажмите, чтобы применить'}</span></span></span>
      <span class="lswt${useLoyalty?' on':''}"><i></i></span></div>`;
  }
  const p=S.loyalty;
  if(!p)return'';
  const rl=p.reward_kind==='discount_percent'?('скидка '+p.reward_value+'%'):('скидка '+fmt(p.reward_value));
  const hint=l&&l.orders_goal
    ?`До награды ${esc(rl)} — прогресс ${l.progress}/${l.orders_goal}`
    :`Каждый ${p.orders_goal}-й заказ — ${esc(rl)}`;
  return `<div class="cl loyhint" id="loyRow"><span class="n">${ic('reward')}<span class="loyhintt">${hint}</span></span></div>`;
}
window.toggleLoyalty=()=>{useLoyalty=!useLoyalty;
  const row=document.getElementById('loyRow');
  if(row)row.outerHTML=loyaltyRow();
  refreshSavings();};
/* Ключ идемпотентности живёт на одно открытие листа: ретрай после обрыва
   ответа и повторный тап по кнопке не создают второй заказ и не списывают
   награду повторно. */
let orderKey='',submitting=false;
window.openSheet=()=>{
  if(!DTYPES.length)return;
  orderKey=crypto.randomUUID();
  if(!dtype)dtype=(tableId&&S.onsite_enabled)?'onsite':(DTYPES[0]?DTYPES[0][0]:'');
  renderSheet();
  if(LOY_ON)ensureLoyalty().then(()=>{
    const row=document.getElementById('loyRow');
    if(row)row.outerHTML=loyaltyRow();
    else{const sv=document.getElementById('savings');
      if(sv&&loyaltyRow())sv.insertAdjacentHTML('afterend',loyaltyRow());}
    refreshSavings();
  });
  sheetOpen(document.getElementById('sheet'));
};
window.setDtype=t=>{dtype=t;
  // Смена способа выдачи сбрасывает адресное состояние: точка и результат
  // зоновой проверки относятся к прежнему выбору и не наследуются.
  addrPoint=null;pickedAddrId='';zoneOk=null;sugItems=[];
  renderSheet();};
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
  cartUpsellHtml()+
  seg+
  `<div id="savings"></div>`+
  loyaltyRow()+
  (dtype==='delivery'?`<div class="cl"><span>Доставка</span><b class="s" id="feeVal">${fmt(fee)}</b></div>`:'')+
  `<div class="cl" style="border-bottom:0"><b>Итого</b><b class="s" id="cartTotal" style="font-size:18px">${fmt(sub+fee)}</b></div>
  <input class="f" id="cn" placeholder="Ваше имя">
  ${dtype==='onsite'?`<select class="f" id="ct" onchange="setTable(this.value)"><option value="">Выберите стол</option>${TABLES.map(t=>`<option value="${t.id}"${t.id===tableId?' selected':''}>${esc(t.label)}</option>`).join('')}</select>`:''}
  ${dtype==='delivery'?`<div class="achips" id="addrChips"></div><div class="aaddr"><input class="f" id="ca" placeholder="Адрес доставки" autocomplete="street-address" oninput="onAddrInput()" onkeydown="onAddrKey(event)" role="combobox" aria-expanded="false" aria-controls="caSug"><button class="amapbtn" type="button" onclick="openAddrMap()" title="Выбрать точку на карте" aria-label="Выбрать точку на карте">${ic('pin')}</button></div><div class="sug" id="caSug" role="listbox"></div><div class="dgrid"><input class="f" id="dflat" placeholder="Кв/офис" autocomplete="off"><input class="f" id="dentrance" placeholder="Подъезд" autocomplete="off"><input class="f" id="dfloor" placeholder="Этаж" autocomplete="off"><input class="f" id="dintercom" placeholder="Домофон" autocomplete="off"></div><div class="zstat" id="zoneStat"></div>`:''}<input class="f" id="cc" placeholder="Комментарий к заказу">
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
      delivery_type:dtype,use_loyalty_reward:useLoyalty};
    const r=await fetch(`/shop/api/v1/public/storefront/${S.slug}/cart/price`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(my!==priceReq||!r.ok)return;
    const d=await r.json();
    const el=document.getElementById('savings');
    if(el)el.innerHTML=(d.discount_minor>0
      ?`<div class="cl save"><span>Выгода${d.applied_promos.length?' · '+esc(d.applied_promos.map(a=>a.name).join(', ')):''}</span><b class="s">−${fmt(d.discount_minor)}</b></div>`:'')
      +(d.loyalty_reward_minor>0
      ?`<div class="cl save loysave"><span>Награда лояльности</span><b class="s">−${fmt(d.loyalty_reward_minor)}</b></div>`:'');
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
let addrPoint=null;       // {lat,lng} точки подсказки/пина карты/сохранённого — едет в заказ
let sugItems=[];          // последняя выдача автокомплита (для pickSug по индексу)
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
  // Координаты сохранённого адреса — та же точка, что проверит сервер.
  addrPoint=a&&a.lat!=null&&a.lng!=null?{lat:a.lat,lng:a.lng}:null;
  renderAddrChips();
  zoneOk=null;clearTimeout(zTimer);zTimer=setTimeout(zoneCheck,150);
};
let zTimer=0,zReq=0,sugTimer=0,sugReq=0,sugIdx=-1;
function hideSug(){const el=document.getElementById('caSug');if(el)el.classList.remove('open');
  const inp=document.getElementById('ca');if(inp)inp.setAttribute('aria-expanded','false');
  sugIdx=-1;}
window.pickSug=(i)=>{
  const it=sugItems[i];
  const inp=document.getElementById('ca');
  if(inp&&it)inp.value=it.display_name||'';
  // Точка выбранной подсказки — сервер проверяет именно её, без перегеокода.
  addrPoint=it?{lat:it.lat,lng:it.lng}:null;
  hideSug();
  if(pickedAddrId){pickedAddrId='';renderAddrChips();}
  zoneOk=null;clearTimeout(zTimer);zoneCheck();
};
function hlq(name,q){
  const i=name.toLowerCase().indexOf(q.toLowerCase());
  if(i<0)return esc(name);
  return esc(name.slice(0,i))+'<b>'+esc(name.slice(i,i+q.length))+'</b>'+esc(name.slice(i+q.length));
}
window.onAddrKey=e=>{
  const el=document.getElementById('caSug');
  if(!el||!el.classList.contains('open')){
    if(e.key==='ArrowDown'){clearTimeout(sugTimer);addrSuggest();}
    return;}
  const rows=[...el.querySelectorAll('.sugrow:not(.sugempty)')];
  if(!rows.length)return;
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){
    e.preventDefault();
    sugIdx=e.key==='ArrowDown'?(sugIdx+1)%rows.length:(sugIdx-1+rows.length)%rows.length;
    rows.forEach((r,i)=>r.classList.toggle('on',i===sugIdx));
    rows[sugIdx].scrollIntoView({block:'nearest'});
  }else if(e.key==='Enter'&&sugIdx>=0){
    e.preventDefault();
    pickSug(Number(rows[sugIdx].dataset.i));
  }else if(e.key==='Escape'){
    e.preventDefault();hideSug();
  }
};
async function addrSuggest(){
  const inp=document.getElementById('ca');
  const el=document.getElementById('caSug');
  const q=(inp?.value||'').trim();
  if(!el)return;
  if(q.length<3){hideSug();return;}
  const my=++sugReq;
  try{
    let url=`/shop/api/v1/public/storefront/${S.slug}/address-suggest?q=${encodeURIComponent(q)}`;
    if(addrPoint)url+=`&lat=${addrPoint.lat}&lng=${addrPoint.lng}`;
    const r=await fetch(url);
    if(my!==sugReq)return;
    const d=await r.json();
    const items=Array.isArray(d.items)?d.items:[];
    sugItems=items;sugIdx=-1;
    el.innerHTML=items.length
      ?items.map((a,i)=>`<div class="sugrow" role="option" data-i="${i}" data-name="${esc(a.display_name||'')}" onclick="pickSug(${i})">${hlq(a.display_name||'',q)}<small>${esc(a.city||'')}</small></div>`).join('')
      :`<div class="sugrow sugempty">Адрес не найден — укажите точку на карте</div>`;
    el.classList.add('open');
    if(inp)inp.setAttribute('aria-expanded','true');
  }catch(e){hideSug();}
}
window.onAddrInput=()=>{
  if(pickedAddrId){pickedAddrId='';renderAddrChips();}
  addrPoint=null;
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
  if(q.length<5&&!addrPoint){zoneOk=null;updatePayBtn();return;}
  const my=++zReq;
  if(st){st.className='zstat wait';st.textContent='Проверяем зону доставки…';}
  try{
    let url=`/shop/api/v1/public/storefront/${S.slug}/delivery-check?address=${encodeURIComponent(q)}`;
    if(addrPoint)url+=`&lat=${addrPoint.lat}&lng=${addrPoint.lng}`;
    const r=await fetch(url);
    if(my!==zReq)return;
    const d=await r.json();
    zoneOk=d.ok===true?true:(d.ok===false?false:null);
    // Точку, которую подтвердил сервер, фиксируем — в заказ едет она же.
    if(zoneOk===true&&d.lat!=null&&d.lng!=null)addrPoint={lat:d.lat,lng:d.lng};
    if(st){
      if(zoneOk===true){st.className='zstat ok';
        const eta=d.eta_minutes?` ~${d.eta_minutes} мин`:'';
        st.innerHTML=ic('check')+esc('Доставим'+eta+(d.inside_zone===false?'':' · '+((d.normalized||'').split(',')[0])));}
      else if(zoneOk===false){st.className='zstat bad';
        st.innerHTML=ic('warn')+esc(d.reason==='out_of_delivery_zone'?'Адрес вне зоны доставки':'Адрес не удалось проверить');}
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
    headers:{'Content-Type':'application/json'},body:JSON.stringify({address:text,
      lat:addrPoint?addrPoint.lat:null,lng:addrPoint?addrPoint.lng:null})});}catch(e){}
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
async function ensureAuth(){
  // Живая сессия резолвится без auth-шита — иначе модалка вспыхивает и гаснет.
  try{
    const r=await fetch(API+'/customer-auth/me',{credentials:'same-origin'});
    if(r.ok)return await r.json();
  }catch(e){}
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
  if(submitting)return;
  const hbSub=hoursBadge();
  if(hbSub&&!hbSub.open){toast('Сейчас закрыто — '+(hbSub?hbSub.t:''));return;}
  if(dtype==='onsite'&&!tableId){toast('Выберите стол');return;}
  if(zoneRequired()&&dtype==='delivery'&&zoneOk!==true){
    if(zoneOk===false){toast('Адрес вне зоны доставки');return;}
    await zoneCheck();
    if(zoneOk!==true){toast(zoneOk===false?'Адрес вне зоны доставки':'Укажите адрес доставки');return;}
  }
  const addrText=dtype==='delivery'?(document.getElementById('ca')?.value||'').trim():'';
  if(dtype==='delivery'&&!addrText&&!pickedAddrId){toast('Укажите адрес доставки');return;}
  const customer=await ensureAuth();
  if(!customer)return;
  const val=id=>(document.getElementById(id)?.value||'').trim();
  const body={items:[...cart.values()].map(l=>({product_id:l.pid,qty:l.qty,
    selections:[...l.sel.entries()].map(([option_id,qty])=>({option_id,qty}))})),
    customer_name:document.getElementById('cn').value||customer.phone_e164,
    delivery_type:dtype,
    table_id:dtype==='onsite'?tableId:null,
    address:addrText,
    customer_address_id:dtype==='delivery'?pickedAddrId:'',
    delivery_lat:dtype==='delivery'&&addrPoint?addrPoint.lat:null,
    delivery_lng:dtype==='delivery'&&addrPoint?addrPoint.lng:null,
    delivery_flat:dtype==='delivery'?val('dflat'):'',
    delivery_entrance:dtype==='delivery'?val('dentrance'):'',
    delivery_floor:dtype==='delivery'?val('dfloor'):'',
    delivery_intercom:dtype==='delivery'?val('dintercom'):'',
    comment:document.getElementById('cc').value,
    use_loyalty_reward:useLoyalty,
    source:EMBED?'embed':'web',
    idempotency_key:orderKey||crypto.randomUUID()};
  submitting=true;
  const pb=document.getElementById('payBtn');if(pb)pb.disabled=true;
  let r=null;
  try{r=await fetch(`/shop/api/v1/public/storefront/${S.slug}/orders`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}
  catch(e){submitting=false;if(pb)pb.disabled=false;toast('Нет связи — заказ не отправлен. Попробуйте ещё раз');return;}
  submitting=false;if(pb)pb.disabled=false;
  if(!r.ok){
    let msg='Не удалось оформить заказ';
    try{const e=await r.json();
      const code=e&&(e.error_code||e.detail);
      if(code==='out_of_delivery_zone')msg='Адрес вне зоны доставки';
      else if(code==='address_unverifiable')msg='Адрес не удалось проверить — уточните или выберите точку на карте';
      else if(code==='shop_closed'){const np=e.error_params&&e.error_params.next_open;msg='Сейчас закрыто'+(np?' — откроемся '+np:'');}
      else if(code==='loyalty_reward_unavailable'){useLoyalty=false;LOYALTY=undefined;msg='Награда уже использована';}
      else if(code==='loyalty_disabled'){useLoyalty=false;msg='Награды сейчас недоступны';}
    }catch(_){}
    toast(msg);return;
  }
  const d=await r.json();
  LOYALTY=undefined;useLoyalty=false;orderKey='';
  if(dtype==='delivery'&&addrText&&!pickedAddrId)saveAddress(addrText);
  cart.clear();draw();
  trackOrder(d.public_code,d);
};"""
