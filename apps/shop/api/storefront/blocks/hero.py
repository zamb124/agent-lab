"""Шапка витрины: обложка, логотип, название, описание, мета-строка.

Блок собирается реестром STOREFRONT_BLOCKS; css/js вставляются
в shell как есть — без экранирования скобок.
"""

CSS: str = """.hero{position:relative;margin:0 -16px;height:260px;overflow:hidden;background:linear-gradient(160deg,var(--accent) 0%,color-mix(in srgb,var(--accent) 42%,#171310) 52%,#171310 100%)}
.hero .bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.9}
.hero .veil{position:absolute;inset:0;background:linear-gradient(180deg,rgba(16,14,12,.15) 20%,rgba(16,14,12,.92) 100%)}
.hero .head{position:absolute;left:24px;right:24px;bottom:18px;display:flex;align-items:flex-end;gap:14px}
.hero .logo{width:64px;height:64px;border-radius:18px;object-fit:cover;border:2px solid rgba(255,255,255,.4);background:var(--card);flex-shrink:0;box-shadow:0 4px 18px rgba(0,0,0,.35)}
.hero h1{font-size:32px;font-weight:650;letter-spacing:-.01em;color:var(--on-hero);text-shadow:0 2px 18px rgba(0,0,0,.7)}
.hero .desc{font-size:14px;color:color-mix(in srgb,var(--on-hero) 86%,transparent);margin-top:4px;text-shadow:0 1px 8px rgba(0,0,0,.7);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.meta{padding:14px 2px 6px;color:var(--muted);font-size:13.5px;display:flex;gap:14px;flex-wrap:wrap}
.meta span{display:inline-flex;align-items:center;gap:6px}
.meta svg{width:15px;height:15px;fill:currentColor;flex-shrink:0;opacity:.85}
.meta .rate{color:var(--afg,var(--accent));font-weight:650;cursor:pointer}
.ob-open,.ob-closed{font-weight:650}
.ob-open{color:var(--success)}
.ob-closed{color:var(--warn)}
body[data-hero=minimal] .hero{height:auto;background:none;margin:0;padding:20px 0 2px}
body[data-hero=minimal] .hero .bg,body[data-hero=minimal] .hero .veil{display:none}
body[data-hero=minimal] .hero .head{position:static;padding:0 2px}
body[data-hero=minimal] .hero h1{color:var(--text);text-shadow:none;font-size:26px}
body[data-hero=minimal] .hero .desc{color:var(--muted);text-shadow:none}
body[data-hero=minimal] .hero .logo{border-color:var(--line);box-shadow:var(--shadow-sm)}
body[data-hero=cover] .hero{height:320px}
body[data-hero=cover] .hero .veil{background:linear-gradient(180deg,rgba(16,14,12,.04) 30%,rgba(16,14,12,.94) 100%)}"""
