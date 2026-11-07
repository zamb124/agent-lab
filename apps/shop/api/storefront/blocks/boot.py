"""Инициализация: первый рендер, восстановление корзины, диплинк ?p=.

Блок собирается реестром STOREFRONT_BLOCKS; css/js вставляются
в shell как есть — без экранирования скобок.
"""

JS: str = """mountBackdrop();
render();
loadCart();for(const l of cart.values())refreshQty(l.pid);draw();
const deeplink=new URLSearchParams(location.search).get('p');
if(deeplink){const el=document.querySelector('[data-pid="'+CSS.escape(deeplink)+'"]');
  if(el){el.classList.add('flash');setTimeout(()=>el.scrollIntoView({behavior:'smooth',block:'center'}),200);}}"""
