"""Базовое состояние и тема: snapshot, форматирование, часы работы, css-токены.

Блок собирается реестром STOREFRONT_BLOCKS; css/js вставляются
в shell как есть — без экранирования скобок.
"""

CSS: str = """*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
::selection{background:color-mix(in srgb,var(--accent) 32%,transparent)}
:focus-visible{outline:2px solid var(--afg);outline-offset:2px}
img{background:var(--card2);transition:opacity .35s ease}
img:not(.ld){opacity:0}
body.lock{overflow:hidden}
body{font-family:ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overscroll-behavior:none;touch-action:manipulation;overflow-x:hidden;overflow-x:clip;text-rendering:optimizeLegibility;-webkit-font-smoothing:antialiased}
.serif{font-family:ui-serif,Georgia,'Times New Roman',serif}
.wrap{max-width:720px;margin:0 auto;padding:0 16px calc(150px + env(safe-area-inset-bottom))}"""

JS: str = """const S=JSON.parse(document.getElementById('snapshot').textContent);
const PRESET=(S.theme&&S.theme.preset)||'menu';
const EMBED=new URLSearchParams(location.search).has('embed');
const TABLE_ID=new URLSearchParams(location.search).get('table')||'';
const TABLES=Array.isArray(S.tables)?S.tables:[];
const fmt=v=>(v/100).toLocaleString('ru-RU')+' ₽';
const IMG=u=>u?`/shop/api/v1/files/download/${u}`:'';
const DAYS=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
function hoursBadge(){
  const wh=S.working_hours||{};
  if(!Object.keys(wh).length)return null;
  const tz=S.timezone||'Europe/Moscow';
  let now;
  try{now=new Date(new Date().toLocaleString('en-US',{timeZone:tz}));}catch(e){now=new Date();}
  const day=(now.getDay()+6)%7;
  const mins=now.getHours()*60+now.getMinutes();
  const hm=v=>{const p=v.split(':');return (+p[0])*60+(+p[1]||0);};
  const range=v=>{if(typeof v!=='string')return null;const p=v.split('-');
    if(p.length<2)return null;const r={o:p[0],c:p[1],om:hm(p[0]),cm:hm(p[1])};
    return r.om===r.cm?null:r;};
  const prev=range(wh[String((day+6)%7)]);
  if(prev&&prev.om>prev.cm&&mins<prev.cm)return{t:'Открыто · до '+prev.c,open:true};
  const today=range(wh[String(day)]);
  if(today){
    if(today.om<today.cm){
      if(mins>=today.om&&mins<today.cm)return{t:'Открыто · до '+today.c,open:true};
      if(mins<today.om)return{t:'Откроемся в '+today.o,open:false};
    }else{
      if(mins>=today.om)return{t:'Открыто · до '+today.c,open:true};
      return{t:'Откроемся в '+today.o,open:false};
    }
  }
  for(let d=1;d<=7;d++){
    const nd=(day+d)%7,tr=range(wh[String(nd)]);
    if(tr)return{t:'Откроемся '+DAYS[nd]+' в '+tr.o,open:false};
  }
  return{t:'временно не работает',open:false};
}"""
