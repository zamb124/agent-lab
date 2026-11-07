"""Выбор точки доставки на карте: bottom-sheet, центр-пин, зона, reverse.

Шит открывается из чекаута (кнопка карты у поля адреса): карта двигается
под неподвижным пином, ``pm-move`` на moveend → локальная проверка зоны
(точный ray-cast по полигону снапшота) + ``/address-reverse`` для имени.
Подтверждение пишет ``addrPoint`` и имя в поле — дальше обычный zoneCheck.

Блок собирается реестром STOREFRONT_BLOCKS; css/js вставляются
в shell как есть — без экранирования скобок.
"""

CSS: str = """.amapbox{position:relative;height:52vh;min-height:320px;border-radius:18px;overflow:hidden;margin:4px 0 12px}
.amapbox platform-map{display:block;width:100%;height:100%}
.ampin{position:absolute;left:50%;top:50%;transform:translate(-50%,-96%);pointer-events:none;z-index:5;color:var(--accent);transition:color .15s ease}
.ampin svg{width:42px;height:42px;fill:currentColor;filter:drop-shadow(0 5px 10px rgba(0,0,0,.45))}
.ampin.bad{color:#d24545}
.amloc{position:absolute;right:12px;bottom:12px;width:44px;height:44px;border-radius:50%;border:0;background:var(--card);color:var(--text);display:grid;place-items:center;cursor:pointer;box-shadow:var(--shadow-sm);z-index:6;transition:color .15s}
.amloc svg{width:20px;height:20px;fill:currentColor}
.amloc:active{color:var(--afg)}
.amname{display:flex;align-items:center;gap:8px;min-height:22px;font-size:14.5px;font-weight:600;margin:0 2px 10px;line-height:1.35}
.amname svg{width:17px;height:17px;fill:var(--afg);flex-shrink:0}
.amname .mut{color:var(--muted);font-weight:500;font-size:13.5px}
.amname .bad{color:#d24545;font-weight:600;font-size:13.5px}"""

JS: str = """/* ——— Шит «точка на карте»: карта двигается под центр-пином ——— */
let amapEl=null,amapObj=null,amapSheet=null,amapCenter=null,amapName='',amapOk=true;
let amapRevTimer=0,amapRevReq=0;
const addrSheet=()=>{
  if(amapSheet)return amapSheet;
  const s=document.createElement('div');
  s.className='sheet';s.id='asheet';
  s.onclick=e=>{if(e.target===s)closeAddrSheet();};
  s.innerHTML=`<div class="panel"><div class="grab"></div><h2>Куда привезти?</h2>
    <div class="amapbox" id="amapBox">
      <div class="ampin" id="amapPin">${ic('pin')}</div>
      <button class="amloc" id="amapLoc" title="Моё местоположение" aria-label="Моё местоположение">${ic('locate')}</button>
    </div>
    <div class="amname" id="amapName"><span class="mut">Двигайте карту — пин в центре</span></div>
    <button class="big" id="amapBtn" onclick="confirmAddrMap()">Доставить сюда</button></div>`;
  document.body.appendChild(s);
  s.querySelector('#amapLoc').onclick=amapLocate;
  amapSheet=s;return s;
};
window.closeAddrSheet=()=>sheetBack(document.getElementById('asheet'));
function ptInRing(lng,lat,ring){let inside=false;
  for(let i=0,j=ring.length-1;i<ring.length;j=i++){
    const xi=ring[i][0],yi=ring[i][1],xj=ring[j][0],yj=ring[j][1];
    if((yi>lat)!==(yj>lat)&&lng<(xj-xi)*(lat-yi)/(yj-yi)+xi)inside=!inside;}
  return inside;}
function inZone(lngLat){const z=S.delivery_zone;
  if(!(z&&z.coordinates&&z.coordinates[0]&&z.coordinates[0].length>3))return true;
  return ptInRing(lngLat[0],lngLat[1],z.coordinates[0]);}
function zoneCentroid(){const z=S.delivery_zone;
  if(!(z&&z.coordinates&&z.coordinates[0]&&z.coordinates[0].length))return null;
  const r=z.coordinates[0];let x=0,y=0;
  for(const p of r){x+=p[0];y+=p[1];}
  return [x/r.length,y/r.length];}
const shopPoint=()=>(S.shop_lat!=null&&S.shop_lng!=null)?[S.shop_lng,S.shop_lat]:null;
function amapLocate(){if(!navigator.geolocation||!amapObj)return;
  navigator.geolocation.getCurrentPosition(
    p=>{if(amapObj)amapObj.easeTo({center:[p.coords.longitude,p.coords.latitude],zoom:17,duration:600});},
    ()=>{},{enableHighAccuracy:true,timeout:6000});}
window.openAddrMap=async()=>{
  const sheet=addrSheet();
  sheetOpen(sheet);
  try{await loadMap();}catch(e){toast('Карта недоступна');sheetBack(sheet);return;}
  const start=addrPoint?[addrPoint.lng,addrPoint.lat]:(shopPoint()||zoneCentroid()||[37.6,55.75]);
  const overlays=[];
  if(S.delivery_zone&&S.delivery_zone.type)
    overlays.push({name:'Зона доставки',data:S.delivery_zone,color:'#e2553f',opacity:.16,width:2.5});
  const markers=[];const sp=shopPoint();
  if(sp)markers.push({lngLat:sp,color:'#8b8378',title:S.name||'Магазин'});
  if(!amapEl){
    amapEl=document.createElement('platform-map');
    amapEl.addEventListener('pm-ready',e=>{amapObj=e.detail.map;
      if(!addrPoint)amapLocate();});
    amapEl.addEventListener('pm-move',e=>{amapCenter=e.detail.center;amapMoved();});
    amapEl.config={center:start,zoom:addrPoint?17:15,moveEvent:true,
      controls:{zoom:true},markers:markers,overlays:overlays,layers:{fetch:false},
      scheme:document.body.classList.contains('light')?'light':'dark'};
    document.getElementById('amapBox').prepend(amapEl);
  }else{
    amapEl.config={...amapEl.config,markers:markers,overlays:overlays,
      scheme:document.body.classList.contains('light')?'light':'dark'};
    if(amapObj)amapObj.jumpTo({center:start,zoom:Math.max(amapObj.getZoom(),15)});
  }
  amapCenter=start;
  amapName='';amapMoved();
};
function amapMoved(){
  const pin=document.getElementById('amapPin'),nameEl=document.getElementById('amapName'),btn=document.getElementById('amapBtn');
  const c=amapCenter;if(!c)return;
  amapOk=inZone(c);
  if(pin)pin.classList.toggle('bad',!amapOk);
  if(btn)btn.disabled=!amapOk;
  if(nameEl)nameEl.innerHTML=amapOk
    ?'<span class="mut">Определяем адрес…</span>'
    :'<span class="bad">Вне зоны доставки</span>';
  clearTimeout(amapRevTimer);const my=++amapRevReq;
  amapRevTimer=setTimeout(async()=>{
    try{
      const r=await fetch(`/shop/api/v1/public/storefront/${S.slug}/address-reverse?lat=${c[1]}&lng=${c[0]}`);
      if(my!==amapRevReq)return;
      const d=await r.json();
      amapName=d.found===true?(d.display_name||''):'';
      if(nameEl)nameEl.innerHTML=!amapOk
        ?'<span class="bad">Вне зоны доставки</span>'
        :(amapName?`${ic('pin')}<span>${esc(amapName)}</span>`
          :'<span class="mut">Точка без адреса — уточните в поле ниже</span>');
    }catch(e){}
  },300);
}
window.confirmAddrMap=()=>{
  if(!amapCenter)return;
  if(!amapOk){toast('Точка вне зоны доставки');return;}
  addrPoint={lat:amapCenter[1],lng:amapCenter[0]};
  const inp=document.getElementById('ca');
  if(inp){if(amapName)inp.value=amapName;else inp.focus();}
  if(pickedAddrId){pickedAddrId='';renderAddrChips();}
  closeAddrSheet();
  zoneOk=null;zoneCheck();
};"""
