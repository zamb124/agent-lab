"""Bottom-sheet инфраструктура: открытие/закрытие, drag-to-close, history, toast.

Блок собирается реестром STOREFRONT_BLOCKS; css/js вставляются
в shell как есть — без экранирования скобок.
"""

CSS: str = """.sheet{position:fixed;inset:0;background:var(--overlay);backdrop-filter:blur(4px);display:none;z-index:20}
.sheet.show{display:block}
.panel{position:absolute;left:50%;transform:translateX(-50%);bottom:0;width:min(720px,100vw);max-height:88vh;overflow:auto;background:var(--card);border-radius:26px 26px 0 0;padding:10px 20px calc(44px + env(safe-area-inset-bottom));animation:up .25s ease;transition:transform .18s ease;box-shadow:var(--shadow-lg)}
.panel.drag{transition:none}
.grab{width:38px;height:5px;border-radius:99px;background:var(--line);margin:0 auto 12px;touch-action:none}
@keyframes up{from{transform:translateX(-50%) translateY(40px)}}
.panel h2{font-size:21px;margin-bottom:16px;letter-spacing:-.01em}
.pshare{position:absolute;top:14px;right:14px;width:38px;height:38px;border-radius:50%;background:rgba(18,18,20,.55);backdrop-filter:blur(8px);color:#fff;display:grid;place-items:center;z-index:2}
.pshare svg{width:18px;height:18px;fill:currentColor}
.toast{position:fixed;left:50%;transform:translateX(-50%) translateY(12px);bottom:calc(90px + env(safe-area-inset-bottom));background:#1c1c20;color:#fff;padding:10px 18px;border-radius:999px;border:1px solid rgba(255,255,255,.08);font-size:13.5px;opacity:0;pointer-events:none;transition:.25s ease;z-index:40;box-shadow:0 8px 24px rgba(0,0,0,.3)}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}"""

JS: str = """document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeCust();closeSheet();}});
let sheetDepth=0,popGuard=0;
function syncLock(){document.body.classList.toggle('lock',!!document.querySelector('.sheet.show'));}
function sheetOpen(el){el.classList.add('show');sheetDepth++;history.pushState({sh:1},'');syncLock();}
function sheetBack(el){if(!el.classList.contains('show'))return;
  el.classList.remove('show');if(sheetDepth>0){sheetDepth--;popGuard++;history.back();}syncLock();}
window.addEventListener('popstate',()=>{if(popGuard>0){popGuard--;return;}
  const list=document.querySelectorAll('.sheet.show');const s=list[list.length-1];
  if(s){s.classList.remove('show');sheetDepth=Math.max(0,sheetDepth-1);syncLock();}});
let dragY=null,dragEl=null;
document.addEventListener('touchstart',e=>{const p=e.target.closest('.panel');if(!p)return;
  if(matchMedia('(min-width:1024px)').matches)return;
  if(e.touches[0].clientY-p.getBoundingClientRect().top>46)return;
  dragY=e.touches[0].clientY;dragEl=p;p.classList.add('drag');},{passive:true});
document.addEventListener('touchmove',e=>{if(dragY==null)return;
  const dy=Math.max(0,e.touches[0].clientY-dragY);
  if(dy>0)e.preventDefault();
  dragEl.style.transform=`translateX(-50%) translateY(${dy}px)`;},{passive:false});
document.addEventListener('touchend',e=>{if(dragY==null)return;
  const dy=Math.max(0,e.changedTouches[0].clientY-dragY);
  const p=dragEl;p.classList.remove('drag');p.style.transform='';dragY=dragEl=null;
  if(dy>90)sheetBack(p.parentElement);});"""
