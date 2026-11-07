"""Account layer витрины — кабинет покупателя поверх основного shell.

`account_tail()` инжектируется в `_PAGE` перед `</body>` отдельной
`<style>`/`<script>` парой: исходный шаблон витрины (f-string с двойными
скобками) не трогаем — здесь строки сырые, экранирования не требуется.

Архитектура: нижние табы на мобиле, верхний хидер на десктопе; «Меню» —
существующий каталог `#app`, остальные вкладки рендерятся в `#acct`.
`?embed=1`/`?table=` не теряются — вкладки переключают виды без навигации.
Диплинки: `?tab=orders|contacts|profile`, `?order=<code>`, `?reorder=<code>`.
"""

from __future__ import annotations

_CSS = """
<style>
.acctnav{position:fixed;left:0;right:0;bottom:0;z-index:60;display:flex;justify-content:space-around;
  background:color-mix(in srgb,var(--card) 92%,transparent);backdrop-filter:blur(14px);
  border-top:1px solid var(--line);padding:6px 4px calc(6px + env(safe-area-inset-bottom))}
.acctnav button{flex:1;background:none;border:0;color:var(--muted);font:600 12px/1.2 inherit;
  display:flex;flex-direction:column;align-items:center;gap:3px;padding:6px 0;cursor:pointer}
.acctnav button.on{color:var(--afg,var(--accent))}
.acctnav svg{width:22px;height:22px;fill:currentColor}
body.has-nav .wrap{padding-bottom:76px}
body.has-nav .cart{bottom:calc(88px + env(safe-area-inset-bottom))}
#acct{display:none}
body.acct #app,body.acct .cart{display:none}
body.acct #acct{display:block}
.ahead{display:none;position:sticky;top:0;z-index:55;background:color-mix(in srgb,var(--bg) 88%,transparent);
  backdrop-filter:blur(14px);border-bottom:1px solid var(--line);padding:12px 20px;
  align-items:center;gap:14px}
.ahead .brand{font:700 16px/1.2 inherit}
.ahead nav{margin-left:auto;display:flex;gap:4px}
.ahead nav button{background:none;border:0;color:var(--muted);font:600 13px/1 inherit;
  padding:8px 14px;border-radius:10px;cursor:pointer}
.ahead nav button.on{color:var(--afg,var(--accent));background:color-mix(in srgb,var(--accent) 14%,transparent)}
@media(min-width:1024px){.ahead{display:flex}.acctnav{display:none}body.has-nav .wrap{padding-bottom:0}}
.aview{max-width:760px;margin:0 auto;padding:16px 16px 96px}
.acard{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  padding:16px;margin-bottom:12px;cursor:pointer;transition:border-color .15s}
.acard:hover{border-color:color-mix(in srgb,var(--accent) 45%,var(--line))}
.acard .top{display:flex;align-items:baseline;gap:8px;justify-content:space-between}
.acard .shop{font:600 14px/1.3 inherit;color:var(--text)}
.acard .when{font:400 12px/1.3 inherit;color:var(--muted)}
.acard .items{font:400 13px/1.5 inherit;color:var(--muted);margin-top:8px}
.acard .sum{display:flex;justify-content:space-between;align-items:center;margin-top:10px}
.acard .sum b{font:700 15px/1 inherit}
.stchip{display:inline-block;font:600 11px/1 inherit;padding:5px 10px;border-radius:999px;
  background:color-mix(in srgb,var(--accent) 16%,transparent);color:var(--afg,var(--accent))}
.stchip.done{background:color-mix(in srgb,var(--success) 16%,transparent);color:var(--success)}
.stchip.cancelled{background:rgba(255,255,255,.08);color:var(--muted)}
.stchip.live{animation:pulse 1.6s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.55}}
[data-tab=orders]{position:relative}
.acctnav [data-tab=orders].has-active::after{content:'';position:absolute;top:5px;right:calc(50% - 23px);width:8px;height:8px;border-radius:50%;background:var(--accent);animation:pulse 1.4s infinite}
.ahead [data-tab=orders].has-active::after{content:'';position:absolute;top:4px;right:5px;width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pulse 1.4s infinite}
.atl{position:relative;margin:14px 0 4px;padding-left:22px}
.atl::before{content:'';position:absolute;left:6px;top:6px;bottom:6px;width:2px;background:var(--line)}
.atl .ev{position:relative;padding:7px 0;font:500 13px/1.4 inherit;color:var(--muted)}
.atl .ev::before{content:'';position:absolute;left:-20px;top:11px;width:10px;height:10px;border-radius:50%;
  background:var(--card2,#2a241f);border:2px solid var(--line)}
.atl .ev.hit{color:var(--text)}
.atl .ev.hit::before{background:var(--accent);border-color:var(--accent)}
.atl .ev .when{display:block;font-size:11px;color:var(--muted)}
.ditems{margin:10px 0}
.ditems .di{display:flex;align-items:center;gap:10px;padding:7px 0;font:400 13px/1.4 inherit;
  border-bottom:1px dashed var(--line)}
.ditems .di:last-child{border-bottom:0}
.diph{width:44px;height:44px;border-radius:10px;object-fit:cover;flex-shrink:0}
.diph-empty{display:flex;align-items:center;justify-content:center;background:var(--card2);color:var(--muted)}
.diph-empty svg{width:20px;height:20px;fill:currentColor}
.din{flex:1;min-width:0}
.ditems .di .q{color:var(--muted);white-space:nowrap}
.ditems .mods{font-size:12px;color:var(--muted)}
.trow{display:flex;justify-content:space-between;padding:6px 0;font:500 13px/1.4 inherit}
.trow.total{font-weight:700;font-size:15px;border-top:1px solid var(--line);margin-top:6px;padding-top:10px}
.amap{height:220px;border-radius:14px;overflow:hidden;margin-top:12px;border:1px solid var(--line)}
.amap platform-map{display:block;width:100%;height:100%}
.abtn{display:block;width:100%;margin-top:12px;padding:14px;border:0;border-radius:14px;cursor:pointer;
  background:var(--accent);color:var(--on-accent,#fff);font:700 14px/1 inherit}
.abtn.ghost{background:transparent;color:var(--afg,var(--accent));border:1px solid var(--line)}
.abtn.danger{background:transparent;color:#f87171;border:1px solid color-mix(in srgb,#f87171 45%,var(--line))}
.arow{display:flex;gap:10px;align-items:center;padding:8px 0;font:500 13px/1.4 inherit;color:var(--muted)}
.arow b{color:var(--text)}
.arow svg{width:16px;height:16px;fill:currentColor;flex-shrink:0;opacity:.85}
.aempty{text-align:center;color:var(--muted);padding:56px 20px;font:500 14px/1.6 inherit}
.aempty .big{margin-bottom:12px}
.aempty .big svg{width:44px;height:44px;fill:var(--muted);opacity:.7}
.ahours{font:400 12px/1.7 inherit;color:var(--muted);margin-top:6px}
.aback{background:none;border:0;color:var(--afg,var(--accent));font:600 13px/1 inherit;padding:0 0 12px;cursor:pointer}
.revline{margin-top:10px;padding-top:10px;border-top:1px dashed var(--line);display:flex;align-items:center;gap:6px;
  font:600 12.5px/1.2 inherit;color:var(--afg,var(--accent))}
.revline svg{width:14px;height:14px;fill:currentColor}
.revline.own{color:var(--muted)}
.fbt{font:700 15px/1.3 inherit;margin-bottom:10px}
.fbstars{display:flex;gap:4px;margin:0 0 10px}
.fstar{background:none;border:0;padding:6px;cursor:pointer;color:var(--muted);transition:transform .12s}
.fstar svg{width:30px;height:30px;fill:currentColor;display:block}
.fstar.on{color:var(--afg,var(--accent))}
.fstar:active{transform:scale(.85)}
.fbchips{display:flex;flex-wrap:wrap;gap:8px;margin:2px 0 12px}
.fchip{border:1px solid var(--line);background:var(--card2,#2a241f);color:var(--muted);
  font:600 12.5px/1 inherit;padding:9px 14px;border-radius:999px;cursor:pointer;transition:all .15s}
.fchip.on{background:color-mix(in srgb,var(--accent) 16%,transparent);
  border-color:color-mix(in srgb,var(--accent) 45%,var(--line));color:var(--afg,var(--accent))}
.fbtext{width:100%;border:1px solid var(--line);border-radius:14px;background:var(--card2,#2a241f);
  color:var(--text);font:400 13.5px/1.5 inherit;padding:12px 14px;resize:none;box-sizing:border-box}
.fbtext:focus{outline:none;border-color:var(--accent)}
.fbedit{background:none;border:0;color:var(--afg,var(--accent));font:600 13px/1 inherit;padding:10px 0 0;cursor:pointer}
.fbcmt{margin-top:6px;font:400 13px/1.55 inherit}
.rstars{display:inline-flex;gap:1px;color:var(--afg,var(--accent))}
.rstars .off{color:var(--muted)}
.rstars svg{width:15px;height:15px;fill:currentColor;display:block}
.rsum{text-align:center;padding:24px 16px;cursor:default}
.rnum{font:750 42px/1 inherit;letter-spacing:-.02em}
.rsum .rstars{justify-content:center;margin:10px 0 6px}
.rsum .rstars svg{width:18px;height:18px}
.rcount{color:var(--muted);font:500 13px/1.3 inherit}
.ritem{cursor:default}
.ritem .rtop{display:flex;justify-content:space-between;align-items:center;gap:10px}
.ritem .rname{font:600 13.5px/1.3 inherit}
.ritem .rchips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.ritem .fchip{padding:6px 11px;font-size:11.5px;cursor:default}
.ritem .rcomment{margin-top:8px;font:400 13px/1.55 inherit}
.ritem .rwhen{margin-top:8px;font:400 11.5px/1 inherit;color:var(--muted)}
.loycard{background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 13%,var(--card)),var(--card) 70%);
 border-color:color-mix(in srgb,var(--accent) 26%,var(--line))}
.loyhead{display:flex;align-items:center;gap:9px}
.loyic{width:30px;height:30px;border-radius:9px;background:var(--accent);display:grid;place-items:center;flex-shrink:0}
.loyic svg{width:17px;height:17px;fill:var(--on-accent)}
.loyhead b{font:700 14px/1.2 inherit;flex:1;min-width:0}
.loybadge{font:700 11.5px/1 inherit;color:var(--on-accent);background:var(--accent);padding:5px 10px;border-radius:99px;white-space:nowrap}
.loytxt{margin-top:9px;font:400 12.5px/1.45 inherit;color:var(--muted)}
.loybar{height:6px;border-radius:3px;background:color-mix(in srgb,var(--text) 10%,transparent);margin-top:10px;overflow:hidden}
.loybar i{display:block;height:100%;border-radius:3px;background:var(--accent);transition:width .4s ease}
.loyscale{margin-top:5px;font:500 11px/1 inherit;color:var(--muted);text-align:right}
</style>
"""

_JS = r"""
<script>
(function(){
'use strict';
const API='/shop/api/v1/public';
const qs=new URLSearchParams(location.search);
const $=id=>document.getElementById(id);
const el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const money=v=>fmt(v);
const WHEN=s=>{try{return new Date(s).toLocaleString('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}catch(e){return s}};
const authApi=API+'/customer-auth';
const auth=()=>document.querySelector('platform-customer-auth');
const REV_ON=(S.features||{}).reviews!==false;
const FBCHIP=S.feedback_chips||{};
const plural=(n,f)=>f[(n%10===1&&n%100!==11)?0:(n%10>=2&&n%10<=4&&(n%100<10||n%100>=20))?1:2];
const starRow=(n,cls)=>'<span class="rstars'+(cls?' '+cls:'')+'">'+[1,2,3,4,5].map(i=>'<span class="'+(i<=n?'':'off')+'">'+ic('star')+'</span>').join('')+'</span>';
let me=null;
async function fetchMe(){try{const r=await fetch(authApi+'/me',{credentials:'same-origin'});
  me=r.ok?await r.json():null;}catch(e){me=null;}return me;}
async function jget(u){const r=await fetch(u,{credentials:'same-origin'});if(!r.ok)throw r;return r.json();}
async function jpost(u,b){const r=await fetch(u,{method:'POST',credentials:'same-origin',
  headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});if(!r.ok)throw r;return r.json();}

/* --- tabs --- */
const TABS=[
 {id:'menu',label:'Меню',ic:'M280-80v-366h-80v-414h80v-40h80v40h80v-40h80v40h80v414h-80v366H280Zm80-446h240v-254h-80v160h-80v-160h-80v160h-80v-160Z'},
 {id:'orders',label:'Заказы',ic:'M280-80q-33 0-56.5-23.5T200-160q0-33 23.5-56.5T280-240q33 0 56.5 23.5T360-160q0 33-23.5 56.5T280-80Zm400 0q-33 0-56.5-23.5T600-160q0-33 23.5-56.5T680-240q33 0 56.5 23.5T760-160q0 33-23.5 56.5T680-80ZM208-800h590q23 0 35 20.5t1 41.5L692-482q-11 20-29.5 31T622-440H324l-44 80h480v80H280q-45 0-68-39.5t-2-78.5l54-98-144-304H40v-80h130l38 80Z'},
 {id:'reviews',label:'Отзывы',ic:'M233-120l65-281L80-590l288-25 112-265 112 265 288 25-218 189 65 281-247-149-247 149Z'},
 {id:'contacts',label:'Контакты',ic:'M480-480q33 0 56.5-23.5T560-560q0-33-23.5-56.5T480-640q-33 0-56.5 23.5T400-560q0 33 23.5 56.5T480-480Zm0 294q122-112 181-203.5T720-552q0-109-69.5-178.5T480-800q-141 0-210.5 69.5T200-552q0 71 59 162.5T480-186Z'},
 {id:'profile',label:'Профиль',ic:'M480-480q-66 0-113-47t-47-113q0-66 47-113t113-47q66 0 113 47t47 113q0 66-47 113t-113 47Zm0 320q-139 0-241-91.5T98-480q0-38 8-73.5t23-68.5q15 34 43.5 54.5T240-654q66 0 113 47t47 113-47 113-113 47q-34 0-63.5-17.5T146-440q-5 20-7.5 39.5T136-360q0 143 96 241.5T480-160Z'},
].filter(t=>t.id!=='reviews'||REV_ON);
const nav=el('nav','acctnav');
const ahead=el('header','ahead');
ahead.appendChild(el('span','brand',esc(S.name||'Витрина')));
const aheadNav=el('nav');
ahead.appendChild(aheadNav);
for(const t of TABS){
 const svg='<svg viewBox="0 -960 960 960"><path d="'+t.ic+'"/></svg>';
 const b=el('button','',svg+'<span>'+t.label+'</span>');
 b.dataset.tab=t.id;b.onclick=()=>go(t.id);nav.appendChild(b);
 const h=el('button','',t.label);h.dataset.tab=t.id;h.onclick=()=>go(t.id);aheadNav.appendChild(h);
}
document.body.appendChild(nav);
const acct=el('div','');acct.id='acct';
const appEl=document.getElementById('app');
appEl.parentElement.insertBefore(ahead,appEl);
appEl.parentElement.appendChild(acct);
document.body.classList.add('has-nav');
if(EMBED){ahead.style.display='none';}

function markTab(id){
 document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('on',b.dataset.tab===id));
 document.body.classList.toggle('acct',id!=='menu');
}
function setTab(id){
 markTab(id);
 if(id!=='menu'){renderView(id);}
}
function go(id){stopSse();if(id==='orders')curOrder=null;setTab(id);}
window.goTab=go;

/* --- orders --- */
const stCls=s=>s==='done'?'done':s==='cancelled'?'cancelled':'';
let ordersCache=null;
/* Поколение представления: запоздалый ответ загрузчика не перетирает
   другой таб — guard перед каждой записью в acct. */
let viewSeq=0;
const stale=seq=>seq!==viewSeq;
async function loadOrders(force){
 const seq=viewSeq;
 if(!me&&await fetchMe()===null){me=null;}
 if(stale(seq))return;
 if(!me){acct.innerHTML='<div class="aview"><div class="aempty"><div class="big">'+ic('lock')+'</div>Войдите по номеру телефона,<br>чтобы видеть свои заказы<div><button class="abtn" style="max-width:280px;margin:18px auto 0" onclick="loginThen()">Войти</button></div></div></div>';return;}
 let d;
 try{d=await jget(API+'/my/orders?limit=50');}catch(e){
   if(e&&e.status===401){me=null;return loadOrders();}
   if(stale(seq))return;
   acct.innerHTML='<div class="aview"><div class="aempty">Не удалось загрузить заказы</div></div>';return;}
 if(stale(seq))return;
 ordersCache=d.items||[];
 renderOrders(ordersCache);
}
window.loginThen=async()=>{const c=await ensureAuth();if(c){me=await fetchMe();renderView(cur);refreshActiveDot();loadPersonal();}};
window.loadOrders=loadOrders;
window.openOrder=openOrder;
function loyaltyCard(){
 const l=LOYALTY;
 if(!LOY_ON||!l)return null;
 const left=Math.max(0,(l.orders_goal||1)-l.progress);
 const pct=l.orders_goal>0?Math.min(100,Math.round(l.progress/l.orders_goal*100)):0;
 const rl=l.reward_kind==='discount_percent'?('скидка '+l.reward_value+'%'):('скидка '+money(l.reward_value));
 const c=el('div','acard loycard');c.style.cursor='default';
 c.innerHTML='<div class="loyhead"><span class="loyic">'+ic('reward')+'</span><b>Лояльность</b>'
  +(l.rewards_available>0?'<span class="loybadge">'+(l.rewards_available>1?l.rewards_available+' награды':'Награда доступна')+'</span>':'')
  +'</div><div class="loytxt">'
  +(l.rewards_available>0?'Включите награду при оформлении — сработает '+rl:'До награды '+rl+' — ещё '+left+' '+plural(left,['заказ','заказа','заказов']))
  +'</div><div class="loybar"><i style="width:'+(l.rewards_available>0?100:pct)+'%"></i></div>'
  +'<div class="loyscale">'+(l.rewards_available>0?'цель выполнена':l.progress+'/'+l.orders_goal)+'</div>';
 return c;
}
function renderOrders(items){
 const v=el('div','aview');
 const lc=loyaltyCard();
 if(lc)v.appendChild(lc);
 if(!items.length){v.appendChild(el('div','aempty','<div class="big">'+ic('cart')+'</div>Заказов пока нет —<br>самое время выбрать что-нибудь вкусное'));}
 for(const o of items){
  const c=el('div','acard');
  const st=o.status_label||o.status;
  const itemsTxt=(o.items_preview||[]).map(i=>esc(i.name)+' × '+i.qty).join(', ');
  c.innerHTML='<div class="top"><span class="shop">'+esc(o.shop.name||'Магазин')+'</span><span class="stchip '+stCls(o.status)+(o.active?' live':'')+'">'+st+'</span></div>'
   +'<div class="when">#'+esc(o.public_code)+' · '+WHEN(o.created_at)+'</div>'
   +(itemsTxt?'<div class="items">'+itemsTxt+'</div>':'')
   +'<div class="sum"><b>'+money(o.total_minor)+'</b><span class="when">'+(o.delivery_type==='delivery'?'Доставка':o.delivery_type==='onsite'?'В заведении':'Самовывоз')+'</span></div>'
   +(o.feedback?'<div class="revline own">'+ic('star')+'Вы оценили на '+o.feedback.rating+'</div>'
    :o.can_review?'<div class="revline">'+ic('star')+'Оценить заказ</div>':'');
  c.onclick=()=>openOrder(o.public_code);
  v.appendChild(c);
 }
 acct.innerHTML='';acct.appendChild(v);
}
let sse=null,curOrder=null,pollTimer=0;
function stopSse(){if(sse){try{sse.close()}catch(e){}sse=null;}
 if(pollTimer){clearTimeout(pollTimer);pollTimer=0;}}
function applyOrderStatus(code,st,label){
 if(curOrder!==code||!st)return;
 const chip=document.querySelector('.od-st');
 if(chip){chip.textContent=label||st;chip.className='stchip od-st '+stCls(st)+' live';}
 refreshActiveDot();
}
function pollOrder(code){
 if(curOrder!==code)return;
 jget(API+'/my/orders/'+encodeURIComponent(code)).then(o=>{
  if(curOrder!==code)return;
  applyOrderStatus(code,o.status,o.status_label);
  if(o.status==='done'||o.status==='cancelled')return;
  pollTimer=setTimeout(()=>pollOrder(code),20000);
 }).catch(()=>{if(curOrder===code)pollTimer=setTimeout(()=>pollOrder(code),20000);});
}
function watchOrder(code){
 stopSse();
 try{
  sse=new EventSource(API+'/orders/'+encodeURIComponent(code)+'/events');
  sse.onmessage=ev=>{try{const m=JSON.parse(ev.data);
   if(m.status)applyOrderStatus(code,m.status,m.status_label);}catch(e){}};
  // Обрыв SSE — переопрос карточки раз в 20 с до терминального статуса.
  sse.onerror=()=>{if(!pollTimer&&curOrder===code)pollOrder(code);};
 }catch(e){pollOrder(code);}
}
async function openOrder(code){
 const seq=viewSeq;
 curOrder=code;markTab('orders');
 let o;
 try{o=await jget(API+'/my/orders/'+encodeURIComponent(code));}catch(e){
  if(stale(seq))return;
  acct.innerHTML='<div class="aview"><button class="aback" onclick="goTab(\'orders\');loadOrders()">← Назад</button><div class="aempty">Заказ не найден</div></div>';return;}
 if(stale(seq))return;
 const v=el('div','aview');
 v.appendChild(el('button','aback','← Все заказы')).onclick=()=>{curOrder=null;stopSse();loadOrders();};
 const head=el('div','acard');
 head.style.cursor='default';
 head.innerHTML='<div class="top"><span class="shop">'+esc(o.shop.name||'Магазин')+'</span><span class="stchip od-st '+stCls(o.status)+(o.active?' live':'')+'">'+(o.status_label||o.status)+'</span></div>'
  +'<div class="when">#'+esc(o.public_code)+' · '+WHEN(o.created_at)+'</div>';
 v.appendChild(head);
 /* timeline */
 const tl=el('div','atl');
 const hist=(o.status_history&&o.status_history.length)?o.status_history:[{status:o.status,at:o.status_changed_at}];
 for(const h of hist){const e=el('div','ev hit','<b>'+((o.status_labels||{})[h.status]||h.status)+'</b><span class="when">'+WHEN(h.at)+'</span>');tl.appendChild(e);}
 v.appendChild(tl);
 /* items + totals */
 const box=el('div','acard');box.style.cursor='default';
 let rows='<div class="ditems">';
 for(const i of o.items||[]){
  const ph=i.photo_file_id
   ?'<img class="diph" src="'+IMG(i.photo_file_id,'sm!sq')+'" loading="lazy" alt="" onload="this.classList.add(\'ld\')">'
   :'<span class="diph diph-empty">'+ic('restaurant')+'</span>';
  rows+='<div class="di">'+ph+'<span class="din">'+esc(i.name)+(i.modifiers&&i.modifiers.length?'<div class="mods">'+i.modifiers.map(m=>esc(m.option_name)+(m.qty>1?' ×'+m.qty:'')).join(', ')+'</div>':'')+'</span><span class="q">'+i.qty+' × '+money(i.price_minor)+'</span></div>';
 }
 rows+='</div>';
 rows+='<div class="trow"><span>Позиции</span><span>'+money(o.items_total_minor)+'</span></div>';
 if(o.discount_minor)rows+='<div class="trow"><span>Скидка</span><span>−'+money(o.discount_minor)+'</span></div>';
 if(o.loyalty_reward_minor)rows+='<div class="trow"><span>Награда лояльности</span><span>−'+money(o.loyalty_reward_minor)+'</span></div>';
 if(o.delivery_fee_minor)rows+='<div class="trow"><span>Доставка</span><span>'+money(o.delivery_fee_minor)+'</span></div>';
 rows+='<div class="trow total"><span>Итого</span><span>'+money(o.total_minor)+'</span></div>';
 box.innerHTML=rows;v.appendChild(box);
 /* delivery + map */
 if(o.delivery_type==='delivery'&&o.address){
  const dbox=el('div','acard');dbox.style.cursor='default';
  const ddet=[['кв.',o.delivery_flat],['подъезд',o.delivery_entrance],['этаж',o.delivery_floor],['домофон',o.delivery_intercom]]
   .filter(p=>p[1]).map(p=>p[0]+' '+esc(p[1])).join(', ');
  dbox.innerHTML='<div class="arow">'+ic('pin')+' <b>'+esc(o.address)+'</b></div>'
   +(ddet?'<div class="arow">'+ic('pin')+' '+ddet+'</div>':'')
   +(o.delivery_eta_minutes?'<div class="arow">'+ic('clock')+' ETA ≈ '+o.delivery_eta_minutes+' мин</div>':'')
   +(o.shop.address?'<div class="arow">'+ic('store')+' '+esc(o.shop.address)+'</div>':'');
  v.appendChild(dbox);
  mountMap(v,o);
 }
 /* оценка заказа — только на витрине самого магазина */
 const fbc=fbCard(o,code);if(fbc)v.appendChild(fbc);
 /* actions */
 if(o.can_cancel){const cb=el('button','abtn danger','Отменить заказ');
  cb.onclick=async()=>{try{await jpost(API+'/my/orders/'+encodeURIComponent(code)+'/cancel');openOrder(code);refreshActiveDot();}catch(e){toast('Не удалось отменить');}};
  v.appendChild(cb);}
 const rb=el('button','abtn ghost','Повторить заказ');
 rb.onclick=()=>reorder(o);v.appendChild(rb);
 if(o.shop.slug&&o.shop.is_published){const ob=el('button','abtn ghost','Открыть магазин');
  ob.onclick=()=>{location.href=o.shop.storefront_url||('/shop/api/v1/public/s/'+o.shop.slug);};v.appendChild(ob);}
 acct.innerHTML='';acct.appendChild(v);
 if(o.active)watchOrder(code);
}
function mountMap(v,o){
 const pts=[];const overlays=[];
 if(o.shop&&o.shop.lat!=null&&o.shop.lng!=null)pts.push({lngLat:[o.shop.lng,o.shop.lat],color:'var(--accent)',title:o.shop.name||'Магазин'});
 if(o.delivery_lat!=null&&o.delivery_lng!=null)pts.push({lngLat:[o.delivery_lng,o.delivery_lat],color:'#4ade80',title:'Ваш адрес'});
 if(o.delivery_route&&o.delivery_route.type){
  overlays.push({name:'Маршрут',data:o.delivery_route,color:'#e2553f',width:4,opacity:.9});}
 if(o.delivery_zone&&o.delivery_zone.type){
  overlays.push({name:'Зона доставки',data:o.delivery_zone,color:'#e2553f',opacity:.12,width:1});}
 if(!pts.length&&!overlays.length)return;
 const holder=el('div','amap');v.appendChild(holder);
 loadMap().then(()=>{
  const m=document.createElement('platform-map');
  m.config={center:(pts[0]?pts[0].lngLat:[37.6,55.75]),zoom:pts.length>1?12:15,
   controls:{zoom:true,fit:true},markers:pts,overlays:overlays,layers:{fetch:false},
   scheme:document.body.classList.contains('light')?'light':'dark'};
  holder.appendChild(m);
 }).catch(()=>{holder.remove();});
}
/* --- feedback: оценка выполненного заказа --- */
function fbCard(o,code){
 if(!REV_ON||!o.shop||o.shop.slug!==S.slug)return null;
 if(!o.feedback&&!o.can_review)return null;
 const c=el('div','acard fb');c.style.cursor='default';
 if(o.feedback){
  const f=o.feedback;
  c.innerHTML='<div class="fbt">Ваша оценка</div>'+starRow(f.rating,'fbstars')
   +((f.chips||[]).length?'<div class="fbchips">'+f.chips.map(k=>'<span class="fchip on">'+esc((f.chip_labels||{})[k]||k)+'</span>').join('')+'</div>':'')
   +(f.comment?'<div class="fbcmt">'+esc(f.comment)+'</div>':'')
   +'<button class="fbedit" type="button">Изменить</button>';
  c.querySelector('.fbedit').onclick=()=>renderFbForm(c,code,f);
 }else{
  renderFbForm(c,code,null);
 }
 return c;
}
function renderFbForm(c,code,fb){
 let rating=fb?fb.rating:0;
 const chosen=new Set(fb?fb.chips:[]);
 c.innerHTML='<div class="fbt">'+(fb?'Изменить оценку':'Как вам заказ?')+'</div>'
  +'<div class="fbstars" data-role="stars"></div>'
  +'<div class="fbchips" data-role="chips" hidden></div>'
  +'<textarea class="fbtext" data-role="text" maxlength="1000" rows="3" placeholder="Расскажите, что понравилось или что можно улучшить" hidden>'+esc(fb?fb.comment:'')+'</textarea>'
  +'<button class="abtn" type="button" data-role="send" hidden>'+(fb?'Сохранить':'Отправить отзыв')+'</button>';
 const stars=c.querySelector('[data-role=stars]'),chips=c.querySelector('[data-role=chips]'),
  text=c.querySelector('[data-role=text]'),send=c.querySelector('[data-role=send]');
 const paint=()=>{
  stars.innerHTML=[1,2,3,4,5].map(i=>'<button class="fstar'+(i<=rating?' on':'')+'" type="button" data-r="'+i+'">'+ic('star')+'</button>').join('');
  const labels=rating?(rating>=4?FBCHIP.pos:FBCHIP.neg):null;
  chips.innerHTML=labels?Object.keys(labels).map(k=>'<button class="fchip'+(chosen.has(k)?' on':'')+'" type="button" data-c="'+k+'">'+esc(labels[k])+'</button>').join(''):'';
  chips.hidden=!rating;text.hidden=!rating;send.hidden=!rating;
 };
 stars.onclick=ev=>{const b=ev.target.closest('.fstar');if(!b)return;rating=+b.dataset.r;paint();};
 chips.onclick=ev=>{const b=ev.target.closest('.fchip');if(!b)return;const k=b.dataset.c;
  if(chosen.has(k))chosen.delete(k);else chosen.add(k);b.classList.toggle('on');};
 send.onclick=async()=>{
  send.disabled=true;
  try{
   await jpost(API+'/storefront/'+encodeURIComponent(S.slug)+'/orders/'+encodeURIComponent(code)+'/feedback',
    {rating:rating,chips:[...chosen],comment:text.value.trim()});
   toast('Спасибо за отзыв!');openOrder(code);
  }catch(e){send.disabled=false;toast(e&&e.status===401?'Войдите по номеру телефона':'Не удалось отправить');}
 };
 paint();
}

/* --- reviews: публичные отзывы витрины --- */
async function renderReviews(){
 const seq=viewSeq;
 const v=el('div','aview');
 let d;
 try{d=await jget(API+'/storefront/'+encodeURIComponent(S.slug)+'/reviews?limit=50');}
 catch(e){if(stale(seq))return;acct.innerHTML='<div class="aview"><div class="aempty">Не удалось загрузить отзывы</div></div>';return;}
 if(stale(seq))return;
 if(!d.count){v.appendChild(el('div','aempty','<div class="big">'+ic('star')+'</div>Отзывов пока нет —<br>закажите и станьте первым'));}
 else{
  const sum=el('div','acard rsum');
  sum.innerHTML='<div class="rnum">'+Number(d.avg_rating).toFixed(1)+'</div>'+starRow(Math.round(d.avg_rating))
   +'<div class="rcount">'+d.count+' '+plural(d.count,['оценка','оценки','оценок'])+'</div>';
  v.appendChild(sum);
  for(const r of d.items||[]){
   const c=el('div','acard ritem');
   c.innerHTML='<div class="rtop"><span class="rname">'+esc(r.customer_name||'Гость')+'</span>'+starRow(r.rating)+'</div>'
    +((r.chips||[]).length?'<div class="rchips">'+r.chips.map(k=>'<span class="fchip on">'+esc((r.chip_labels||{})[k]||k)+'</span>').join('')+'</div>':'')
    +(r.comment?'<div class="rcomment">'+esc(r.comment)+'</div>':'')
    +'<div class="rwhen">'+WHEN(r.created_at)+'</div>';
   v.appendChild(c);
  }
 }
 acct.innerHTML='';acct.appendChild(v);
}

async function reorder(o){
 const v=o||null;
 if(!v)return;
 let added=0,skipped=0;
 for(const i of v.items||[]){
  const p=byId(i.product_id);
  if(!p){skipped++;continue;}
  const sel=new Map();
  for(const m of i.modifiers||[])if(m.option_id)sel.set(m.option_id,m.qty||1);
  const key=i.product_id+'#'+selHash(sel);
  const l=cart.get(key)||{pid:i.product_id,sel,qty:0};
  l.qty+=i.qty;cart.set(key,l);added+=i.qty;refreshQty(i.product_id);
 }
 draw();
 toast(added?('В корзину добавлено: '+added):'Позиции недоступны');
 if(added)go('menu');
}
async function reorderByCode(code){
 let o;try{o=await jget(API+'/my/orders/'+encodeURIComponent(code));}catch(e){toast('Заказ не найден');return;}
 reorder(o);
}

/* --- contacts --- */
function renderContacts(){
 const v=el('div','aview');
 const card=el('div','acard');card.style.cursor='default';
 let h='<div class="shop" style="font-size:18px">'+esc(S.name||'Магазин')+'</div>';
 if(S.address)h+='<div class="arow">'+ic('pin')+' <b>'+esc(S.address)+'</b></div>';
 if(S.city)h+='<div class="arow">'+ic('pin')+' '+esc(S.city)+'</div>';
 if(S.phone)h+='<div class="arow">'+ic('call')+' <a style="color:var(--afg)" href="tel:'+esc(S.phone)+'">'+esc(S.phone)+'</a></div>';
 const hb=hoursBadge();if(hb)h+='<div class="arow">'+ic('clock')+' '+esc(hb.t)+'</div>';
 card.innerHTML=h;v.appendChild(card);
 jget(API+'/storefront/'+encodeURIComponent(S.slug)+'/geo').then(g=>{
  if(!g)return;
  const zone=(g.delivery_zone&&g.delivery_zone.type)?g.delivery_zone:null;
  if(g.lat==null&&!zone)return;
  const holder=el('div','amap');v.appendChild(holder);
  loadMap().then(()=>{
   const m=document.createElement('platform-map');
   const ov=[];
   if(zone)ov.push({name:'Зона доставки',data:zone,color:'#e2553f',opacity:.12,width:1});
   const mk=[];
   if(g.lat!=null)mk.push({lngLat:[g.lng,g.lat],color:'var(--accent)',title:S.name});
   let box=null;
   if(zone){
    const pts=[];
    (function walk(c){if(typeof c[0]==='number'){pts.push(c);return;}for(const x of c)walk(x);})(zone.coordinates);
    let a=pts[0][0],b=a,c=pts[0][1],d=c;
    for(const p of pts){if(p[0]<a)a=p[0];if(p[0]>b)b=p[0];if(p[1]<c)c=p[1];if(p[1]>d)d=p[1];}
    box=[[a,c],[b,d]];
   }
   m.config={center:g.lat!=null?[g.lng,g.lat]:[(box[0][0]+box[1][0])/2,(box[0][1]+box[1][1])/2],zoom:12,
    controls:{zoom:true,fit:true},
    markers:mk,
    overlays:ov,layers:{fetch:false},scheme:document.body.classList.contains('light')?'light':'dark'};
   if(box)m.addEventListener('pm-ready',ev=>ev.detail.map.fitBounds(box,{padding:60,duration:400}),{once:true});
   holder.appendChild(m);
  }).catch(()=>{holder.remove();});
 }).catch(()=>{});
 acct.innerHTML='';acct.appendChild(v);
}

/* --- profile --- */
async function renderProfile(){
 const seq=viewSeq;
 if(!me)await fetchMe();
 if(stale(seq))return;
 const v=el('div','aview');
 if(!me){v.appendChild(el('div','aempty','<div class="big">'+ic('person')+'</div>Вы не вошли<div><button class="abtn" style="max-width:280px;margin:18px auto 0" onclick="loginThen()">Войти по номеру</button></div>'));}
 else{
  const card=el('div','acard');card.style.cursor='default';
  card.innerHTML='<div class="shop" style="font-size:18px">'+esc(me.name||me.phone_e164)+'</div>'
   +'<div class="arow">'+ic('call')+' '+esc(me.phone_e164)+'</div>'
   +(me.scope_company_ids&&me.scope_company_ids.length?'<div class="arow">'+ic('store')+' Витрин в профиле: '+me.scope_company_ids.length+'</div>':'');
  v.appendChild(card);
  const nb=el('button','abtn ghost','Сменить имя');
  nb.onclick=async()=>{const n=prompt('Ваше имя',me.name||'');if(n==null)return;
   try{me=await jpost(authApi+'/me',{name:n});renderProfile();}catch(e){toast('Не удалось сохранить');}};
  v.appendChild(nb);
  const lb=el('button','abtn danger','Выйти');
  lb.onclick=async()=>{try{await fetch(authApi+'/logout',{method:'POST',credentials:'same-origin'});}catch(e){}
   me=null;ordersCache=null;refreshActiveDot();renderProfile();};
  v.appendChild(lb);
 }
 acct.innerHTML='';acct.appendChild(v);
}

/* --- personal: «как всегда» и подписки «сообщить о появлении» --- */
async function loadPersonal(){
 try{
  if(!me&&await fetchMe()===null)return;
  if(!me)return;
  const d=await jget(API+'/storefront/'+encodeURIComponent(S.slug)+'/personal');
  LOYALTY=d.loyalty||null;
  if(cur==='orders'&&!curOrder&&ordersCache)renderOrders(ordersCache);
  (d.back_in_stock_ids||[]).forEach(id=>SUBS.add(id));
  (d.favorite_ids||[]).forEach(id=>FAVS.add(id));
  const usual=SHELVES.find(s=>s.kind==='usual');
  if(usual&&(d.usual||[]).length){
   usual.product_ids=d.usual.map(u=>u.product_id);
   const holder=document.getElementById('sh-'+usual.id);
   if(holder)holder.outerHTML=shelfHtml(usual);
  }
  const fav=SHELVES.find(s=>s.kind==='favorites');
  if(fav&&(d.favorite_ids||[]).length){
   fav.product_ids=d.favorite_ids;
   const fh=document.getElementById('sh-'+fav.id);
   if(fh)fh.outerHTML=shelfHtml(fav);
  }
  if(FAVS.size)document.querySelectorAll('[data-fav]').forEach(el=>{
   el.classList.toggle('on',FAVS.has(el.dataset.fav));});
 }catch(e){}
}

/* --- active-order dot на табе «Заказы»: пульсирует, пока есть живой заказ --- */
let dotTimer=0;
async function refreshActiveDot(){
 try{
  if(!me)await fetchMe();
  const on=!!(me&&((await jget(API+'/my/orders?active=true&limit=1')).items||[])[0]);
  document.querySelectorAll('[data-tab=orders]').forEach(b=>b.classList.toggle('has-active',on));
  if(!on)return;
 }catch(e){}
 clearTimeout(dotTimer);dotTimer=setTimeout(refreshActiveDot,60000);
}

/* --- view switch --- */
let cur='menu';
function renderView(id){
 cur=id;viewSeq++;
 if(id==='orders'){if(curOrder)openOrder(curOrder);else loadOrders();}
 else if(id==='reviews')renderReviews();
 else if(id==='contacts')renderContacts();
 else if(id==='profile')renderProfile();
}
setTab('menu');

/* --- deeplinks --- */
const tab=qs.get('tab');
const order=qs.get('order');
const reorderCode=qs.get('reorder');
if(order){openOrder(order);}
else if(reorderCode){reorderByCode(reorderCode);}
else if(tab&&TABS.some(t=>t.id===tab))go(tab);
refreshActiveDot();
loadPersonal();

/* --- PWA: service worker только на витринном хосте (scope '/') --- */
if('serviceWorker' in navigator&&location.pathname==='/'){
 try{navigator.serviceWorker.register('/sw.js');}catch(e){}
}
})();
</script>
"""


def account_tail() -> str:
    """`<style>`+`<script>` кабинета покупателя — вставка перед `</body>`."""
    return _CSS + _JS
