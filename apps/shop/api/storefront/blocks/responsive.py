"""Адаптив: desktop-раскладка, light-тема токены вне :root.

Блок собирается реестром STOREFRONT_BLOCKS; css/js вставляются
в shell как есть — без экранирования скобок.
"""

CSS: str = """@media(min-width:1024px){
.wrap{max-width:1240px;padding:0 24px calc(140px + env(safe-area-inset-bottom))}
.hero{margin:0 calc(50% - 50vw);height:340px}
body[data-hero=minimal] .hero{margin:0}
.hero .head{left:50%;right:auto;transform:translateX(-50%);width:min(1240px,100%);bottom:28px;padding:0 24px}
body[data-hero=minimal] .hero .head{left:auto;right:auto;transform:none;width:auto;bottom:auto;padding:0 2px}
.hero .logo{width:84px;height:84px;border-radius:22px}
.hero h1{font-size:40px}
.hero .desc{font-size:15.5px;-webkit-line-clamp:3;max-width:680px}
.meta{padding:16px 2px 8px;font-size:14px;gap:18px}
.msearch{margin:14px 0 4px;max-width:460px}
#msw{margin-left:262px}
#app.flat #msw{margin-left:0}
#menu{display:grid;grid-template-columns:230px minmax(0,1fr);gap:0 32px;align-items:start;margin-top:10px}
#menu>:not(.tabs){grid-column:2}
#app.flat #menu{display:block}
.tabs{grid-column:1;grid-row:1;position:sticky;top:24px;z-index:5;flex-direction:column;align-items:stretch;gap:4px;padding:0;background:none;overflow-x:visible;overflow-y:auto;max-height:calc(100vh - 40px);scrollbar-width:thin}
#app.flat .tabs{display:none}
.tabs button{text-align:left;border:0;border-radius:12px;background:transparent;padding:11px 14px}
.tabs button:hover{color:var(--text);background:color-mix(in srgb,var(--text) 6%,transparent)}
.tabs button.on{background:color-mix(in srgb,var(--accent) 15%,transparent);color:var(--afg);font-weight:650}
.cat{font-size:24px;margin:34px 0 10px}
.cat.sub{font-size:18px}
#mbody>.mchunk:first-child>.cat{margin-top:0}
body[data-preset=menu] .mchunk,body[data-preset=compact] .mchunk{display:grid;grid-template-columns:1fr 1fr;column-gap:40px}
body[data-preset=menu] .mchunk>.cat,body[data-preset=compact] .mchunk>.cat{grid-column:1/-1}
body[data-preset=grid] .grid{grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:18px}
.gcard{transition:transform .15s ease,border-color .15s ease,box-shadow .15s ease}
.gcard:hover{transform:translateY(-2px);border-color:color-mix(in srgb,var(--accent) 45%,var(--line));box-shadow:var(--shadow-lg)}
.item{border-radius:12px;padding-left:12px;padding-right:12px;margin-left:-12px;margin-right:-12px;transition:background .15s ease}
body[data-preset=compact] .item{padding-left:12px;padding-right:12px}
.item:hover{background:color-mix(in srgb,var(--text) 4%,transparent)}
.cart{left:auto;right:32px;transform:none;width:min(360px,30vw);bottom:28px}
.cart.show{animation:cartIn .25s ease}
.cart.pop{animation:cartPop .28s ease}
@keyframes cartIn{from{transform:translateY(16px);opacity:0}}
@keyframes cartPop{0%{transform:scale(1)}40%{transform:scale(1.05)}100%{transform:scale(1)}}
.grab{display:none}
#sheet .panel{left:auto;right:0;top:0;bottom:0;transform:none;width:min(470px,94vw);height:100%;max-height:none;border-radius:0;padding:18px 24px calc(28px + env(safe-area-inset-bottom));display:flex;flex-direction:column;animation:drawerIn .24s ease}
#sheet .panel #panel{display:flex;flex-direction:column;flex:1}
#sheet .panel .big{margin-top:auto}
@keyframes drawerIn{from{transform:translateX(56px);opacity:.5}}
#csheet.show{display:grid;place-items:center}
#csheet .panel{position:relative;inset:auto;transform:none;width:min(620px,94vw);max-height:88vh;border-radius:26px;padding:18px 24px 30px;animation:zoomIn .2s ease}
@keyframes zoomIn{from{transform:scale(.95) translateY(14px);opacity:0}}
.toast{bottom:44px}
.bnrs{gap:14px}
.bnr{width:340px}
.shcard{width:176px}
.sh.hero .shcard{width:min(400px,52vw)}
}
@media(min-width:721px) and (max-width:1023px){
.wrap{max-width:920px;padding:0 24px calc(150px + env(safe-area-inset-bottom))}
.hero{height:300px}
.hero h1{font-size:36px}
body[data-hero=cover] .hero{height:340px}
.grid{grid-template-columns:repeat(auto-fill,minmax(210px,1fr))}
.bnr{width:330px}
.shcard{width:168px}
.sh.hero .shcard{width:min(360px,60vw)}
.tabs{top:calc(env(safe-area-inset-top) + 4px)}
.panel{width:min(640px,100vw)}
}
@media(max-width:520px){.hero{height:210px}body[data-hero=cover] .hero{height:250px}.hero h1{font-size:26px}.grid{grid-template-columns:1fr 1fr;gap:10px}}"""
