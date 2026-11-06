"""Корзина: состояние, шагеры количества, плавающая кнопка с суммой.

Блок собирается реестром STOREFRONT_BLOCKS; css/js вставляются
в shell как есть — без экранирования скобок.
"""

CSS: str = """.cart{position:fixed;left:50%;transform:translateX(-50%);bottom:calc(18px + env(safe-area-inset-bottom));width:min(688px,92vw);background:var(--accent);color:var(--on-accent);border:0;font:inherit;font-size:16px;font-weight:650;padding:17px;border-radius:99px;cursor:pointer;display:none;box-shadow:var(--shadow-lg);z-index:10;letter-spacing:.01em}
.cart.show{display:block;animation:pop .25s ease}
@keyframes pop{from{transform:translateX(-50%) translateY(16px);opacity:0}}"""

JS: str = """window.haptic=()=>{if(navigator.vibrate)navigator.vibrate(8);};
window.addPlain=(pid,d)=>{const key=pid+'#';const l=cart.get(key)||{pid,sel:new Map(),qty:0};
  l.qty+=d;if(l.qty<=0)cart.delete(key);else cart.set(key,l);if(d>0)haptic();refreshQty(pid);draw();};
window.addLine=(key,d)=>{const l=cart.get(key);if(!l)return;l.qty+=d;
  if(l.qty<=0)cart.delete(key);else cart.set(key,l);refreshQty(l.pid);draw();};
function total(){let t=0;for(const l of cart.values()){const p=byId(l.pid);if(p)t+=unitPrice(p,l.sel)*l.qty;}return t;}
function count(){let n=0;for(const l of cart.values())n+=l.qty;return n;}
function draw(){const b=document.getElementById('cart');const n=count();saveCart();
  if(n){b.textContent=`Корзина · ${n} · ${fmt(total())} →`;b.classList.add('show');
    if(n>(b._n||0)){b.classList.remove('pop');void b.offsetWidth;b.classList.add('pop');}}else b.classList.remove('show');
  b._n=n;}"""
