"""Figma Screens — генерация экранов сервисов на странице «📱 Экраны».

Спеки экранов (блоки DSL) 1:1 по маршрутам UI: каждый экран — фрейм 1440
с инстансом Shell/Sidebar + контент из блоков (stats/table/list/cards/
form/kanban/chat/detail/editor/map/split). Зона сервиса пересобирается
целиком — идемпотентно, экраны других сервисов не трогаются.

``uv run python -m scripts.tools.figma_screens <service>|all``
"""

from __future__ import annotations

import argparse
import json
import sys

from scripts.tools.figma_tokens import (
    Json,
    _figma_exec,
    _project_file_key,
    _require_design_file,
    _Server,
    extract,
)
from scripts.tools.figma_uikit import _HELPERS_JS

_RENDER_JS = _HELPERS_JS + r"""
const W = 1440, MW = 390, SIDE = 280, PAD = 32, MPAD = 16;
function frameBox(w, h, pad, dir, gap) {
  const f = figma.createFrame();
  f.layoutMode = dir || 'VERTICAL';
  f.itemSpacing = gap == null ? 12 : gap;
  f.paddingLeft = f.paddingRight = f.paddingTop = f.paddingBottom = pad == null ? 0 : pad;
  f.primaryAxisSizingMode = 'FIXED'; f.counterAxisSizingMode = 'FIXED';
  f.resize(w, h);
  f.fills = [];
  return f;
}
function glassBox(w, h, radius) {
  const f = frameBox(w, h, 0);
  boundFill(f, 'glass/tint/subtle', { r: 1, g: 1, b: 1, a: 0.03 });
  boundStroke(f, 'glass/border/subtle');
  f.cornerRadius = radius || 16;
  f.clipsContent = true;
  return f;
}
function bar(w, h, color, radius) {
  const r = figma.createRectangle();
  r.resize(w, h); r.cornerRadius = radius == null ? h / 2 : radius;
  boundFill(r, color || 'glass/tint/strong', { r: 1, g: 1, b: 1, a: 0.08 });
  return r;
}
function btn(label, primary) {
  const b = frameBox(0, 0, 0, 'HORIZONTAL', 8);
  b.primaryAxisSizingMode = 'AUTO'; b.counterAxisSizingMode = 'AUTO';
  b.counterAxisAlignItems = 'CENTER'; b.primaryAxisAlignItems = 'CENTER';
  b.paddingLeft = b.paddingRight = 20; b.paddingTop = b.paddingBottom = 9;
  b.cornerRadius = 22;
  if (primary) boundFill(b, 'platform/btn/primary/bg', { r: 0.6, g: 0.65, b: 0.98 });
  else { boundFill(b, 'platform/btn/secondary/bg', { r: 0.6, g: 0.65, b: 0.98, a: 0.15 }); }
  b.appendChild(txt(label, FONT_R, 14, primary ? 'platform/btn/primary/text' : 'accent'));
  return b;
}
function field(label, w) {
  const f = frameBox(w || 360, 0, 0, 'VERTICAL', 4);
  f.counterAxisSizingMode = 'AUTO';
  f.paddingLeft = f.paddingRight = 16; f.paddingTop = f.paddingBottom = 12;
  f.cornerRadius = 18;
  boundFill(f, 'field/pill/bg', { r: 1, g: 1, b: 1, a: 0.05 });
  boundStroke(f, 'field/pill/border');
  f.appendChild(txt(label.toUpperCase(), FONT_M, 10, 'field/pill/label/color'));
  f.appendChild(txt('…', FONT_M, 15, 'field/pill/input/color'));
  return f;
}
function avatar(size, initials, grad) {
  const a = figma.createFrame();
  a.resize(size, size); a.cornerRadius = size / 2;
  a.layoutMode = 'HORIZONTAL'; a.primaryAxisAlignItems = 'CENTER'; a.counterAxisAlignItems = 'CENTER';
  if (grad) a.fills = [{ type: 'GRADIENT_LINEAR', gradientTransform: [[1, -1, 0.5], [1, 1, 0.5]], gradientStops: [{ color: { r: 0.6, g: 0.65, b: 0.98, a: 1 }, position: 0 }, { color: { r: 0.55, g: 0.36, b: 0.96, a: 1 }, position: 1 }] }];
  else boundFill(a, 'glass/tint/strong', { r: 1, g: 1, b: 1, a: 0.08 });
  a.appendChild(txt(initials || '·', FONT_M, Math.round(size * 0.38), grad ? 'platform/btn/primary/text' : 'text/secondary'));
  return a;
}
function badge(label, colorName) {
  const b = frameBox(0, 0, 0, 'HORIZONTAL', 0);
  b.primaryAxisSizingMode = 'AUTO'; b.counterAxisSizingMode = 'AUTO';
  b.paddingLeft = b.paddingRight = 9; b.paddingTop = b.paddingBottom = 3;
  b.cornerRadius = 99;
  boundFill(b, colorName + '/bg', { r: 0.06, g: 0.72, b: 0.5, a: 0.15 });
  b.appendChild(txt(label, FONT_M, 10, colorName));
  return b;
}
// ---- blocks ----
const blocks = {
  stats(b, parent) {
    const roww = frameBox(b.w, 0, 0, 'HORIZONTAL', 16);
    roww.counterAxisSizingMode = 'AUTO';
    const n = b.items.length;
    for (const it of b.items) {
      const card = glassBox(0, 96, 16);
      card.counterAxisSizingMode = 'AUTO'; card.primaryAxisSizingMode = 'AUTO';
      card.layoutGrow = 1;
      card.paddingLeft = card.paddingRight = 20; card.paddingTop = card.paddingBottom = 16;
      card.layoutMode = 'VERTICAL'; card.itemSpacing = 6;
      card.appendChild(txt(it[0], FONT_R, 12, 'text/secondary'));
      card.appendChild(txt(it[1], FONT_S, 24, 'text/primary'));
      if (it[2]) card.appendChild(txt(it[2], FONT_M, 11, String(it[2]).startsWith('+') ? 'success' : 'text/tertiary'));
      roww.appendChild(card);
    }
    parent.appendChild(roww);
  },
  toolbar(b, parent) {
    const roww = frameBox(b.w, 0, 0, 'HORIZONTAL', 10);
    roww.counterAxisSizingMode = 'AUTO'; roww.counterAxisAlignItems = 'CENTER';
    const search = field(b.search || 'Поиск…', 300);
    search.layoutMode = 'HORIZONTAL'; search.counterAxisAlignItems = 'CENTER';
    search.children[0].remove();
    roww.appendChild(search);
    for (const f of b.filters || []) roww.appendChild(badge(f + ' ▾', 'info'));
    const sp = frameBox(0, 10, 0); sp.layoutGrow = 1; roww.appendChild(sp);
    for (const a of b.actions || []) roww.appendChild(btn(a[0], a[1]));
    parent.appendChild(roww);
  },
  table(b, parent) {
    const t = glassBox(b.w, 0, 14);
    t.primaryAxisSizingMode = 'AUTO'; t.layoutMode = 'VERTICAL'; t.itemSpacing = 0;
    const widths = b.widths || b.cols.map(() => Math.floor((b.w - 32) / b.cols.length));
    const mkRow = (cells, head) => {
      const r = frameBox(b.w, 0, 0, 'HORIZONTAL', 0);
      r.counterAxisSizingMode = 'AUTO'; r.counterAxisAlignItems = 'CENTER';
      r.paddingLeft = r.paddingRight = 16; r.paddingTop = r.paddingBottom = head ? 13 : 14;
      if (head) boundFill(r, 'glass/tint/subtle', { r: 1, g: 1, b: 1, a: 0.03 });
      else r.strokes = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1, a: 0.06 } }], r.strokeWeight = 1;
      cells.forEach((cs, i) => {
        const cell = frameBox(widths[i] || 120, 18, 0, 'HORIZONTAL', 0);
        cell.counterAxisAlignItems = 'CENTER';
        if (typeof cs === 'object' && cs.badge) cell.appendChild(badge(cs.badge, cs.color || 'info'));
        else cell.appendChild(txt(String(cs), head ? FONT_M : FONT_R, head ? 11 : 13, head ? 'text/tertiary' : 'text/secondary'));
        r.appendChild(cell);
      });
      return r;
    };
    t.appendChild(mkRow(b.cols, true));
    for (const rw of b.rows) t.appendChild(mkRow(rw, false));
    parent.appendChild(t);
  },
  list(b, parent) {
    const w = frameBox(b.w, 0, 0, 'VERTICAL', 8);
    w.primaryAxisSizingMode = 'AUTO';
    for (const it of b.items) {
      const r = frameBox(b.w, 0, 0, 'HORIZONTAL', 12);
      r.counterAxisSizingMode = 'AUTO'; r.counterAxisAlignItems = 'CENTER';
      r.paddingLeft = r.paddingRight = 14; r.paddingTop = r.paddingBottom = 11;
      r.cornerRadius = 12;
      boundFill(r, 'glass/tint/subtle', { r: 1, g: 1, b: 1, a: 0.03 });
      if (it.icon === false) {} else r.appendChild(avatar(34, it.icon || '◆', it.grad));
      const tx = frameBox(0, 0, 0, 'VERTICAL', 3);
      tx.primaryAxisSizingMode = 'AUTO'; tx.counterAxisSizingMode = 'AUTO'; tx.layoutGrow = 1;
      tx.appendChild(txt(it.title, FONT_M, 14, 'text/primary'));
      if (it.sub) tx.appendChild(txt(it.sub, FONT_R, 12, 'text/tertiary'));
      r.appendChild(tx);
      if (it.badge) r.appendChild(badge(it.badge, it.badgeColor || 'info'));
      r.appendChild(txt('›', FONT_R, 16, 'text/tertiary'));
      w.appendChild(r);
    }
    parent.appendChild(w);
  },
  cards(b, parent) {
    const roww = frameBox(b.w, 0, 0, 'HORIZONTAL', 16);
    roww.layoutWrap = 'WRAP'; roww.counterAxisSpacing = 16;
    roww.counterAxisSizingMode = 'AUTO';
    const cw = Math.floor((b.w - 16 * ((b.cols || 3) - 1)) / (b.cols || 3));
    for (const it of b.items) {
      const card = glassBox(cw, it.h || 150, 16);
      card.layoutMode = 'VERTICAL'; card.itemSpacing = 8;
      card.paddingLeft = card.paddingRight = card.paddingTop = card.paddingBottom = 18;
      if (it.icon) card.appendChild(avatar(36, it.icon, it.grad));
      card.appendChild(txt(it.title, FONT_M, 15, 'text/primary'));
      if (it.sub) card.appendChild(txt(it.sub, FONT_R, 12, 'text/secondary'));
      if (it.badge) card.appendChild(badge(it.badge, it.badgeColor || 'info'));
      roww.appendChild(card);
    }
    parent.appendChild(roww);
  },
  form(b, parent) {
    const card = glassBox(b.narrow ? 520 : b.w, 0, 18);
    card.primaryAxisSizingMode = 'AUTO';
    card.layoutMode = 'VERTICAL'; card.itemSpacing = 14;
    card.paddingLeft = card.paddingRight = card.paddingTop = card.paddingBottom = 24;
    if (b.title) card.appendChild(txt(b.title, FONT_S, 17, 'text/primary'));
    for (const f of b.fields) card.appendChild(field(f, 0));
    for (const c of card.children) if (c.layoutMode) c.layoutAlign = 'STRETCH';
    const foot = frameBox(0, 0, 0, 'HORIZONTAL', 10);
    foot.counterAxisSizingMode = 'AUTO'; foot.primaryAxisAlignItems = 'MAX';
    foot.appendChild(btn(b.cancel || 'Отмена', false));
    foot.appendChild(btn(b.submit || 'Сохранить', true));
    card.appendChild(foot);
    parent.appendChild(card);
  },
  kanban(b, parent) {
    const roww = frameBox(b.w, 0, 0, 'HORIZONTAL', 16);
    roww.counterAxisSizingMode = 'AUTO'; roww.counterAxisAlignItems = 'MIN';
    const cw = Math.floor((b.w - 32) / b.cols.length);
    for (const colDef of b.cols) {
      const c = glassBox(cw, 0, 14);
      c.primaryAxisSizingMode = 'AUTO';
      c.layoutMode = 'VERTICAL'; c.itemSpacing = 10;
      c.paddingLeft = c.paddingRight = c.paddingTop = c.paddingBottom = 14;
      const head = frameBox(cw - 28, 0, 0, 'HORIZONTAL', 8);
      head.counterAxisSizingMode = 'AUTO'; head.counterAxisAlignItems = 'CENTER';
      head.appendChild(txt(colDef.title, FONT_S, 13, 'text/secondary'));
      head.appendChild(badge(String(colDef.cards.length), 'info'));
      c.appendChild(head);
      for (const cd of colDef.cards) {
        const k = glassBox(cw - 28, 0, 12);
        k.primaryAxisSizingMode = 'AUTO';
        k.layoutMode = 'VERTICAL'; k.itemSpacing = 6;
        k.paddingLeft = k.paddingRight = k.paddingTop = k.paddingBottom = 12;
        k.appendChild(txt(cd[0], FONT_M, 13, 'text/primary'));
        if (cd[1]) k.appendChild(txt(cd[1], FONT_R, 11, 'text/tertiary'));
        c.appendChild(k);
      }
      roww.appendChild(c);
    }
    parent.appendChild(roww);
  },
  chat(b, parent) {
    const w = frameBox(b.w, 0, 0, 'VERTICAL', 12);
    w.primaryAxisSizingMode = 'AUTO';
    for (const m of b.msgs) {
      const mine = m.mine;
      const r = frameBox(b.w, 0, 0, 'HORIZONTAL', 10);
      r.counterAxisSizingMode = 'AUTO'; r.counterAxisAlignItems = 'MIN';
      if (mine) r.primaryAxisAlignItems = 'MAX';
      if (!mine) r.appendChild(avatar(32, m.who || '·', false));
      const bub = frameBox(Math.min(b.w * 0.6, 560), 0, 0, 'VERTICAL', 4);
      bub.primaryAxisSizingMode = 'AUTO';
      bub.paddingLeft = bub.paddingRight = 14; bub.paddingTop = bub.paddingBottom = 10;
      bub.cornerRadius = 12;
      boundFill(bub, mine ? 'accent/subtle' : 'glass/tint/medium', { r: 1, g: 1, b: 1, a: 0.05 });
      bub.appendChild(txt(m.text, FONT_R, 13, 'text/primary'));
      if (m.time) bub.appendChild(txt(m.time, FONT_R, 10, 'text/tertiary'));
      r.appendChild(bub);
      w.appendChild(r);
    }
    const comp = frameBox(b.w, 48, 0, 'HORIZONTAL', 10);
    comp.counterAxisAlignItems = 'CENTER'; comp.cornerRadius = 24;
    boundFill(comp, 'glass/solid/subtle', { r: 0.11, g: 0.11, b: 0.18, a: 0.75 });
    boundStroke(comp, 'glass/border/subtle');
    comp.paddingLeft = 18; comp.paddingRight = 10;
    comp.appendChild(txt('Сообщение…', FONT_R, 13, 'text/tertiary'));
    const sp = frameBox(0, 10, 0); sp.layoutGrow = 1; comp.appendChild(sp);
    const send = frameBox(34, 34, 0, 'HORIZONTAL', 0);
    send.cornerRadius = 17; boundFill(send, 'platform/btn/primary/bg', { r: 0.6, g: 0.65, b: 0.98 });
    send.primaryAxisAlignItems = 'CENTER'; send.counterAxisAlignItems = 'CENTER';
    send.appendChild(txt('↑', FONT_M, 15, 'platform/btn/primary/text'));
    comp.appendChild(send);
    w.appendChild(comp);
    parent.appendChild(w);
  },
  detail(b, parent) {
    const roww = frameBox(b.w, 0, 0, 'HORIZONTAL', 20);
    roww.counterAxisSizingMode = 'AUTO'; roww.counterAxisAlignItems = 'MIN';
    const main = frameBox(0, 0, 0, 'VERTICAL', 14);
    main.primaryAxisSizingMode = 'AUTO'; main.counterAxisSizingMode = 'AUTO'; main.layoutGrow = 1;
    const hd = frameBox(0, 0, 0, 'HORIZONTAL', 12);
    hd.counterAxisSizingMode = 'AUTO'; hd.counterAxisAlignItems = 'CENTER';
    hd.appendChild(txt(b.title, FONT_S, 20, 'text/primary'));
    if (b.badge) hd.appendChild(badge(b.badge, b.badgeColor || 'success'));
    const sp = frameBox(0, 10, 0); sp.layoutGrow = 1; hd.appendChild(sp);
    for (const a of b.actions || []) hd.appendChild(btn(a[0], a[1]));
    main.appendChild(hd);
    for (const kv of b.rows || []) {
      const kr = frameBox(0, 0, 0, 'HORIZONTAL', 0);
      kr.counterAxisSizingMode = 'AUTO';
      kr.paddingTop = kr.paddingBottom = 8;
      kr.strokes = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1, a: 0.06 } }]; kr.strokeWeight = 1;
      const k = frameBox(220, 18, 0); k.appendChild(txt(kv[0], FONT_R, 13, 'text/tertiary'));
      const v = frameBox(0, 18, 0); v.layoutGrow = 1; v.appendChild(txt(kv[1], FONT_M, 13, 'text/secondary'));
      kr.appendChild(k); kr.appendChild(v);
      main.appendChild(kr);
    }
    roww.appendChild(main);
    if (b.side) {
      const side = glassBox(300, 0, 14);
      side.primaryAxisSizingMode = 'AUTO';
      side.layoutMode = 'VERTICAL'; side.itemSpacing = 10;
      side.paddingLeft = side.paddingRight = side.paddingTop = side.paddingBottom = 16;
      side.appendChild(txt(b.side[0], FONT_S, 13, 'text/secondary'));
      for (const s of b.side[1]) side.appendChild(txt(s, FONT_R, 12, 'text/tertiary'));
      roww.appendChild(side);
    }
    parent.appendChild(roww);
  },
  editor(b, parent) {
    const canvas = figma.createFrame();
    canvas.resize(b.w, b.h || 460);
    boundFill(canvas, 'bg/secondary', { r: 0.07, g: 0.07, b: 0.14 });
    canvas.cornerRadius = 16; canvas.clipsContent = true;
    boundStroke(canvas, 'glass/border/subtle');
    const nodes = b.nodes || [['Триггер', 80, 60], ['LLM: агент', 360, 140], ['Условие', 640, 60], ['HTTP', 640, 240], ['Ответ', 920, 140]];
    const links = b.links || [[0, 1], [1, 2], [2, 3], [1, 4]];
    const pos = [];
    for (const nd of nodes) {
      const card = glassBox(180, 64, 12);
      card.layoutMode = 'VERTICAL'; card.itemSpacing = 4;
      card.paddingLeft = card.paddingRight = 14; card.paddingTop = card.paddingBottom = 10;
      card.appendChild(txt(nd[0], FONT_M, 13, 'text/primary'));
      card.appendChild(txt(nd[3] || 'нода', FONT_R, 10, 'accent'));
      canvas.appendChild(card);
      card.x = nd[1]; card.y = nd[2];
      pos.push([nd[1] + 90, nd[2] + 32]);
    }
    for (const lk of links) {
      const [x1, y1] = pos[lk[0]], [x2, y2] = pos[lk[1]];
      const line = figma.createVector();
      line.vectorPaths = [{ windingRule: 'NONE', data: `M ${x1} ${y1} C ${x1 + 60} ${y1} ${x2 - 60} ${y2} ${x2} ${y2}` }];
      line.strokes = [{ type: 'SOLID', color: { r: 0.6, g: 0.65, b: 0.98 }, opacity: 0.6 }];
      line.strokeWeight = 2; line.fills = [];
      canvas.appendChild(line);
    }
    parent.appendChild(canvas);
  },
  map(b, parent) {
    const m = figma.createFrame();
    m.resize(b.w, b.h || 420);
    boundFill(m, 'bg/secondary', { r: 0.06, g: 0.09, b: 0.16 });
    m.cornerRadius = 16; m.clipsContent = true;
    boundStroke(m, 'glass/border/subtle');
    for (let i = 0; i < 40; i++) {
      const dot = figma.createEllipse();
      dot.resize(3, 3);
      boundFill(dot, 'glass/tint/strong', { r: 1, g: 1, b: 1, a: 0.12 });
      m.appendChild(dot);
      dot.x = 30 + (i * 97) % (b.w - 60); dot.y = 20 + (i * 61) % ((b.h || 420) - 40);
    }
    const path = figma.createVector();
    path.vectorPaths = [{ windingRule: 'NONE', data: `M 120 ${(b.h || 420) - 100} C ${b.w * 0.3} ${(b.h || 420) * 0.4} ${b.w * 0.6} ${(b.h || 420) * 0.6} ${b.w - 160} 120` }];
    path.strokes = [{ type: 'SOLID', color: { r: 0.6, g: 0.65, b: 0.98 } }];
    path.strokeWeight = 3; path.dashPattern = [8, 6]; path.fills = [];
    m.appendChild(path);
    for (const [px, py, lbl, colr] of b.pins || [[120, (b.h || 420) - 100, 'A', 'accent'], [b.w - 160, 120, 'B', 'accent/secondary']]) {
      const pin = figma.createFrame(); pin.resize(30, 30); pin.cornerRadius = 15;
      boundFill(pin, colr, { r: 0.6, g: 0.65, b: 0.98 });
      pin.layoutMode = 'HORIZONTAL'; pin.primaryAxisAlignItems = 'CENTER'; pin.counterAxisAlignItems = 'CENTER';
      pin.appendChild(txt(lbl, FONT_B, 13, 'platform/btn/primary/text'));
      m.appendChild(pin); pin.x = px - 15; pin.y = py - 15;
    }
    parent.appendChild(m);
  },
  split(b, parent) {
    const roww = frameBox(b.w, b.h || 480, 0, 'HORIZONTAL', 0);
    const left = glassBox(Math.round(b.w * 0.34), b.h || 480, 14);
    left.layoutMode = 'VERTICAL'; left.itemSpacing = 0; left.clipsContent = true;
    for (const it of b.items) {
      const r = frameBox(Math.round(b.w * 0.34), 0, 0, 'VERTICAL', 3);
      r.primaryAxisSizingMode = 'AUTO';
      r.paddingLeft = r.paddingRight = 14; r.paddingTop = r.paddingBottom = 12;
      if (it.active) boundFill(r, 'accent/subtle', { r: 0.6, g: 0.65, b: 0.98, a: 0.16 });
      else r.strokes = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1, a: 0.05 } }], r.strokeWeight = 1;
      r.appendChild(txt(it.title, FONT_M, 13, it.active ? 'accent' : 'text/primary'));
      if (it.sub) r.appendChild(txt(it.sub, FONT_R, 11, 'text/tertiary'));
      left.appendChild(r);
    }
    roww.appendChild(left);
    const right = frameBox(0, b.h || 480, 20, 'VERTICAL', 12);
    right.layoutGrow = 1; right.layoutAlign = 'STRETCH';
    right.appendChild(txt(b.detail || 'Выберите элемент слева', FONT_S, 16, 'text/primary'));
    for (const ln of b.lines || []) right.appendChild(txt(ln, FONT_R, 13, 'text/secondary'));
    roww.appendChild(right);
    parent.appendChild(roww);
  },
  hero(b, parent) {
    const w = frameBox(b.w, 0, 0, 'VERTICAL', 16);
    w.primaryAxisSizingMode = 'AUTO'; w.counterAxisAlignItems = 'CENTER';
    w.paddingTop = w.paddingBottom = 48;
    if (b.kicker) w.appendChild(txt(b.kicker, FONT_M, 13, 'accent'));
    w.appendChild(txt(b.title, FONT_B, 44, 'text/primary'));
    if (b.sub) { const s = txt(b.sub, FONT_R, 17, 'text/secondary'); s.textAlignHorizontal = 'CENTER'; s.resize(b.w * 0.7, 40); w.appendChild(s); }
    const cta = frameBox(0, 0, 0, 'HORIZONTAL', 12);
    cta.counterAxisSizingMode = 'AUTO';
    for (const a of b.actions || [['Начать', true], ['Подробнее', false]]) cta.appendChild(btn(a[0], a[1]));
    w.appendChild(cta);
    parent.appendChild(w);
  },
  fields(b, parent) {
    for (const f of b.items) {
      const fl = field(f, 0);
      fl.layoutAlign = 'STRETCH';
      parent.appendChild(fl);
    }
    if (b.checks) for (const c of b.checks) {
      const roww = frameBox(0, 0, 0, 'HORIZONTAL', 8);
      roww.counterAxisSizingMode = 'AUTO'; roww.counterAxisAlignItems = 'CENTER';
      const cb = frameBox(16, 16, 0, 'HORIZONTAL', 0);
      cb.cornerRadius = 5;
      boundFill(cb, c[1] ? 'platform/btn/primary/bg' : 'field/pill/bg', { r: 0.6, g: 0.65, b: 0.98 });
      boundStroke(cb, 'field/pill/border');
      cb.primaryAxisAlignItems = 'CENTER'; cb.counterAxisAlignItems = 'CENTER';
      if (c[1]) cb.appendChild(txt('✓', FONT_B, 10, 'platform/btn/primary/text'));
      roww.appendChild(cb);
      roww.appendChild(txt(c[0], FONT_R, 12, 'text/secondary'));
      parent.appendChild(roww);
    }
    const foot = frameBox(0, 0, 0, 'HORIZONTAL', 10);
    foot.counterAxisSizingMode = 'AUTO'; foot.primaryAxisAlignItems = 'MAX';
    foot.appendChild(btn(b.cancel || 'Отмена', false));
    foot.appendChild(btn(b.submit || 'Сохранить', true));
    parent.appendChild(foot);
    foot.layoutAlign = 'STRETCH';
  },
  state(b, parent) {
    const w = frameBox(b.w, 0, 0, 'VERTICAL', 12);
    w.primaryAxisSizingMode = 'AUTO'; w.counterAxisAlignItems = 'CENTER';
    w.paddingTop = w.paddingBottom = 56;
    const ic = avatar(64, b.icon || '◌', false);
    ic.children[0].fontSize = 26;
    w.appendChild(ic);
    w.appendChild(txt(b.title, FONT_S, 18, 'text/primary'));
    if (b.sub) {
      const s = txt(b.sub, FONT_R, 13, 'text/tertiary');
      s.textAlignHorizontal = 'CENTER';
      w.appendChild(s);
    }
    if (b.action) w.appendChild(btn(b.action, true));
    parent.appendChild(w);
  },
  skeleton(b, parent) {
    const w = frameBox(b.w, 0, 0, 'VERTICAL', 14);
    w.primaryAxisSizingMode = 'AUTO';
    for (let i = 0; i < (b.n || 5); i++) {
      const r = frameBox(b.w, 0, 0, 'HORIZONTAL', 12);
      r.counterAxisSizingMode = 'AUTO'; r.counterAxisAlignItems = 'CENTER';
      const sq = frameBox(36, 36, 0);
      sq.cornerRadius = 10;
      boundFill(sq, 'glass/tint/medium', { r: 1, g: 1, b: 1, a: 0.06 });
      r.appendChild(sq);
      const colw = [0.5, 0.7, 0.35, 0.6][i % 4];
      const b1 = bar(Math.round(b.w * colw), 12);
      r.appendChild(b1);
      const b2 = bar(Math.round(b.w * (colw * 0.55)), 9);
      const sp = frameBox(0, 10, 0); sp.layoutGrow = 1; r.appendChild(sp);
      r.appendChild(b2);
      w.appendChild(r);
    }
    parent.appendChild(w);
  },
  text(b, parent) {
    for (const ln of b.lines) parent.appendChild(txt(ln, FONT_R, 13, 'text/secondary'));
  },
  gallery(b, parent) {
    const roww = frameBox(b.w, 0, 0, 'HORIZONTAL', 14);
    roww.layoutWrap = 'WRAP'; roww.counterAxisSpacing = 14; roww.counterAxisSizingMode = 'AUTO';
    const cw = Math.floor((b.w - 14 * ((b.cols || 4) - 1)) / (b.cols || 4));
    for (let i = 0; i < (b.n || 8); i++) {
      const c = glassBox(cw, b.h || 140, 14);
      c.layoutMode = 'VERTICAL'; c.itemSpacing = 6;
      c.paddingLeft = c.paddingRight = c.paddingTop = c.paddingBottom = 14;
      const img = frameBox(cw - 28, (b.h || 140) - 80, 0);
      img.cornerRadius = 10;
      boundFill(img, 'accent/subtle', { r: 0.6, g: 0.65, b: 0.98, a: 0.12 });
      img.layoutMode = 'HORIZONTAL'; img.primaryAxisAlignItems = 'CENTER'; img.counterAxisAlignItems = 'CENTER';
      img.appendChild(txt('◧', FONT_R, 22, 'accent'));
      c.appendChild(img);
      c.appendChild(txt((b.items && b.items[i]) || 'Документ ' + (i + 1), FONT_M, 12, 'text/primary'));
      c.appendChild(txt('обновлён недавно', FONT_R, 10, 'text/tertiary'));
      roww.appendChild(c);
    }
    parent.appendChild(roww);
  },
};
try {
let sidebarComp = null;
await figma.loadAllPagesAsync();
for (const p of figma.root.children) {
  const c = p.findOne(n => n.name === 'Shell/Sidebar' && n.type === 'COMPONENT');
  if (c) { sidebarComp = c; break; }
}
if (spec.journeys) {
  for (const j of spec.journeys) {
    const lane = frameBox(0, 0, 0, 'VERTICAL', 14);
    lane.primaryAxisSizingMode = 'AUTO'; lane.counterAxisSizingMode = 'AUTO';
    lane.appendChild(txt(j.name, FONT_S, 18, 'text/primary'));
    const row = frameBox(0, 0, 0, 'HORIZONTAL', 40);
    row.primaryAxisSizingMode = 'AUTO'; row.counterAxisSizingMode = 'AUTO';
    row.counterAxisAlignItems = 'CENTER';
    j.steps.forEach((st, i) => {
      const chip = glassBox(200, 64, 12);
      chip.layoutMode = 'VERTICAL'; chip.itemSpacing = 4;
      chip.paddingLeft = chip.paddingRight = 14; chip.paddingTop = chip.paddingBottom = 11;
      chip.appendChild(txt(st[0], FONT_M, 10, 'accent'));
      chip.appendChild(txt(st[1], FONT_M, 13, 'text/primary'));
      row.appendChild(chip);
      if (i < j.steps.length - 1) {
        const arrow = figma.createVector();
        arrow.vectorPaths = [{ windingRule: 'NONE', data: 'M 0 10 L 30 10 M 23 4 L 31 10 L 23 16' }];
        arrow.strokes = [{ type: 'SOLID', color: { r: 0.6, g: 0.65, b: 0.98 }, opacity: 0.8 }];
        arrow.strokeWeight = 2; arrow.fills = [];
        arrow.strokeJoin = 'ROUND';
        row.appendChild(arrow);
      }
    });
    lane.appendChild(row);
    container.appendChild(lane);
  }
  return { journeys: spec.journeys.length };
}
function topBar(title) {
  const tb = frameBox(MW, 56, 0, 'HORIZONTAL', 10);
  tb.counterAxisAlignItems = 'CENTER';
  tb.paddingLeft = tb.paddingRight = 14;
  boundFill(tb, 'glass/solid/subtle', { r: 0.11, g: 0.11, b: 0.18, a: 0.78 });
  boundStroke(tb, 'glass/border/subtle');
  const back = frameBox(32, 32, 0, 'HORIZONTAL', 0);
  back.cornerRadius = 16; back.primaryAxisAlignItems = 'CENTER'; back.counterAxisAlignItems = 'CENTER';
  back.appendChild(txt('‹', FONT_R, 18, 'text/secondary'));
  tb.appendChild(back);
  tb.appendChild(txt(title, FONT_S, 16, 'text/primary'));
  const sp = frameBox(0, 10, 0); sp.layoutGrow = 1; tb.appendChild(sp);
  const bell = frameBox(32, 32, 0, 'HORIZONTAL', 0);
  bell.cornerRadius = 16; bell.primaryAxisAlignItems = 'CENTER'; bell.counterAxisAlignItems = 'CENTER';
  bell.appendChild(txt('🔔', FONT_R, 14, 'text/secondary'));
  tb.appendChild(bell);
  return tb;
}
function bottomNav() {
  const bn = frameBox(MW, 62, 0, 'HORIZONTAL', 0);
  bn.paddingLeft = bn.paddingRight = 12; bn.paddingTop = 8; bn.paddingBottom = 10;
  boundFill(bn, 'glass/solid/subtle', { r: 0.11, g: 0.11, b: 0.18, a: 0.82 });
  boundStroke(bn, 'glass/border/subtle');
  const items = [['⌂', 'Главная', true], ['✉', 'Синк', false], ['◆', 'CRM', false], ['✓', 'Задачи', false], ['⚡', 'Flows', false]];
  for (const it of items) {
    const cell = frameBox(0, 0, 0, 'VERTICAL', 2);
    cell.counterAxisSizingMode = 'AUTO'; cell.layoutGrow = 1;
    cell.counterAxisAlignItems = 'CENTER';
    cell.appendChild(txt(it[0], FONT_R, 17, it[2] ? 'accent' : 'text/tertiary'));
    cell.appendChild(txt(it[1], FONT_M, 9, it[2] ? 'accent' : 'text/tertiary'));
    bn.appendChild(cell);
  }
  return bn;
}
for (const scr of spec.screens || []) {
  const isMobile = !!scr.mobile;
  const isDialog = !!scr.dialog;
  const sw = isMobile ? MW : W;
  const wrap = frameBox(0, 0, 0, 'VERTICAL', 14);
  wrap.primaryAxisSizingMode = 'AUTO'; wrap.counterAxisSizingMode = 'AUTO';
  wrap.appendChild(txt(scr.title + (isMobile ? ' · 390' : ''), FONT_S, isMobile ? 15 : 18, 'text/primary'));
  const sf = frameBox(sw, scr.h || (isMobile ? 844 : 860), 0, 'VERTICAL', 0);
  sf.name = spec.svc + '/' + scr.name + (isMobile ? '@mobile' : '');
  sf.clipsContent = true;
  boundFill(sf, 'bg/primary', { r: 0.086, g: 0.13, b: 0.24 });
  if (isMobile) {
    sf.appendChild(topBar(scr.title));
    const mc = frameBox(MW, 0, MPAD, 'VERTICAL', 16);
    mc.layoutGrow = 1; mc.layoutAlign = 'STRETCH';
    for (const blk of scr.blocks) {
      blk.w = MW - MPAD * 2;
      blocks[blk.t](blk, mc);
    }
    sf.appendChild(mc);
    sf.appendChild(bottomNav());
  } else if (!isDialog) {
    sf.layoutMode = 'HORIZONTAL';
    if (scr.shell !== false && sidebarComp) {
      const inst = sidebarComp.createInstance();
      inst.layoutAlign = 'STRETCH'; inst.layoutGrow = 0;
      sf.appendChild(inst);
    } else if (scr.shell !== false) {
      const sb = frameBox(SIDE, scr.h || 860, 16, 'VERTICAL', 4);
      boundStroke(sb, 'glass/border/subtle');
      sf.appendChild(sb);
    }
    const content = frameBox(scr.shell === false ? W : W - SIDE, scr.h || 860, PAD, 'VERTICAL', 20);
    content.counterAxisAlignItems = 'MIN';
    for (const blk of scr.blocks) {
      blk.w = (scr.shell === false ? W : W - SIDE) - PAD * 2;
      blocks[blk.t](blk, content);
    }
    sf.appendChild(content);
  }
  if (isDialog) {
    sf.layoutMode = 'VERTICAL';
    sf.primaryAxisAlignItems = 'CENTER'; sf.counterAxisAlignItems = 'CENTER';
    sf.fills = [{ type: 'SOLID', color: { r: 0.02, g: 0.02, b: 0.05, a: 0.88 } }];
    const dlg = figma.createFrame();
    dlg.resize(560, 10);
    dlg.fills = [{ type: 'SOLID', color: { r: 0.1, g: 0.1, b: 0.18 } }];
    boundStroke(dlg, 'glass/border/subtle');
    dlg.cornerRadius = 18;
    dlg.layoutMode = 'VERTICAL'; dlg.itemSpacing = 14;
    dlg.primaryAxisSizingMode = 'AUTO'; dlg.counterAxisSizingMode = 'FIXED';
    dlg.paddingLeft = dlg.paddingRight = dlg.paddingTop = dlg.paddingBottom = 24;
    dlg.appendChild(txt(scr.dialogTitle || scr.title, FONT_S, 17, 'text/primary'));
    for (const blk of scr.blocks) {
      blk.w = 512;
      blocks[blk.t](blk, dlg);
    }
    sf.appendChild(dlg);
  }
  wrap.appendChild(sf);
  container.appendChild(wrap);
}
return { screens: spec.screens.length };
} catch (e) {
  return { error: String(e), stack: e.stack ? String(e.stack).slice(0, 1200) : null };
}
"""

SCREENS: dict[str, Json] = {
    "sync": {
        "title": "Синк — чат и звонки",
        "zone": "zone/010 — Sync",
        "screens": [
            {"name": "channel", "title": "Канал — лента сообщений", "blocks": [
                {"t": "split", "h": 760, "items": [
                    {"title": "# general", "sub": "1 240 сообщений", "active": True},
                    {"title": "# flows-алерты", "sub": "98"},
                    {"title": "# команда", "sub": "312"},
                    {"title": "@ Lara", "sub": "агент"},
                    {"title": "@ Поддержка", "sub": "12"},
                ], "detail": "# general", "lines": []},
            ]},
            {"name": "chat", "title": "Диалог — сообщения + composer", "blocks": [
                {"t": "chat", "msgs": [
                    {"who": "АК", "text": "Доброе утро! Отчёт по вчерашнему инциденту готов — смотри в Документах.", "time": "09:12"},
                    {"who": "·", "text": "Lara, собери сводку по алертам за ночь и кинь сюда.", "time": "09:15", "mine": True},
                    {"who": "L", "text": "Готово: 3 инцидента, все закрыты. Детали в треде ↴", "time": "09:15"},
                    {"who": "АК", "text": "Принято. В 11:00 звон — подключайся.", "time": "09:18"},
                ]},
            ]},
            {"name": "call", "title": "Звонок — видеосетка + чат", "blocks": [
                {"t": "cards", "cols": 2, "items": [
                    {"title": "Виктор Швед", "sub": "говорит", "icon": "ВШ", "grad": True, "badge": "REC", "badgeColor": "error", "h": 220},
                    {"title": "Анна Ким", "sub": "микрофон выкл", "icon": "АК", "grad": True, "h": 220},
                    {"title": "Lara (агент)", "sub": "слушает", "icon": "L", "h": 220},
                    {"title": "Игорь Панов", "sub": "", "icon": "ИП", "h": 220},
                ]},
                {"t": "toolbar", "actions": [["🎙 Микрофон", False], ["📹 Камера", False], ["💬 Чат", False], ["Завершить", True]]},
            ]},
            {"name": "settings", "title": "Настройки канала", "blocks": [
                {"t": "form", "title": "Канал #general", "fields": ["Название", "Описание", "Уведомления"], "submit": "Сохранить"},
            ]},
            {"name": "guest", "title": "Гостевое приглашение", "shell": False, "blocks": [
                {"t": "hero", "kicker": "LINNEX SYNC", "title": "Вас пригласили в звонок", "sub": "Виктор Швед · команда Linnex", "actions": [["Присоединиться", True], ["Отклонить", False]]},
            ]},
        ],
    },
    "flows": {
        "title": "Flows — агенты и автоматизация",
        "zone": "zone/020 — Flows",
        "screens": [
            {"name": "list", "title": "Список flow", "blocks": [
                {"t": "toolbar", "search": "Найти flow…", "filters": ["Статус", "Владелец"], "actions": [["Создать flow", True]]},
                {"t": "table", "cols": ["НАЗВАНИЕ", "СТАТУС", "ЗАПУСКОВ", "ОБНОВЛЁН", ""], "rows": [
                    ["Support Agent", {"badge": "активен", "color": "success"}, "1 240", "2 ч назад", "›"],
                    ["Lead Qualifier", {"badge": "активен", "color": "success"}, "856", "вчера", "›"],
                    ["Invoice Watcher", {"badge": "пауза", "color": "warning"}, "64", "12 мая", "›"],
                    ["Nightly ETL", {"badge": "черновик", "color": "info"}, "0", "10 мая", "›"],
                ]},
            ]},
            {"name": "editor", "title": "Редактор flow — canvas нод", "blocks": [
                {"t": "editor", "nodes": [
                    ["Триггер: webhook", 60, 60, "trigger"],
                    ["LLM · GPT-5", 330, 140, "llm_node"],
                    ["Ветка по intent", 620, 60, "condition"],
                    ["Tool: crm.search", 620, 240, "tool"],
                    ["Ответ → канал", 910, 140, "output"],
                ]},
            ]},
            {"name": "detail", "title": "Flow — детали и метрики", "blocks": [
                {"t": "detail", "title": "Support Agent", "badge": "активен", "actions": [["Редактировать", True], ["Логи", False]], "rows": [
                    ["Модель", "linnex_llm · gpt-5"],
                    ["Запусков за 7д", "1 240 (успех 97%)"],
                    ["Средняя длительность", "4.2 с"],
                    ["Расход токенов", "1.2M / день"],
                    ["Владелец", "Виктор Швед"],
                ], "side": ["Быстрые действия", ["▶ Тестовый запуск", "⏸ Пауза", "⧉ Дублировать", "🗑 Архив"]]},
            ]},
            {"name": "session", "title": "Сессия — выполнение flow", "blocks": [
                {"t": "split", "h": 700, "items": [
                    {"title": "#1042 · webhook", "sub": "успех · 4.2с", "active": True},
                    {"title": "#1041 · schedule", "sub": "успех · 3.8с"},
                    {"title": "#1040 · webhook", "sub": "ошибка · 1.1с"},
                    {"title": "#1039 · handoff", "sub": "успех · 6.0с"},
                ], "detail": "Сессия #1042", "lines": ["▸ Триггер: входящий webhook (2 мс)", "▸ LLM: 1 204 токена (3.1 с)", "▸ Tool crm.search: 200 OK (400 мс)", "▸ Ответ отправлен в #general"]},
            ]},
            {"name": "evaluation", "title": "Evaluation Lab", "blocks": [
                {"t": "stats", "items": [["Pass rate", "94.2%", "+1.3%"], ["Сценариев", "128", ""], ["Регрессий", "3", "-2"], ["Стоимость прогона", "₽412", ""]]},
                {"t": "table", "cols": ["СЦЕНАРИЙ", "МОДЕЛЬ", "ОЦЕНКА", "СТАТУС"], "rows": [
                    ["refund-flow", "gpt-5", "0.98", {"badge": "pass", "color": "success"}],
                    ["escalation", "gpt-5", "0.91", {"badge": "pass", "color": "success"}],
                    ["sql-guard", "gpt-5-mini", "0.62", {"badge": "fail", "color": "error"}],
                ]},
            ]},
            {"name": "skills", "title": "Skill Library", "blocks": [
                {"t": "cards", "cols": 3, "items": [
                    {"title": "agent-planning", "sub": "Планирование шагов агента", "badge": "core", "icon": "🧭"},
                    {"title": "code-review", "sub": "Ревью PR и диффов", "badge": "team", "icon": "🔍"},
                    {"title": "sql-expert", "sub": "Запросы к datasource", "badge": "team", "icon": "🗄"},
                    {"title": "writer", "sub": "Тексты и документы", "badge": "core", "icon": "✍"},
                    {"title": "geo-routing", "sub": "Маршруты и ETA", "badge": "beta", "icon": "🗺"},
                    {"title": "voice", "sub": "STT/TTS пайплайн", "badge": "beta", "icon": "🎙"},
                ]},
            ]},
            {"name": "mcp", "title": "MCP-серверы", "blocks": [
                {"t": "list", "items": [
                    {"title": "context7", "sub": "docs lookup · 12 tools", "icon": "C7", "badge": "ok", "badgeColor": "success"},
                    {"title": "postgres-prod", "sub": "db.* · 8 tools", "icon": "PG", "badge": "ok", "badgeColor": "success"},
                    {"title": "linear", "sub": "issues · 6 tools", "icon": "LN", "badge": "auth", "badgeColor": "warning"},
                ]},
            ]},
            {"name": "tools", "title": "Tools — реестр", "blocks": [
                {"t": "table", "cols": ["TOOL", "ТИП", "CAPABILITY", "ИСПОЛЬЗОВАНИЙ"], "rows": [
                    ["crm.entity.search", "builtin", "crm.read", "12 400"],
                    ["db.query", "capability", "db.read", "8 112"],
                    ["http.request", "capability", "net.out", "5 930"],
                    ["code.run", "sandbox", "eval.code", "2 014"],
                ]},
            ]},
        ],
    },
    "crm": {
        "title": "NetWorkle — CRM-граф",
        "zone": "zone/030 — CRM",
        "screens": [
            {"name": "dashboard", "title": "CRM — дашборд", "blocks": [
                {"t": "stats", "items": [["Сущностей", "4 812", "+96"], ["Заметок", "1 208", "+31"], ["Задач открыто", "142", "-8"], ["Интеграций", "6", ""]]},
                {"t": "cards", "cols": 3, "items": [
                    {"title": "Последние сущности", "sub": "ООО «Вега», ИП Соколов…", "icon": "◆"},
                    {"title": "Свежие заметки", "sub": "12 за сегодня", "icon": "✎"},
                    {"title": "Просроченные задачи", "sub": "4 требуют внимания", "icon": "!", "badge": "4", "badgeColor": "error"},
                ]},
            ]},
            {"name": "entities", "title": "Сущности", "blocks": [
                {"t": "toolbar", "search": "Искать сущность…", "filters": ["Тип", "Namespace"], "actions": [["Создать", True]]},
                {"t": "table", "cols": ["ИМЯ", "ТИП", "СВЯЗЕЙ", "ОБНОВЛЕНО"], "rows": [
                    ["ООО «Вега»", {"badge": "company", "color": "info"}, "18", "2 ч назад"],
                    ["ИП Соколов", {"badge": "person", "color": "success"}, "7", "вчера"],
                    ["АО «ТрансНефть»", {"badge": "company", "color": "info"}, "42", "вчера"],
                    ["Марина Орлова", {"badge": "person", "color": "success"}, "3", "3 дня"],
                ]},
            ]},
            {"name": "entity-detail", "title": "Карточка сущности", "blocks": [
                {"t": "detail", "title": "ООО «Вега»", "badge": "company", "actions": [["Заметка", True], ["Задача", False]], "rows": [
                    ["ИНН", "7708123456"], ["Сайт", "vega.example"], ["Менеджер", "Анна Ким"], ["Сделок", "3 активных · ₽2.1M"],
                ], "side": ["Связи", ["→ ИП Соколов (директор)", "→ Счёт №1042", "→ Заметок: 12", "→ Файлов: 4"]]},
            ]},
            {"name": "notes", "title": "Заметки", "blocks": [
                {"t": "split", "h": 720, "items": [
                    {"title": "Созвон по договору", "sub": "сегодня · ООО «Вега»", "active": True},
                    {"title": "Пожелания к интеграции", "sub": "вчера"},
                    {"title": "Итоги квартала", "sub": "12 мая"},
                    {"title": "Онбординг клиента", "sub": "10 мая"},
                ], "detail": "Созвон по договору", "lines": ["Обсудили условия §4–6.", "Клиент просит отсрочку 14 дней — вынести на решение.", "AI-анализ: 2 action item → создано задачи.", "Связи: ООО «Вега», ИП Соколов."]},
            ]},
            {"name": "tasks", "title": "Задачи CRM", "blocks": [
                {"t": "kanban", "cols": [
                    {"title": "К выполнению", "cards": [["Позвонить ИП Соколов", "сегодня"], ["Отправить КП «Вега»", "до пт"]]},
                    {"title": "В работе", "cards": [["Договор §4 правки", "юрист"]]},
                    {"title": "Готово", "cards": [["Встреча 14.05", ""], ["Онбординг план", ""]]},
                ]},
            ]},
            {"name": "graph", "title": "Граф связей", "blocks": [
                {"t": "editor", "h": 620, "nodes": [
                    ["ООО «Вега»", 480, 260, "company"],
                    ["ИП Соколов", 160, 120, "person"],
                    ["Счёт №1042", 160, 420, "doc"],
                    ["Сделка Q2", 820, 120, "deal"],
                    ["Анна Ким", 820, 420, "person"],
                ], "links": [[0, 1], [0, 2], [0, 3], [0, 4]]},
            ]},
            {"name": "namespaces", "title": "Пространства", "blocks": [
                {"t": "cards", "cols": 3, "items": [
                    {"title": "Продажи", "sub": "1 204 сущности · 6 участников", "icon": "🏢"},
                    {"title": "Партнёры", "sub": "412 сущностей", "icon": "🤝"},
                    {"title": "Личное", "sub": "89 сущностей", "icon": "👤"},
                ]},
            ]},
            {"name": "templates", "title": "Шаблоны пространств", "blocks": [
                {"t": "cards", "cols": 3, "items": [
                    {"title": "B2B Sales", "sub": "company/person/deal/invoice", "icon": "📊"},
                    {"title": "Рекрутинг", "sub": "candidate/vacancy/interview", "icon": "🎯"},
                    {"title": "Проекты", "sub": "project/milestone/task", "icon": "📁"},
                ]},
            ]},
        ],
    },
    "office": {
        "title": "Документы",
        "zone": "zone/040 — Office",
        "screens": [
            {"name": "recent", "title": "Недавние документы", "blocks": [
                {"t": "toolbar", "search": "Искать документ…", "filters": ["Тип", "Каталог"], "actions": [["Загрузить", False], ["Создать", True]]},
                {"t": "gallery", "n": 8, "items": ["Отчёт Q2.xlsx", "Договор-1042.docx", "Презентация.pptx", "Акт.pdf", "План проекта", "Накладная", "Спецификация", "Письмо"]},
            ]},
            {"name": "catalogs", "title": "Каталоги", "blocks": [
                {"t": "split", "h": 700, "items": [
                    {"title": "📁 Договоры", "sub": "142 файла", "active": True},
                    {"title": "📁 Финансы", "sub": "86"},
                    {"title": "📁 Маркетинг", "sub": "230"},
                    {"title": "📁 HR", "sub": "54"},
                    {"title": "🗑 Корзина", "sub": "12"},
                ], "detail": "📁 Договоры", "lines": ["Договор-1042.docx — сегодня, Анна К.", "Договор-1041.pdf — вчера", "Доп. соглашение-3.docx — 12 мая", "NDA-шаблон.docx — шаблон"]},
            ]},
            {"name": "editor", "title": "Редактор документа (OnlyOffice)", "blocks": [
                {"t": "toolbar", "actions": [["Скачать", False], ["Поделиться", True], ["⋯", False]]},
                {"t": "text", "lines": [
                    "ДОГОВОР №1042",
                    "",
                    "1. Предмет договора. Поставщик обязуется поставить, а Покупатель — принять и оплатить…",
                    "2. Стоимость и порядок расчётов. Общая сумма договора составляет 2 140 000 ₽…",
                    "3. Сроки поставки. Поставка осуществляется в течение 30 календарных дней…",
                    "",
                    "— совместное редактирование: Анна К., Игорь П.",
                ]},
            ]},
            {"name": "public", "title": "Публичная ссылка на файл", "shell": False, "blocks": [
                {"t": "hero", "kicker": "LINNEX DOCUMENTS", "title": "Отчёт Q2.xlsx", "sub": "Файл открыт по публичной ссылке · 2.4 MB", "actions": [["Скачать", True], ["Просмотр", False]]},
            ]},
        ],
    },
    "worktracker": {
        "title": "Задачи — Worktracker",
        "zone": "zone/050 — Worktracker",
        "screens": [
            {"name": "board", "title": "Доска задач", "blocks": [
                {"t": "toolbar", "search": "Поиск задачи…", "filters": ["Очередь", "Исполнитель"], "actions": [["Новая задача", True]]},
                {"t": "kanban", "cols": [
                    {"title": "Новые", "cards": [["WT-812: вернуть лид в воронку", "crm"], ["WT-815: починить webhook", "flows"]]},
                    {"title": "В работе", "cards": [["WT-790: ревью договора", "Анна К."], ["WT-802: HITL — ждёт вас", "Lara"]]},
                    {"title": "Ревью", "cards": [["WT-770: отчёт готов", ""]]},
                    {"title": "Готово", "cards": [["WT-740: выкат 1.46", ""], ["WT-738: миграция", ""]]},
                ]},
            ]},
            {"name": "my", "title": "Мои задачи", "blocks": [
                {"t": "list", "items": [
                    {"title": "WT-802: одобрить HITL-шаг flow", "sub": "Support Agent · ждёт 2 ч", "badge": "HITL", "badgeColor": "warning", "icon": "⚡"},
                    {"title": "WT-790: ревью договора §4", "sub": "CRM · до пятницы", "icon": "📄"},
                    {"title": "WT-812: вернуть лид", "sub": "назначена вчера", "icon": "◆"},
                    {"title": "WT-815: webhook 500-е", "sub": "flows · high", "badge": "bug", "badgeColor": "error", "icon": "🐞"},
                ]},
            ]},
            {"name": "item", "title": "Карточка задачи WT-802", "blocks": [
                {"t": "detail", "title": "WT-802: одобрить HITL-шаг", "badge": "HITL", "badgeColor": "warning", "actions": [["Одобрить", True], ["Отклонить", False]], "rows": [
                    ["Очередь", "flows-hitl"], ["Исполнитель", "Lara (flow-employee)"], ["Назначил", "flow Support Agent"], ["Дедлайн", "сегодня 18:00"], ["Приоритет", "high"],
                ], "side": ["Связи", ["→ flow session #1042", "→ канал #general", "→ WT-790 (зависит)"]]},
            ]},
            {"name": "queues", "title": "Очереди", "blocks": [
                {"t": "table", "cols": ["ОЧЕРЕДЬ", "ОТКРЫТО", "SLA", "HITL"], "rows": [
                    ["support", "23", "4 ч", "2"],
                    ["flows-hitl", "4", "1 ч", "4"],
                    ["crm", "12", "1 д", "0"],
                    ["devops", "6", "2 ч", "0"],
                ]},
            ]},
        ],
    },
    "shop": {
        "title": "Магазин — онлайн-витрина",
        "zone": "zone/060 — Shop",
        "screens": [
            {"name": "menu", "title": "Меню — витрина", "shell": False, "blocks": [
                {"t": "toolbar", "search": "Найти блюдо…", "filters": ["Пицца", "Роллы", "Напитки", "Десерты"]},
                {"t": "cards", "cols": 4, "items": [
                    {"title": "Маргарита", "sub": "420 ₽ · томат, моцарелла", "icon": "🍕", "h": 190},
                    {"title": "Филадельфия", "sub": "590 ₽ · лосось, крем", "icon": "🍣", "h": 190},
                    {"title": "Цезарь", "sub": "380 ₽ · курица, пармезан", "icon": "🥗", "h": 190},
                    {"title": "Тирамису", "sub": "290 ₽ · классика", "icon": "🍰", "h": 190},
                ]},
            ]},
            {"name": "builder", "title": "Конструктор меню", "blocks": [
                {"t": "split", "h": 700, "items": [
                    {"title": "Пицца", "sub": "12 позиций", "active": True},
                    {"title": "Роллы", "sub": "18"},
                    {"title": "Напитки", "sub": "9"},
                    {"title": "Модификаторы", "sub": "24"},
                ], "detail": "Категория: Пицца", "lines": ["Маргарита — 420 ₽ — в наличии", "Пепперони — 480 ₽", "4 сыра — 540 ₽", "+ модификаторы: бортик, соус, доп. сыр"]},
            ]},
            {"name": "orders", "title": "Заказы", "blocks": [
                {"t": "table", "cols": ["№", "КЛИЕНТ", "СУММА", "СТАТУС", "ВРЕМЯ"], "rows": [
                    ["#3128", "+7 900 …12-34", "1 240 ₽", {"badge": "доставка", "color": "info"}, "12:40"],
                    ["#3127", "+7 916 …77-01", "860 ₽", {"badge": "готовится", "color": "warning"}, "12:32"],
                    ["#3126", "самовывоз", "1 590 ₽", {"badge": "готов", "color": "success"}, "12:15"],
                ]},
            ]},
            {"name": "promos", "title": "Акции и промокоды", "blocks": [
                {"t": "cards", "cols": 3, "items": [
                    {"title": "2+1 пицца", "sub": "до 31 мая · −33%", "badge": "активна", "badgeColor": "success", "icon": "%"},
                    {"title": "WELCOME10", "sub": "−10% первый заказ", "badge": "активна", "badgeColor": "success", "icon": "#"},
                    {"title": "Счастливые часы", "sub": "14–17 ч · −15%", "badge": "расписание", "badgeColor": "info", "icon": "⏰"},
                ]},
            ]},
            {"name": "settings", "title": "Настройки витрины", "blocks": [
                {"t": "form", "title": "Витрина vega-shop", "fields": ["Домен / slug", "Зона доставки", "Часы работы", "Мин. сумма заказа"], "submit": "Сохранить"},
            ]},
        ],
    },
    "stock": {
        "title": "Склад — WMS",
        "zone": "zone/070 — Stock",
        "screens": [
            {"name": "transfers-in", "title": "Приход — трансферы", "blocks": [
                {"t": "table", "cols": ["№", "ОТКУДА", "КУДА", "ПОЗИЦИЙ", "СТАТУС"], "rows": [
                    ["TR-1042", "Поставщик «Альфа»", "Основной склад", "24", {"badge": "принят", "color": "success"}],
                    ["TR-1041", "Цех-2", "Основной склад", "8", {"badge": "в пути", "color": "info"}],
                    ["TR-1040", "Поставщик «Бета»", "Холодный зал", "56", {"badge": "частично", "color": "warning"}],
                ]},
            ]},
            {"name": "transfers-out", "title": "Расход — трансферы", "blocks": [
                {"t": "table", "cols": ["№", "ОТКУДА", "КУДА", "ПОЗИЦИЙ", "СТАТУС"], "rows": [
                    ["TR-2098", "Основной склад", "Витрина", "12", {"badge": "отгружен", "color": "success"}],
                    ["TR-2097", "Холодный зал", "Кухня", "31", {"badge": "сборка", "color": "warning"}],
                ]},
            ]},
            {"name": "products", "title": "Товары", "blocks": [
                {"t": "toolbar", "search": "SKU / название…", "filters": ["Категория", "Склад"], "actions": [["Новый товар", True]]},
                {"t": "table", "cols": ["SKU", "ТОВАР", "ОСТАТОК", "ЕИ", "ЦЕНА"], "rows": [
                    ["SKU-1024", "Моцарелла 2кг", "14.2", "кг", "890 ₽"],
                    ["SKU-0871", "Лосось с/с", "6.8", "кг", "1 450 ₽"],
                    ["SKU-2048", "Мука в/с 25кг", "3", "меш", "1 120 ₽"],
                ]},
            ]},
            {"name": "locations", "title": "Локации", "blocks": [
                {"t": "cards", "cols": 3, "items": [
                    {"title": "Основной склад", "sub": "1 204 SKU · 68% заполнение", "icon": "🏭"},
                    {"title": "Холодный зал", "sub": "310 SKU · 4°C", "icon": "❄"},
                    {"title": "Витрина", "sub": "86 SKU · витрина", "icon": "🛒"},
                ]},
            ]},
            {"name": "valuation", "title": "Оценка запасов", "blocks": [
                {"t": "stats", "items": [["Стоимость запасов", "₽4.82M", "+2.1%"], ["SKU", "1 214", ""], ["Просрочено", "3 позиции", "-1"], ["Оборачиваемость", "18 дн", ""]]},
                {"t": "table", "cols": ["КАТЕГОРИЯ", "СТОИМОСТЬ", "ДОЛЯ"], "rows": [
                    ["Сырьё", "₽2.10M", "44%"], ["Полуфабрикаты", "₽1.40M", "29%"], ["Готовая продукция", "₽0.98M", "20%"], ["Упаковка", "₽0.34M", "7%"],
                ]},
            ]},
        ],
    },
    "geo": {
        "title": "Гео — карты и маршруты",
        "zone": "zone/080 — Geo",
        "screens": [
            {"name": "map-lab", "title": "Map Lab — карта", "blocks": [
                {"t": "map", "h": 640, "pins": [[120, 540, "Склад", "accent"], [1280, 120, "Клиент", "accent/secondary"], [700, 300, "Курьер", "accent/tertiary"]]},
            ]},
            {"name": "route-lab", "title": "Route Lab — маршрут", "blocks": [
                {"t": "map", "h": 460},
                {"t": "stats", "items": [["Дистанция", "18.4 км", ""], ["ETA", "32 мин", ""], ["Остановок", "5", ""], ["Загрузка", "78%", ""]]},
            ]},
            {"name": "sources", "title": "Источники геоданных", "blocks": [
                {"t": "list", "items": [
                    {"title": "OSM Nominatim", "sub": "геокодинг · активен", "badge": "ok", "badgeColor": "success", "icon": "🌍"},
                    {"title": "pgRouting", "sub": "матрица · локально", "badge": "ok", "badgeColor": "success", "icon": "🧭"},
                    {"title": "DaData", "sub": "адреса · ключ настроен", "badge": "ok", "badgeColor": "success", "icon": "📮"},
                ]},
            ]},
            {"name": "addresses", "title": "Адресная база", "blocks": [
                {"t": "toolbar", "search": "Адрес…", "actions": [["Импорт", True]]},
                {"t": "table", "cols": ["АДРЕС", "КООРДИНАТЫ", "ЗОНА", "ТОЧНОСТЬ"], "rows": [
                    ["Москва, Тверская 1", "55.7558, 37.6173", "Центр", {"badge": "roof", "color": "success"}],
                    ["Москва, Арбат 24", "55.7496, 37.5934", "Центр", {"badge": "street", "color": "warning"}],
                ]},
            ]},
        ],
    },
    "rag": {
        "title": "RAG — база знаний",
        "zone": "zone/090 — RAG",
        "screens": [
            {"name": "services", "title": "RAG — сервисы", "blocks": [
                {"t": "stats", "items": [["Документов", "12 408", ""], ["Чанков", "96 204", ""], ["Запросов/день", "3 140", "+8%"], ["Реранк", "вкл", ""]]},
                {"t": "list", "items": [
                    {"title": "agentset-prod", "sub": "pgvector · 12k документов", "badge": "ok", "badgeColor": "success", "icon": "🧠"},
                    {"title": "embedding litserve", "sub": "bge-m3 · локально", "badge": "ok", "badgeColor": "success", "icon": "⚡"},
                    {"title": "rerank", "sub": "bge-reranker", "badge": "ok", "badgeColor": "success", "icon": "↕"},
                ]},
            ]},
            {"name": "namespace", "title": "Namespace — индексация", "blocks": [
                {"t": "table", "cols": ["ДОКУМЕНТ", "ЧАНКОВ", "ИНДЕКС", "ОБНОВЛЁН"], "rows": [
                    ["manual.pdf", "412", {"badge": "ok", "color": "success"}, "сегодня"],
                    ["runbook.md", "96", {"badge": "ok", "color": "success"}, "вчера"],
                    ["faq.docx", "64", {"badge": "reembed", "color": "warning"}, "очередь"],
                ]},
            ]},
            {"name": "search", "title": "Поиск по базе знаний", "blocks": [
                {"t": "toolbar", "search": "Как продлить TLS-сертификат?", "actions": [["Найти", True]]},
                {"t": "list", "items": [
                    {"title": "runbook/tls.md — §3", "sub": "score 0.94 · cert-manager renew", "badge": "0.94", "badgeColor": "success", "icon": "§"},
                    {"title": "infra.md — продление", "sub": "score 0.87", "badge": "0.87", "badgeColor": "info", "icon": "§"},
                    {"title": "ingress.yaml", "sub": "score 0.71", "badge": "0.71", "badgeColor": "info", "icon": "§"},
                ]},
            ]},
            {"name": "settings", "title": "Настройки RAG", "blocks": [
                {"t": "form", "title": "Индексация", "fields": ["Chunk size", "Overlap", "Гибридный поиск", "TTL кэша"], "submit": "Применить"},
            ]},
        ],
    },
    "wiki": {
        "title": "Wiki — знания команды",
        "zone": "zone/100 — Wiki",
        "screens": [
            {"name": "page", "title": "Страница wiki", "blocks": [
                {"t": "split", "h": 720, "items": [
                    {"title": "Главная", "sub": "", "active": True},
                    {"title": "Инженерия", "sub": "24 стр."},
                    {"title": "— Релизный процесс", "sub": ""},
                    {"title": "— Runbooks", "sub": "12 стр."},
                    {"title": "Продукт", "sub": "8 стр."},
                ], "detail": "Релизный процесс", "lines": ["1. Ветка release/* от main.", "2. Гейты: lint → test → e2e.", "3. Canary 10% → 100%.", "4. Rollback — helm rollback в один шаг."]},
            ]},
            {"name": "history", "title": "История страницы", "blocks": [
                {"t": "list", "items": [
                    {"title": "v14 — правка §3", "sub": "Анна К. · сегодня 14:20", "icon": "v14", "badge": "current", "badgeColor": "success"},
                    {"title": "v13 — добавлен runbook", "sub": "Виктор Ш. · вчера", "icon": "v13"},
                    {"title": "v12 — исправлена ссылка", "sub": "Анна К. · 12 мая", "icon": "v12"},
                ]},
            ]},
            {"name": "shared", "title": "Публичная wiki-страница", "shell": False, "blocks": [
                {"t": "hero", "kicker": "LINNEX WIKI", "title": "Релизный процесс", "sub": "Опубликовано командой Инженерия · v14", "actions": [["Читать", True]]},
            ]},
        ],
    },
    "processes": {
        "title": "Процессы — связи экранов по docs/scenarios",
        "zone": "zone/999 — Процессы",
        "journeys": [
            {"name": "1 · Вход → работа в чате → звонок", "steps": [
                ["frontend", "login"], ["frontend", "dashboard"], ["sync", "channel"], ["sync", "chat"], ["sync", "call"]]},
            {"name": "2 · Заметка CRM → AI-анализ → задача", "steps": [
                ["crm", "notes"], ["crm", "entity-detail"], ["crm", "tasks"], ["worktracker", "board"], ["worktracker", "item"]]},
            {"name": "3 · Flow: сборка → сессия → HITL → eval", "steps": [
                ["flows", "list"], ["flows", "editor"], ["flows", "session"], ["worktracker", "item · HITL"], ["flows", "evaluation"]]},
            {"name": "4 · Заказ → склад → доставка", "steps": [
                ["shop", "menu"], ["shop", "orders"], ["stock", "transfers-out"], ["geo", "route-lab"], ["geo", "map-lab"]]},
            {"name": "5 · Документ → знания → агент", "steps": [
                ["office", "catalogs"], ["office", "editor"], ["wiki", "page"], ["rag", "namespace"], ["rag", "search"], ["flows", "session"]]},
        ],
        "screens": [],
    },
    "litserve": {
        "title": "LitServe — локальный инференс",
        "zone": "zone/110 — LitServe",
        "screens": [
            {"name": "services", "title": "Инференс-сервисы", "blocks": [
                {"t": "stats", "items": [["Воркеров", "4", ""], ["GPU util", "62%", ""], ["Запросов/мин", "312", ""], ["p95", "84 мс", "-6 мс"]]},
                {"t": "table", "cols": ["СЕРВИС", "МОДЕЛЬ", "ВОРКЕРОВ", "СТАТУС"], "rows": [
                    ["embedding", "bge-m3", "2", {"badge": "ok", "color": "success"}],
                    ["rerank", "bge-reranker-v2", "1", {"badge": "ok", "color": "success"}],
                    ["stt", "whisper-large", "1", {"badge": "warmup", "color": "warning"}],
                ]},
            ]},
        ],
    },
    "frontend": {
        "title": "Платформа — консоль и маркетинг",
        "zone": "zone/005 — Platform",
        "screens": [
            {"name": "landing", "title": "Лендинг", "shell": False, "blocks": [
                {"t": "hero", "kicker": "LINNEX", "title": "Платформа автоматизации бизнеса", "sub": "AI-агенты, база знаний, CRM-граф, чат и документы — в одном рабочем пространстве.", "actions": [["Начать бесплатно", True], ["Смотреть демо", False]]},
                {"t": "cards", "cols": 4, "items": [
                    {"title": "AI Studio", "sub": "агенты и flow", "icon": "⚡"},
                    {"title": "NetWorkle", "sub": "CRM-граф", "icon": "◆"},
                    {"title": "Sync", "sub": "чат и звонки", "icon": "✉"},
                    {"title": "Документы", "sub": "офис и файлы", "icon": "▤"},
                ]},
            ]},
            {"name": "product", "title": "Продуктовая страница", "shell": False, "blocks": [
                {"t": "hero", "kicker": "AI STUDIO", "title": "Агенты, которые работают", "sub": "Визуальный редактор flow, LLM-ноды, tools и evaluation в одном месте.", "actions": [["Попробовать", True]]},
                {"t": "cards", "cols": 3, "items": [
                    {"title": "Визуальный редактор", "sub": "ноды, ветки, маппинги", "icon": "◫"},
                    {"title": "Evaluation Lab", "sub": "прогоны и метрики", "icon": "∑"},
                    {"title": "Skill Library", "sub": "пакеты навыков", "icon": "🧭"},
                ]},
            ]},
            {"name": "blog", "title": "Блог — список постов", "shell": False, "blocks": [
                {"t": "cards", "cols": 3, "items": [
                    {"title": "Как мы строили flows", "sub": "12 мая · 8 мин", "icon": "✍"},
                    {"title": "RAG в продакшене", "sub": "5 мая · 6 мин", "icon": "🧠"},
                    {"title": "Liquid Glass дизайн", "sub": "28 апр · 4 мин", "icon": "🎨"},
                ]},
            ]},
            {"name": "login", "title": "Вход", "shell": False, "blocks": [
                {"t": "form", "narrow": True, "title": "Вход в Linnex", "fields": ["Email", "Пароль"], "submit": "Войти", "cancel": "Создать аккаунт"},
            ]},
            {"name": "dashboard", "title": "Консоль — дашборд", "blocks": [
                {"t": "stats", "items": [["Сервисов", "12", ""], ["Сообщений/день", "8 412", "+4%"], ["Flow-запусков", "1 240", ""], ["Документов", "3 204", ""]]},
                {"t": "cards", "cols": 4, "items": [
                    {"title": "Синк", "sub": "3 непрочитанных", "icon": "✉"},
                    {"title": "CRM", "sub": "4 задачи", "icon": "◆"},
                    {"title": "Flows", "sub": "12 активных", "icon": "⚡"},
                    {"title": "Документы", "sub": "обновлено 8", "icon": "▤"},
                ]},
            ]},
            {"name": "search", "title": "Глобальный поиск", "blocks": [
                {"t": "toolbar", "search": "договор вега…", "filters": ["Все типы"]},
                {"t": "list", "items": [
                    {"title": "Договор-1042.docx", "sub": "Документы · Договоры", "icon": "▤", "badge": "file", "badgeColor": "info"},
                    {"title": "ООО «Вега»", "sub": "CRM · сущность", "icon": "◆", "badge": "entity", "badgeColor": "success"},
                    {"title": "#1042 счёт", "sub": "CRM · doc", "icon": "🧾"},
                ]},
            ]},
            {"name": "notifications", "title": "Уведомления", "blocks": [
                {"t": "list", "items": [
                    {"title": "WT-802 ждёт вашего решения", "sub": "2 мин назад · HITL", "badge": "new", "badgeColor": "warning", "icon": "⚡"},
                    {"title": "@упоминание в #general", "sub": "12 мин", "icon": "✉"},
                    {"title": "Отчёт готов к скачиванию", "sub": "1 ч", "icon": "📊"},
                ]},
            ]},
            {"name": "settings", "title": "Настройки профиля", "blocks": [
                {"t": "form", "title": "Профиль", "fields": ["Имя", "Email", "Язык", "Часовой пояс"], "submit": "Сохранить"},
            ]},
            {"name": "team", "title": "Команда", "blocks": [
                {"t": "toolbar", "search": "Участник…", "actions": [["Пригласить", True]]},
                {"t": "table", "cols": ["УЧАСТНИК", "РОЛЬ", "СТАТУС", "АКТИВНОСТЬ"], "rows": [
                    ["Виктор Швед", {"badge": "admin", "color": "warning"}, "онлайн", "сейчас"],
                    ["Анна Ким", {"badge": "member", "color": "info"}, "онлайн", "5 мин"],
                    ["Lara (flow)", {"badge": "agent", "color": "success"}, "24/7", "—"],
                ]},
            ]},
            {"name": "billing", "title": "Биллинг", "blocks": [
                {"t": "stats", "items": [["Баланс", "₽48 240", ""], ["Расход/мес", "₽12 400", "-8%"], ["Токенов", "42M", ""], ["Тариф", "Team", ""]]},
                {"t": "table", "cols": ["ДАТА", "ОПЕРАЦИЯ", "СУММА"], "rows": [
                    ["15.05", "llm · gpt-5 · 1.2M tok", "-₽412"],
                    ["14.05", "voice · 48 мин", "-₽96"],
                    ["12.05", "пополнение", "+₽10 000"],
                ]},
            ]},
            {"name": "integrations", "title": "Интеграции", "blocks": [
                {"t": "cards", "cols": 3, "items": [
                    {"title": "Telegram", "sub": "уведомления в канал", "badge": "подключено", "badgeColor": "success", "icon": "TG"},
                    {"title": "DaData", "sub": "адреса и реквизиты", "badge": "подключено", "badgeColor": "success", "icon": "DD"},
                    {"title": "1C", "sub": "выгрузка документов", "badge": "настроить", "badgeColor": "warning", "icon": "1C"},
                ]},
            ]},
            {"name": "namespaces", "title": "Пространства компании", "blocks": [
                {"t": "cards", "cols": 3, "items": [
                    {"title": "Основное", "sub": "по умолчанию", "icon": "🏢"},
                    {"title": "Разработка", "sub": "dev-команда", "icon": "🛠"},
                    {"title": "Продажи", "sub": "отдел продаж", "icon": "📈"},
                ]},
            ]},
        ],
    },
}


def _payload(service: str) -> Json:
    spec = extract()
    sdef = SCREENS[service]
    tokens = {t["name"]: {"Dark": t["values"].get("Dark")} for t in spec["tokens"]}
    return {
        "page": "📱 Экраны",
        "zone": sdef["zone"],
        "collDark": f"{spec['collection']} · Dark",
        "tokens": tokens,
        "svc": service,
        "screens": [*sdef.get("screens", []), *EXTRA_SCREENS.get(service, []), *MODAL_SCREENS.get(service, []), *STATE_SCREENS.get(service, [])],
        "journeys": sdef.get("journeys"),
    }


def _sc(name: str, title: str, blocks: list[Json], shell: bool = True, h: int | None = None, mobile: bool = False, dialog: bool = False, dialog_title: str = "") -> Json:
    scr: Json = {"name": name, "title": title, "blocks": blocks}
    if not shell:
        scr["shell"] = False
    if h:
        scr["h"] = h
    if mobile:
        scr["mobile"] = True
    if dialog:
        scr["dialog"] = True
        if dialog_title:
            scr["dialogTitle"] = dialog_title
    return scr


def _modal(name: str, title: str, fields: list[str], submit: str = "Сохранить", checks: list[list[object]] | None = None, extra: list[Json] | None = None) -> Json:
    blk: Json = {"t": "fields", "items": fields, "submit": submit}
    if checks:
        blk["checks"] = checks
    return _sc("modal-" + name, "◈ " + title, [blk, *(extra or [])], dialog=True, dialog_title=title)


EXTRA_SCREENS: dict[str, list[Json]] = {
    "frontend": [
        # маркетинг
        _sc("product-agents", "Продукт — AI Studio", [
            {"t": "hero", "kicker": "AI STUDIO", "title": "Агенты, которые работают", "sub": "Визуальный редактор flow, LLM-ноды, tools и evaluation.", "actions": [["Попробовать", True]]},
            {"t": "cards", "cols": 3, "items": [
                {"title": "Визуальный редактор", "sub": "ноды, ветки, маппинги", "icon": "◫"},
                {"title": "Evaluation Lab", "sub": "прогоны и метрики", "icon": "∑"},
                {"title": "Skills", "sub": "пакеты навыков", "icon": "🧭"}]}], shell=False),
        _sc("product-crm", "Продукт — NetWorkle", [
            {"t": "hero", "kicker": "NETWORKLE", "title": "CRM как граф знаний", "sub": "Сущности, связи, AI-анализ заметок.", "actions": [["Попробовать", True]]},
            {"t": "cards", "cols": 3, "items": [
                {"title": "Граф связей", "sub": "сущности и отношения", "icon": "◆"},
                {"title": "AI-заметки", "sub": "анализ и экстракция", "icon": "✎"},
                {"title": "Пространства", "sub": "namespaces команд", "icon": "▤"}]}], shell=False),
        _sc("product-documents", "Продукт — Документы", [
            {"t": "hero", "kicker": "ДОКУМЕНТЫ", "title": "Офис в облаке", "sub": "Файлы, каталоги, OnlyOffice-редактор.", "actions": [["Попробовать", True]]},
            {"t": "cards", "cols": 3, "items": [
                {"title": "Каталоги", "sub": "структура файлов", "icon": "📁"},
                {"title": "Редактор", "sub": "совместная работа", "icon": "✎"},
                {"title": "Публичные ссылки", "sub": "шаринг", "icon": "🔗"}]}], shell=False),
        _sc("product-geo", "Продукт — Geo", [
            {"t": "hero", "kicker": "GEO", "title": "Гео-движок", "sub": "Адреса, маршруты, матрицы, изохроны.", "actions": [["Попробовать", True]]},
            {"t": "map", "h": 300}], shell=False),
        _sc("product-rag", "Продукт — RAG", [
            {"t": "hero", "kicker": "RAG", "title": "База знаний для агентов", "sub": "pgvector, гибридный поиск, реранк.", "actions": [["Попробовать", True]]},
            {"t": "cards", "cols": 3, "items": [
                {"title": "Индексация", "sub": "чанки и эмбеддинги", "icon": "🧠"},
                {"title": "Гибридный поиск", "sub": "BM25 + vector", "icon": "🔍"},
                {"title": "Реранк", "sub": "точность ответов", "icon": "↕"}]}], shell=False),
        _sc("product-shop", "Продукт — Магазин", [
            {"t": "hero", "kicker": "SHOP", "title": "Онлайн-витрина за час", "sub": "Меню, акции, заказы, доставка.", "actions": [["Создать витрину", True]]},
            {"t": "cards", "cols": 3, "items": [
                {"title": "Меню", "sub": "каталог и модификаторы", "icon": "🍕"},
                {"title": "Заказы", "sub": "лента в реальном времени", "icon": "🧾"},
                {"title": "Акции", "sub": "промокоды и скидки", "icon": "%"}]}], shell=False),
        _sc("product-sync", "Продукт — Sync", [
            {"t": "hero", "kicker": "SYNC", "title": "Чат людей и агентов", "sub": "Каналы, треды, звонки, гостевые ссылки.", "actions": [["Попробовать", True]]},
            {"t": "cards", "cols": 3, "items": [
                {"title": "Каналы", "sub": "команды и проекты", "icon": "#"},
                {"title": "Звонки", "sub": "LiveKit-видео", "icon": "📹"},
                {"title": "Агенты в чате", "sub": "flow-сотрудники", "icon": "⚡"}]}], shell=False),
        _sc("product-wiki", "Продукт — Wiki", [
            {"t": "hero", "kicker": "WIKI", "title": "Знания команды", "sub": "Страницы, история, публичный сайт.", "actions": [["Попробовать", True]]},
            {"t": "cards", "cols": 3, "items": [
                {"title": "Дерево страниц", "sub": "иерархия знаний", "icon": "📚"},
                {"title": "История", "sub": "версии и diff", "icon": "🕘"},
                {"title": "Публикации", "sub": "публичный сайт", "icon": "🌐"}]}], shell=False),
        _sc("digital-workers", "Демо — digital workers", [
            {"t": "hero", "kicker": "DIGITAL WORKERS", "title": "Наймите цифрового сотрудника", "sub": "Flow-агенты как члены команды: inbox, задачи, HITL.", "actions": [["Посмотреть демо", True]]},
            {"t": "cards", "cols": 3, "items": [
                {"title": "Поддержка", "sub": "ответы 24/7", "icon": "💬"},
                {"title": "Продажи", "sub": "квалификация лидов", "icon": "📈"},
                {"title": "Операционист", "sub": "рутина на автомате", "icon": "⚙"}]}], shell=False),
        _sc("about", "О компании", [
            {"t": "hero", "kicker": "О НАС", "title": "Linnex — платформа для команд", "sub": "Строим инструменты, где люди и AI-агенты работают вместе.", "actions": []},
            {"t": "text", "lines": ["Миссия — убрать рутину из операционки.", "Команда распределённая, офис — в продукте."]}], shell=False),
        _sc("blog-post", "Блог — пост", [
            {"t": "text", "lines": [
                "Как мы строили flows",
                "12 мая · 8 мин чтения · Виктор Ш.",
                "",
                "Flows начинались как прототип оркестрации LLM-вызовов.",
                "Сегодня это полноценный runtime: леджер событий, reducer,",
                "supersteps, прерывания и resume, HITL и time travel.",
                "В посте разбираем архитектуру и компромиссы."]}], shell=False),
        _sc("legal", "Юридические документы", [
            {"t": "split", "h": 600, "items": [
                {"title": "Условия использования", "sub": "terms", "active": True},
                {"title": "Политика конфиденциальности", "sub": "policy"},
                {"title": "Cookies", "sub": "cookies"},
                {"title": "Согласие на cookies", "sub": "consent"}],
                "detail": "Условия использования", "lines": [
                    "1. Общие положения. Платформа Linnex предоставляет…",
                    "2. Аккаунт. Пользователь обязуется…",
                    "3. Данные. Обработка согласно Политике…",
                    "4. Ответственность. Сервис предоставляется «как есть»…"]}], shell=False),
        _sc("roadmap", "Дорожная карта", [
            {"t": "kanban", "cols": [
                {"title": "Сейчас", "cards": [["HITL в чате", "Q2"], ["Embed-виджеты", ""]]},
                {"title": "Дальше", "cards": [["Voice-агенты v2", "Q3"], ["Мобильное приложение", ""]]},
                {"title": "Исследуем", "cards": [["Мульти-агенты", ""], ["Self-hosted", ""]]}]}], shell=False),
        _sc("support", "Поддержка", [
            {"t": "split", "h": 560, "items": [
                {"title": "Начало работы", "sub": "6 статей", "active": True},
                {"title": "Flows", "sub": "14 статей"},
                {"title": "Биллинг", "sub": "5 статей"},
                {"title": "API", "sub": "9 статей"}],
                "detail": "Частые вопросы", "lines": [
                    "▸ Как подключить свой домен? — Настройки → Домены.",
                    "▸ Лимиты тарифа Team? — до 15 участников, 5 flow.",
                    "▸ Как выгрузить данные? — Экспорт в Настройках → Данные."]}], shell=False),
        # вход и выбор компании
        _sc("join", "Присоединение по инвайту", [
            {"t": "form", "narrow": True, "title": "Вас пригласили в «Linnex Team»", "fields": ["Имя", "Email", "Пароль"], "submit": "Присоединиться", "cancel": "У меня есть аккаунт"}], shell=False),
        _sc("select-company", "Выбор компании", [
            {"t": "cards", "cols": 3, "items": [
                {"title": "Linnex Team", "sub": "12 участников · admin", "icon": "LT", "grad": True},
                {"title": "Вега", "sub": "4 участника", "icon": "ВГ"},
                {"title": "+ Новая компания", "sub": "создать пространство", "icon": "+"}]}], shell=False),
        # консоль
        _sc("services", "Каталог сервисов", [
            {"t": "cards", "cols": 4, "items": [
                {"title": "Sync", "sub": "чат и звонки", "icon": "✉"},
                {"title": "NetWorkle", "sub": "CRM-граф", "icon": "◆"},
                {"title": "Документы", "sub": "офис", "icon": "▤"},
                {"title": "Wiki", "sub": "знания", "icon": "📚"},
                {"title": "Задачи", "sub": "worktracker", "icon": "✓"},
                {"title": "Flows", "sub": "агенты", "icon": "⚡"},
                {"title": "Магазин", "sub": "витрина", "icon": "🛒"},
                {"title": "Склад", "sub": "WMS", "icon": "📦"}]}]),
        _sc("admin", "Админка платформы", [
            {"t": "stats", "items": [["Компаний", "148", "+6"], ["Пользователей", "2 904", "+41"], ["Событий/день", "1.2M", ""], ["Ошибок 5xx", "0.02%", "-0.01"]]},
            {"t": "table", "cols": ["КОМПАНИЯ", "ПЛАН", "ПОЛЬЗОВАТЕЛЕЙ", "СТАТУС"], "rows": [
                ["Linnex Team", {"badge": "team", "color": "info"}, "12", {"badge": "ok", "color": "success"}],
                ["Вега", {"badge": "free", "color": "info"}, "4", {"badge": "ok", "color": "success"}],
                ["ТестКо", {"badge": "trial", "color": "warning"}, "2", {"badge": "overdue", "color": "error"}]]}]),
        _sc("api-keys", "API-ключи", [
            {"t": "toolbar", "search": "Ключ…", "actions": [["Создать ключ", True]]},
            {"t": "table", "cols": ["ИМЯ", "ПРЕФИКС", "SCOPES", "ПОСЛЕДНИЙ ЗАПРОС"], "rows": [
                ["ci-deploy", "lx_9f2a…", "flows.run, read", "2 ч назад"],
                ["analytics", "lx_77b1…", "read", "вчера"],
                ["legacy-bot", "lx_00c4…", "*", {"badge": "отозван", "color": "error"}]]}]),
        _sc("company-variables", "Переменные компании", [
            {"t": "toolbar", "search": "Переменная…", "actions": [["Добавить", True]]},
            {"t": "table", "cols": ["КЛЮЧ", "ЗНАЧЕНИЕ", "SCOPE", "ОБНОВЛЕНА"], "rows": [
                ["support_phone", "+7 495 …", "company", "вчера"],
                ["delivery_zones", "moscow_central", "company", "3 дня"],
                ["openai_key", "sk-•••", "secret", "неделя"]]}]),
        _sc("company-voice-providers", "Голосовые провайдеры", [
            {"t": "list", "items": [
                {"title": "OpenAI Realtime", "sub": "STT+TTS · primary", "badge": "active", "badgeColor": "success", "icon": "OA"},
                {"title": "Yandex SpeechKit", "sub": "fallback", "badge": "standby", "badgeColor": "info", "icon": "YA"},
                {"title": "Local whisper", "sub": "litserve · тест", "icon": "WS"}]}]),
        _sc("embed-configs", "Embed-конфигурации", [
            {"t": "table", "cols": ["КОНФИГ", "FLOW", "ДОМЕНЫ", "ЗАПУСКОВ"], "rows": [
                ["support-widget", "Support Agent", "vega.example", "1 204"],
                ["quiz-embed", "Lead Qualifier", "*", "312"]]}]),
        _sc("lead-requests", "Заявки с лендинга", [
            {"t": "stats", "items": [["Всего", "212", "+18"], ["Новых", "9", ""], ["Конверсия", "4.1%", "+0.3"]]},
            {"t": "table", "cols": ["ДАТА", "КОНТАКТ", "ИСТОЧНИК", "СТАТУС"], "rows": [
                ["сегодня", "ivan@vega.example", "landing/agents", {"badge": "new", "color": "warning"}],
                ["вчера", "+7 900 …", "demo", {"badge": "call", "color": "info"}],
                ["12.05", "maria@corp.ru", "blog", {"badge": "done", "color": "success"}]]}]),
        _sc("platform-tracing", "Трейсинг — спаны", [
            {"t": "stats", "items": [["Спанов/час", "48K", ""], ["p95 latency", "212 мс", "-18"], ["Ошибок", "0.4%", ""], ["Трейсов", "12 400", ""]]},
            {"t": "table", "cols": ["ОПЕРАЦИЯ", "СЕРВИС", "P95", "ОШИБКИ"], "rows": [
                ["llm.complete", "flows", "3.8 с", "0.1%"],
                ["sync/messages/send", "sync", "84 мс", "0%"],
                ["op_entities_search", "crm", "120 мс", "0.2%"],
                ["embedding", "litserve", "62 мс", "0%"]]}]),
        _sc("crawl-report", "SEO — отчёт краула", [
            {"t": "stats", "items": [["Страниц", "312", "+4"], ["Проиндексировано", "298", ""], ["Ошибок", "3", "-2"], ["sitemap", "актуален", ""]]},
            {"t": "table", "cols": ["URL", "СТАТУС", "ИНДЕКС", "ОБНОВЛЁН"], "rows": [
                ["/products/agents", "200", {"badge": "ok", "color": "success"}, "сегодня"],
                ["/blog/flows-runtime", "200", {"badge": "ok", "color": "success"}, "вчера"],
                ["/old-pricing", "404", {"badge": "fix", "color": "error"}, "—"]]}]),
        _sc("scheduler-tasks", "Планировщик задач", [
            {"t": "table", "cols": ["ЗАДАЧА", "РАСПИСАНИЕ", "ПОСЛЕДНИЙ ЗАПУСК", "СТАТУС"], "rows": [
                ["seo.sitemap.rebuild", "0 4 * * *", "сегодня 04:00", {"badge": "ok", "color": "success"}],
                ["billing.settlement", "*/15 * * * *", "12:45", {"badge": "ok", "color": "success"}],
                ["rag.reembed.queue", "*/30 * * * *", "12:30", {"badge": "ok", "color": "success"}],
                ["cleanup.retention", "0 2 * * 0", "вс 02:00", {"badge": "ok", "color": "success"}]]}]),
        _sc("access", "Запрос доступа", [
            {"t": "form", "narrow": True, "title": "Запрос доступа", "fields": ["Email", "Компания", "Роль", "Комментарий"], "submit": "Отправить", "cancel": "Отмена"}], shell=False),

        _sc("dashboard-mobile", "Дашборд (mobile)", [
            {"t": "stats", "items": [["Сервисов", "12", ""], ["Сообщений", "8.4K", "+4%"]]},
            {"t": "cards", "cols": 2, "items": [
                {"title": "Синк", "sub": "3 новых", "icon": "✉", "h": 110},
                {"title": "Задачи", "sub": "4 открытых", "icon": "✓", "h": 110},
                {"title": "Flows", "sub": "12 активных", "icon": "⚡", "h": 110},
                {"title": "Документы", "sub": "8 обновлено", "icon": "▤", "h": 110}]}], mobile=True),
        _sc("login-mobile", "Вход (mobile)", [
            {"t": "form", "title": "Вход в Linnex", "fields": ["Email", "Пароль"], "submit": "Войти", "cancel": "Создать аккаунт"}], mobile=True)
    ],
    "crm": [
        _sc("access-requests", "Заявки на доступ", [
            {"t": "table", "cols": ["ПОЛЬЗОВАТЕЛЬ", "ПРОСТРАНСТВО", "РОЛЬ", "СТАТУС", ""], "rows": [
                ["igor@vega.example", "Продажи", "editor", {"badge": "new", "color": "warning"}, "✓ ✗"],
                ["maria@corp.ru", "Партнёры", "viewer", {"badge": "approved", "color": "success"}, "—"]]}]),
        _sc("entity-new", "Создание сущности", [
            {"t": "form", "title": "Новая сущность", "fields": ["Тип (company/person/deal)", "Название", "Namespace", "Связи"], "submit": "Создать"}]),
        _sc("namespace-detail", "Пространство — детали", [
            {"t": "detail", "title": "Продажи", "badge": "namespace", "actions": [["Настройки", True]], "rows": [
                ["Сущностей", "1 204"], ["Участников", "6"], ["Интеграций", "2"], ["Создано", "12.03.2025"]],
                "side": ["Быстрые действия", ["+ Сущность", "+ Заметка", "Импорт", "Шаблоны"]]}]),
        _sc("namespace-imports", "Импорт в пространство", [
            {"t": "form", "title": "Импорт данных", "fields": ["Источник (csv/amo/bitrix)", "Файл", "Маппинг полей", "Namespace"], "submit": "Запустить импорт"},
            {"t": "table", "cols": ["ИМПОРТ", "ЗАПИСЕЙ", "СТАТУС"], "rows": [
                ["amo-export.csv", "412", {"badge": "done", "color": "success"}],
                ["contacts.csv", "96", {"badge": "errors: 3", "color": "warning"}]]}]),
        _sc("integrations", "Интеграции пространства", [
            {"t": "cards", "cols": 3, "items": [
                {"title": "Telegram-бот", "sub": "заявки → сущности", "badge": "on", "badgeColor": "success", "icon": "TG"},
                {"title": "Email-парсер", "sub": "письма → заметки", "badge": "on", "badgeColor": "success", "icon": "@"},
                {"title": "Webhook", "sub": "входящие события", "badge": "off", "badgeColor": "info", "icon": "↯"}]}]),
        _sc("note-detail", "Заметка — деталь + AI-анализ", [
            {"t": "split", "h": 660, "items": [
                {"title": "Созвон по договору", "sub": "ООО «Вега»", "active": True},
                {"title": "Пожелания к интеграции", "sub": ""}],
                "detail": "Созвон по договору", "lines": [
                    "Клиент просит отсрочку 14 дней.",
                    "AI-анализ: 2 action item → WT-812, WT-813.",
                    "Связи: ООО «Вега», ИП Соколов, Счёт №1042.",
                    "Sentiment: позитивный, риск — сроки оплаты."]}]),
        _sc("relationship-types", "Типы связей", [
            {"t": "table", "cols": ["ТИП", "ОТ → К", "СВЯЗЕЙ", "СИСТЕМНЫЙ"], "rows": [
                ["director_of", "person → company", "48", {"badge": "core", "color": "info"}],
                ["owns", "company → deal", "124", {"badge": "core", "color": "info"}],
                ["contacted", "user → entity", "2 310", {"badge": "auto", "color": "success"}],
                ["partner", "company → company", "17", "custom"]]}]),
        _sc("services", "CRM — сервисные страницы", [
            {"t": "list", "items": [
                {"title": "Сущности", "sub": "4 812 записей", "icon": "◆"},
                {"title": "Заметки", "sub": "1 208", "icon": "✎"},
                {"title": "Задачи", "sub": "142 открытых", "icon": "✓"},
                {"title": "Граф", "sub": "визуализация", "icon": "◉"},
                {"title": "Пространства", "sub": "3 активных", "icon": "▤"}]}]),
        _sc("settings", "Настройки CRM", [
            {"t": "form", "title": "NetWorkle", "fields": ["Namespace по умолчанию", "AI-анализ заметок", "Авто-связи", "Ретенция истории"], "submit": "Сохранить"}]),
        _sc("suggests", "Подсказки и дедупликация", [
            {"t": "list", "items": [
                {"title": "ООО «Вега» ≈ «ВЕГА» ООО", "sub": "похожесть 0.94 — объединить?", "badge": "merge", "badgeColor": "warning", "icon": "⇄"},
                {"title": "ИП Соколов → добавить в Продажи", "sub": "suggest по активности", "badge": "new", "badgeColor": "info", "icon": "+"},
                {"title": "3 заметки без связей", "sub": "привязать к сущностям", "icon": "✎"}]}]),

        _sc("entities-mobile", "Сущности (mobile)", [
            {"t": "toolbar", "search": "Искать…"},
            {"t": "list", "items": [
                {"title": "ООО «Вега»", "sub": "company · 18 связей", "icon": "В", "grad": True, "badge": "co", "badgeColor": "info"},
                {"title": "ИП Соколов", "sub": "person · 7", "icon": "С", "badge": "p", "badgeColor": "success"},
                {"title": "АО «ТрансНефть»", "sub": "company · 42", "icon": "Т"},
                {"title": "Марина Орлова", "sub": "person · 3", "icon": "О"}]}], mobile=True)
    ],
    "flows": [
        _sc("branch", "Flow — ветка preview", [
            {"t": "editor", "h": 420, "nodes": [
                ["Триггер", 60, 60, "trigger"], ["LLM · v2-draft", 330, 140, "llm_node"],
                ["Ветка A/B", 620, 60, "condition"], ["Ответ v2", 910, 140, "output"]],
                "links": [[0, 1], [1, 2], [2, 3]]},
            {"t": "toolbar", "actions": [["Сравнить с main", False], ["Мерж", True]]}]),
        _sc("profile", "Профиль агента (flow_employee)", [
            {"t": "detail", "title": "Lara — flow-сотрудник", "badge": "agent", "badgeColor": "success", "actions": [["inbox", True]], "rows": [
                ["Flow", "Support Agent"], ["Статус", "онлайн 24/7"], ["Задач выполнено", "1 204"],
                ["Inbox", "3 необработанных"], ["Доступы", "crm.read, sync.write"]],
                "side": ["Активность", ["→ ответ в #general (2 мин)", "→ WT-802 ждёт HITL", "→ 12 сессий сегодня"]]}]),
        _sc("structured-output", "Structured output — схема", [
            {"t": "form", "title": "Схема ответа LLM", "fields": ["JSON Schema", "Строгий режим", "Пример ответа"], "submit": "Сохранить"},
            {"t": "text", "lines": ["{", '  "intent": "refund | question | escalate",', '  "confidence": "number 0..1",', '  "draft": "string"', "}"]}]),
        _sc("services", "Flows — сервисы рантайма", [
            {"t": "list", "items": [
                {"title": "Workflow runtime", "sub": "ledger + reducer · ok", "badge": "ok", "badgeColor": "success", "icon": "⚙"},
                {"title": "capability-gateway", "sub": "sandbox exec · ok", "badge": "ok", "badgeColor": "success", "icon": "⛨"},
                {"title": "MCP provisioner", "sub": "12 серверов", "badge": "ok", "badgeColor": "success", "icon": "M"},
                {"title": "Eval runner", "sub": "очередь: 0", "icon": "∑"}]}]),

        _sc("list-mobile", "Flows (mobile)", [
            {"t": "list", "items": [
                {"title": "Support Agent", "sub": "1 240 запусков", "badge": "on", "badgeColor": "success", "icon": "⚡"},
                {"title": "Lead Qualifier", "sub": "856", "badge": "on", "badgeColor": "success", "icon": "⚡"},
                {"title": "Invoice Watcher", "sub": "64", "badge": "пауза", "badgeColor": "warning", "icon": "⚡"}]}], mobile=True)
    ],
    "office": [
        _sc("embed", "Встроенный редактор (embed)", [
            {"t": "toolbar", "actions": [["Сохранить", True], ["⋯", False]]},
            {"t": "text", "lines": [
                "Спецификация к договору №1042",
                "",
                "Поз. 1 — Лицензия Linnex Team ×15 … ₽180 000",
                "Поз. 2 — Внедрение и онбординг … ₽96 000",
                "",
                "— редактируют: Анна К. (сейчас)"]}]),
        _sc("services", "Документы — сервисы", [
            {"t": "list", "items": [
                {"title": "FilesService", "sub": "S3 · seaweedfs", "badge": "ok", "badgeColor": "success", "icon": "S3"},
                {"title": "OnlyOffice BFF", "sub": "редактор", "badge": "ok", "badgeColor": "success", "icon": "OO"},
                {"title": "RAG-индекс каталога", "sub": "12k чанков", "icon": "🧠"}]}]),

        _sc("recent-mobile", "Документы (mobile)", [
            {"t": "list", "items": [
                {"title": "Отчёт Q2.xlsx", "sub": "сегодня", "icon": "X", "grad": True},
                {"title": "Договор-1042.docx", "sub": "вчера · Анна К.", "icon": "D"},
                {"title": "Презентация.pptx", "sub": "12 мая", "icon": "P"},
                {"title": "Акт.pdf", "sub": "10 мая", "icon": "F"}]}], mobile=True)
    ],
    "worktracker": [
        _sc("queue-detail", "Очередь flows-hitl", [
            {"t": "stats", "items": [["Открыто", "4", ""], ["SLA breach", "0", ""], ["Ср. время", "38 мин", "-12"], ["Назначено агентам", "2", ""]]},
            {"t": "table", "cols": ["ЗАДАЧА", "НАЗНАЧЕНА", "SLA", "СТАТУС"], "rows": [
                ["WT-802 · одобрить шаг", "Виктор Ш.", "40 мин", {"badge": "waiting", "color": "warning"}],
                ["WT-815 · webhook 500", "Анна К.", "2 ч", {"badge": "working", "color": "info"}],
                ["WT-818 · ревью схемы", "—", "4 ч", {"badge": "new", "color": "warning"}]]}]),

        _sc("my-mobile", "Мои задачи (mobile)", [
            {"t": "list", "items": [
                {"title": "WT-802: одобрить HITL-шаг", "sub": "ждёт 2 ч", "badge": "HITL", "badgeColor": "warning", "icon": "⚡"},
                {"title": "WT-790: ревью договора", "sub": "до пт", "icon": "📄"},
                {"title": "WT-815: webhook 500-е", "sub": "high", "badge": "bug", "badgeColor": "error", "icon": "🐞"}]}], mobile=True)
    ],
    "wiki": [
        _sc("search", "Поиск по wiki", [
            {"t": "toolbar", "search": "релизный процесс…", "actions": [["Найти", True]]},
            {"t": "list", "items": [
                {"title": "Релизный процесс", "sub": "Инженерия · совпадение в §2", "icon": "📄", "badge": "0.96", "badgeColor": "success"},
                {"title": "Runbooks — деплой", "sub": "Инженерия · §1", "icon": "📄", "badge": "0.81", "badgeColor": "info"},
                {"title": "Продукт — roadmap", "sub": "Продукт", "icon": "📄"}]}])],
    "stock": [
        _sc("transfer-detail", "Трансфер TR-1042 — деталь", [
            {"t": "detail", "title": "TR-1042", "badge": "принят", "actions": [["Печать", False], ["Правка", True]], "rows": [
                ["Откуда", "Поставщик «Альфа»"], ["Куда", "Основной склад"], ["Позиций", "24"],
                ["Сумма", "₽86 400"], ["Принял", "Анна К."], ["Дата", "сегодня 11:20"]],
                "side": ["Позиции", ["×6 Моцарелла 2кг", "×12 Мука в/с 25кг", "×6 Лосось с/с"]]}])],
    "sync": [
        _sc("channel-mobile", "Канал (mobile)", [
            {"t": "list", "items": [
                {"title": "# general", "sub": "1 240 сообщений", "badge": "3", "badgeColor": "warning", "icon": "#"},
                {"title": "# flows-алерты", "sub": "98", "icon": "#"},
                {"title": "@ Lara", "sub": "агент · онлайн", "icon": "L", "grad": True},
                {"title": "@ Поддержка", "sub": "12", "icon": "@"}]}], mobile=True),
        _sc("chat-mobile", "Диалог (mobile)", [
            {"t": "chat", "msgs": [
                {"who": "АК", "text": "Отчёт готов — в Документах.", "time": "09:12"},
                {"who": "·", "text": "Lara, сводку по алертам.", "time": "09:15", "mine": True},
                {"who": "L", "text": "Готово: 3 инцидента, все закрыты.", "time": "09:15"}]}], mobile=True),
        _sc("scheduled-calls", "Запланированные звонки", [
            {"t": "table", "cols": ["ЗВОНОК", "ВРЕМЯ", "УЧАСТНИКИ", "ССЫЛКА"], "rows": [
                ["Ежедневный стендап", "завтра 10:00", "5", "linnex.link/std-9f2"],
                ["Демо «Вега»", "пт 15:00", "4", "linnex.link/veg-77b"],
                ["Ретро спринта", "через нед.", "8", "linnex.link/ret-00c"]]}]),
        _sc("services", "Sync — сервисы", [
            {"t": "list", "items": [
                {"title": "LiveKit", "sub": "медиа-сервер · ok", "badge": "ok", "badgeColor": "success", "icon": "LK"},
                {"title": "Запись звонков", "sub": "в S3 · on", "badge": "on", "badgeColor": "success", "icon": "⏺"},
                {"title": "Voice gateway", "sub": "STT/TTS · 8015", "icon": "🎙"}]}]),
    ],    "wiki": [
        _sc("search", "Поиск по wiki", [
            {"t": "toolbar", "search": "релизный процесс…", "actions": [["Найти", True]]},
            {"t": "list", "items": [
                {"title": "Релизный процесс", "sub": "Инженерия · совпадение в §2", "icon": "📄", "badge": "0.96", "badgeColor": "success"},
                {"title": "Runbooks — деплой", "sub": "Инженерия · §1", "icon": "📄", "badge": "0.81", "badgeColor": "info"},
                {"title": "Продукт — roadmap", "sub": "Продукт", "icon": "📄"}]}]),
        _sc("page-mobile", "Страница wiki (mobile)", [
            {"t": "text", "lines": [
                "Релизный процесс",
                "",
                "1. Ветка release/* от main.",
                "2. Гейты: lint → test → e2e.",
                "3. Canary 10% → 100%.",
                "4. Rollback — helm rollback."]}], mobile=True)
    ],
    "shop": [

        _sc("menu-mobile", "Меню (mobile)", [
            {"t": "toolbar", "search": "Найти блюдо…"},
            {"t": "cards", "cols": 2, "items": [
                {"title": "Маргарита", "sub": "420 ₽", "icon": "🍕", "h": 130},
                {"title": "Филадельфия", "sub": "590 ₽", "icon": "🍣", "h": 130},
                {"title": "Цезарь", "sub": "380 ₽", "icon": "🥗", "h": 130},
                {"title": "Тирамису", "sub": "290 ₽", "icon": "🍰", "h": 130}]}], mobile=True)
    ],
    "geo": [

        _sc("map-mobile", "Карта (mobile)", [
            {"t": "map", "h": 480, "pins": [[60, 400, "Склад", "accent"], [300, 100, "Клиент", "accent/secondary"]]}], mobile=True)
    ],
    "rag": [

        _sc("search-mobile", "Поиск (mobile)", [
            {"t": "toolbar", "search": "Запрос…"},
            {"t": "list", "items": [
                {"title": "runbook/tls.md", "sub": "score 0.94", "badge": "0.94", "badgeColor": "success", "icon": "§"},
                {"title": "infra.md", "sub": "score 0.87", "badge": "0.87", "badgeColor": "info", "icon": "§"}]}], mobile=True)
    ],

}



def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.tools.figma_screens")
    parser.add_argument("service", choices=[*SCREENS.keys(), "all"])
    parser.add_argument("--file-key", default="")
    parser.add_argument("--wait-plugin", type=float, default=30)
    ns = parser.parse_args()
    services = list(SCREENS) if ns.service == "all" else [ns.service]
    file_key = str(ns.file_key or "") or _project_file_key()
    server = _Server()
    try:
        if not server.start():
            print("screens: figma-console-mcp не инициализировался", file=sys.stderr)
            return 2
        _require_design_file(server, file_key or None, wait=float(ns.wait_plugin or 30))
        for svc in services:
            payload = _payload(svc)
            code = _RENDER_JS.replace("SPEC", json.dumps(payload, ensure_ascii=True), 1)
            result = _figma_exec(server, code, timeout_ms=300_000)
            print(f"{svc}: {json.dumps(result, ensure_ascii=False)[:300]}", flush=True)
        return 0
    finally:
        server.stop()




MODAL_SCREENS: dict[str, list[Json]] = {
    "frontend": [
        _modal("topup", "Пополнение баланса", ["Сумма, ₽", "Способ оплаты", "Промокод"], "Пополнить"),
        _modal("create-api-key", "Новый API-ключ", ["Имя", "Scopes (через запятую)", "TTL"], "Создать",
               checks=[["read", True], ["flows.run", True], ["write", False]]),
        _modal("embed-code", "Код виджета", ["Домен", "Flow", "Тема виджета"], "Скопировать"),
        _modal("namespace-create", "Новое пространство", ["Название", "Описание", "Видимость"], "Создать"),
        _modal("crawl-profile", "Профиль краула", ["Домен", "Глубина", "Расписание", "Robots"], "Сохранить"),
        _modal("lead-form", "Форма заявки", ["Имя", "Email", "Компания", "Сообщение"], "Отправить"),
        _modal("balance-grant", "Выдать грант", ["Компания", "Сумма", "Причина", "Истекает"], "Выдать"),
        _modal("ai-provider", "AI-провайдер", ["Провайдер", "API key", "Модель по умолчанию", "Лимит RPM"], "Подключить"),
        _modal("scheduler-task", "Задача планировщика", ["Имя задачи", "Cron", "Payload", "Очередь"], "Создать"),
        _modal("system-access", "Доступ system", ["Пользователь", "Scope", "Причина"], "Выдать"),
  
        _modal("crawl-domain-add", "Домен для краула", ["Домен", "Профиль", "Sitemap"], "Добавить"),
        _modal("crawl-domain-edit", "Настройки домена", ["Профиль", "Частота", "Исключения"], "Сохранить"),
        _modal("crawl-url-add", "URL для краула", ["URL", "Приоритет"], "Добавить"),
        _modal("crawl-url-detail", "URL — детали краула", ["URL", "Статус", "Последний краул"], "Обновить"),
        _modal("edit-api-key", "Правка API-ключа", ["Имя", "Scopes", "TTL"], "Сохранить"),
        _modal("create-embed", "Новый embed", ["Имя", "Flow", "Домены"], "Создать"),
    ],
    "crm": [
        _modal("access-request", "Запрос доступа в пространство", ["Пространство", "Роль", "Комментарий"], "Отправить"),
        _modal("ai-analysis", "AI-анализ заметки", ["Заметка", "Экстракт сущностей", "Создать задачи"], "Запустить"),
        _modal("entity-merge", "Слияние сущностей", ["Донор", "Целевая", "Переносить связи"], "Объединить"),
        _modal("entity-type", "Тип сущности", ["Имя", "Иконка", "Поля", "Системный"], "Создать"),
        _modal("knowledge-import", "Импорт знаний", ["Файл", "Формат", "Пространство"], "Импортировать"),
        _modal("note-graph", "Заметка → граф", ["Связать с сущностью", "Тип связи"], "Связать"),
        _modal("share", "Поделиться", ["Пользователь / email", "Доступ (view/edit)", "Комментарий"], "Пригласить"),
        _modal("activity-task", "Задача по активности", ["Название", "Исполнитель", "Дедлайн", "Связь"], "Создать"),
        _modal("entity-delete", "Удалить сущность", ["Подтверждение имени"], "Удалить"),
        _modal("namespace", "Пространство", ["Название", "Описание", "Шаблон"], "Сохранить"),
    ],
    "flows": [
        _modal("flow-create", "Новый flow", ["Имя", "Шаблон", "Namespace", "Триггер"], "Создать"),
        _modal("branch-create", "Новая ветка", ["Имя ветки", "От", "Описание"], "Создать"),
        _modal("trigger-editor", "Редактор триггера", ["Тип", "Cron / event", "Payload", "Фильтр"], "Сохранить"),
        _modal("variable-mapping", "Маппинг переменной", ["Источник", "JSONPath", "Целевая переменная", "Transform"], "Применить"),
        _modal("mcp-servers", "MCP-серверы", ["Сервер", "Transport", "URL / command"], "Добавить"),
        _modal("sessions", "Сессии flow", ["Фильтр по статусу", "Период", "Branch"], "Показать"),
        _modal("tool-create", "Новый tool", ["Имя", "Тип (builtin/capability)", "Schema", "Теги"], "Создать"),
        _modal("skill-picker", "Выбор скила", ["Поиск по библиотеке"], "Добавить",
               extra=[{"t": "list", "items": [
                   {"title": "agent-planning", "sub": "core", "icon": "🧭"},
                   {"title": "code-review", "sub": "team", "icon": "🔍"},
                   {"title": "sql-expert", "sub": "team", "icon": "🗄"}]}]),
        _modal("api-console", "API-консоль", ["Endpoint", "Method", "Body"], "Выполнить"),
        _modal("preview-share", "Публичный preview", ["Slug", "TTL ссылки", "Пароль"], "Создать ссылку"),
        _modal("integrations", "Интеграции flow", ["Сервис", "Scope", "Ключ"], "Подключить"),
        _modal("node-run-result", "Результат ноды", ["Session", "Node", "Показать payload"], "Открыть"),
        _modal("variables", "Переменные flow", ["Имя", "Тип", "Значение по умолчанию", "Secret"], "Добавить"),
        _modal("code", "Code node", ["Язык", "Entrypoint", "Capabilities"], "Сохранить"),
        _modal("employee-settings", "Сотрудник flow", ["Имя", "Inbox-канал", "Автоназначение"], "Сохранить"),
        _modal("incoming-policy", "Входящая политика", ["Источник", "Allow-list", "Действие"], "Сохранить"),
        _modal("flow-edit", "Настройки flow", ["Имя", "Описание", "Namespace", "Теги"], "Сохранить"),
        _modal("logs", "Логи сессии", ["Session", "Уровень", "Период"], "Показать"),
        _modal("state", "ExecutionState", ["Session", "Формат (json/tree)"], "Открыть"),
        _modal("tracing", "Трейсинг flow", ["Trace ID", "Спан", "Глубина"], "Показать"),
        _modal("span-details", "Детали спана", ["Span", "Атрибуты", "Дочерние"], "Открыть"),
        _modal("edge-condition", "Условие перехода", ["Источник", "Выражение", "Иначе"], "Сохранить"),
        _modal("raw-json", "Raw JSON ноды", ["Node ID"], "Экспорт",
               extra=[{"t": "text", "lines": ['{ "type": "llm_node", "model": "linnex_llm",', '  "prompt": "…", "tools": ["crm.search"] }']}]),
        _modal("durable-history", "История durable-сессии", ["Session", "Событие от", "Limit"], "Показать"),
        _modal("canvas-help", "Горячие клавиши", [], "Закрыть",
               extra=[{"t": "list", "items": [
                   {"title": "Space + drag", "sub": "панорама", "icon": "⌨"},
                   {"title": "Del", "sub": "удалить ноду", "icon": "⌫"},
                   {"title": "Cmd+Z", "sub": "undo", "icon": "↩"}]}]),
        _modal("library-picker", "Библиотека нод", ["Поиск ноды"], "Вставить",
               extra=[{"t": "list", "items": [
                   {"title": "llm_node", "sub": "модель + промпт", "icon": "🧠"},
                   {"title": "code_node", "sub": "пользовательский код", "icon": "{}"},
                   {"title": "tool_node", "sub": "tool из реестра", "icon": "🔧"}]}]),
        _modal("embedded-tool", "Embedded tool конфиг", ["Tool", "Свойства", "Маппинг"], "Сохранить"),
        _modal("interface-template", "Шаблон интерфейса", ["Тип UI", "Грамматика", "Превью"], "Применить"),
        _modal("html-editor", "HTML-интерфейс", ["Шаблон", "CSS-vars"], "Сохранить"),
        _modal("browser-preview", "Preview в браузере", ["URL", "Ширина"], "Открыть"),
        _modal("code-docs", "Доки по code node", [], "Закрыть",
               extra=[{"t": "text", "lines": ["code node исполняет Python в песочнице.", "Capabilities: db.read, net.out, eval.code.", "Результат — в ExecutionState.outputs."]}]),
        _modal("code-node-drop", "Добавить code node", ["Скилл / шаблон", "Язык"], "Создать"),
        _modal("skill-create", "Новый скил", ["Имя", "Описание", "Зависимости"], "Создать"),
        _modal("skill-edit", "Правка скила", ["Имя", "Инструкции", "Tools"], "Сохранить"),
        _modal("skill-import", "Импорт скила", ["Файл .md", "Namespace"], "Импортировать"),
    ],
    "office": [
        _modal("catalog-create", "Новый каталог", ["Название", "Родитель", "Описание"], "Создать"),
        _modal("document-upload", "Загрузка документа", ["Файл", "Каталог", "Теги"], "Загрузить"),
        _modal("catalog-members", "Участники каталога", ["Пользователь", "Доступ"], "Пригласить"),
        _modal("office-access", "Доступ к документу", ["Email / ссылка", "Права (view/edit)", "Срок"], "Выдать"),
        _modal("catalog-rag", "RAG каталога", ["Индексировать", "Chunk size", "Reembed"], "Применить"),
        _modal("document-rename", "Переименовать", ["Новое имя"], "Переименовать"),
    ],
    "sync": [
        _modal("channel-create", "Новый канал", ["Название", "Тип (public/private)", "Участники"], "Создать"),
        _modal("members-add", "Добавить участников", ["Пользователи", "Роль"], "Добавить"),
        _modal("call-link", "Ссылка на звонок", ["Название", "TTL", "Запись"], "Создать"),
        _modal("call-incoming", "Входящий звонок", [], "Принять",
               extra=[{"t": "text", "lines": ["Виктор Швед · #general · видео"]}]),
        _modal("forward", "Переслать сообщение", ["Канал / диалог", "Комментарий"], "Переслать"),
        _modal("notifications", "Уведомления канала", ["Все / упоминания / ничего", "Тихие часы"], "Сохранить"),
        _modal("channel-edit", "Настройки канала", ["Название", "Описание", "Архивировать"], "Сохранить"),
        _modal("namespace", "Пространство Sync", ["Название"], "Сохранить"),
    ],
    "worktracker": [
        _modal("work-item-create", "Новая задача", ["Название", "Очередь", "Исполнитель", "Дедлайн", "Приоритет"], "Создать",
               checks=[["Высокий приоритет", False], ["Назначить flow-сотруднику", False]]),
        _modal("board-create", "Новая доска", ["Название", "Очереди", "Колонки"], "Создать"),
        _modal("board-settings", "Настройки доски", ["Название", "WIP-лимиты", "Автопереходы"], "Сохранить"),
    ],
    "shop": [
        _modal("product", "Товар", ["Название", "Цена", "Категория", "Фото", "Описание"], "Сохранить"),
        _modal("modifiers", "Модификаторы", ["Группа", "Опции", "Обязательность", "Лимит"], "Сохранить"),
        _modal("banner", "Баннер", ["Заголовок", "Изображение", "Ссылка", "Период"], "Опубликовать"),
        _modal("shelf", "Полка меню", ["Название", "Позиции", "Порядок"], "Сохранить"),
    ],
    "geo": [
        _modal("address-editor", "Адрес", ["Строка адреса", "Координаты", "Зона доставки", "Комментарий"], "Сохранить"),
        _modal("region-editor", "Регион / зона", ["Название", "Полигон", "Цвет", "Тариф"], "Сохранить"),
        _modal("feature-admin", "Фича карты", ["Тип", "Свойства", "Слой"], "Сохранить"),
    ],
    "rag": [
        _modal("namespace-create", "Новый namespace", ["Имя", "Модель эмбеддинга", "Chunk size", "Overlap"], "Создать"),
    ],
    "wiki": [
        _modal("move-page", "Переместить страницу", ["Новый родитель", "Сохранить редирект"], "Переместить"),
        _modal("page-access", "Доступ к странице", ["Видимость", "Пользователи", "Публичная ссылка"], "Сохранить"),
        _modal("import-report", "Отчёт импорта", ["Источник", "Страниц", "Ошибок"], "Закрыть",
               extra=[{"t": "text", "lines": ["Импортировано 24 страницы, 3 пропущены (дубли)."]}]),
    ],
}


STATE_SCREENS: dict[str, list[Json]] = {
    "frontend": [
        _sc("dashboard-empty", "Дашборд — empty", [
            {"t": "state", "icon": "🏠", "title": "Добро пожаловать в Linnex", "sub": "Подключите первый сервис, чтобы начать", "action": "Открыть каталог"}]),
        _sc("search-empty", "Поиск — пустой результат", [
            {"t": "toolbar", "search": "qwerty123…"},
            {"t": "state", "icon": "🔍", "title": "Ничего не найдено", "sub": "Попробуйте изменить запрос или область поиска"}]),
        _sc("notifications-empty", "Уведомления — пусто", [
            {"t": "state", "icon": "🔔", "title": "Всё прочитано", "sub": "Новые уведомления появятся здесь"}]),
        _sc("billing-error", "Биллинг — ошибка оплаты", [
            {"t": "state", "icon": "⚠", "title": "Платёж не прошёл", "sub": "Карта •• 4242 отклонена банком. Обновите способ оплаты.", "action": "Изменить карту"}]),
        _sc("dashboard-loading", "Дашборд — загрузка", [
            {"t": "skeleton", "n": 5}]),
    ],
    "crm": [
        _sc("entities-empty", "Сущности — empty", [
            {"t": "toolbar", "search": "Искать сущность…", "actions": [["Создать", True]]},
            {"t": "state", "icon": "◆", "title": "Сущностей пока нет", "sub": "Создайте первую или импортируйте из CSV", "action": "Создать сущность"}]),
        _sc("notes-empty", "Заметки — empty", [
            {"t": "state", "icon": "✎", "title": "Заметок нет", "sub": "Заметки появятся после первого созвона", "action": "Новая заметка"}]),
        _sc("entity-error", "Сущность — ошибка доступа", [
            {"t": "state", "icon": "⛨", "title": "Нет доступа", "sub": "Сущность в пространстве «Продажи» — запросите доступ у владельца", "action": "Запросить доступ"}]),
        _sc("graph-loading", "Граф — загрузка", [
            {"t": "skeleton", "n": 6}]),
    ],
    "flows": [
        _sc("list-empty", "Flows — empty", [
            {"t": "toolbar", "search": "Найти flow…", "actions": [["Создать flow", True]]},
            {"t": "state", "icon": "⚡", "title": "Первый flow", "sub": "Выберите шаблон или соберите с нуля", "action": "Создать flow"}]),
        _sc("session-error", "Сессия — ошибка ноды", [
            {"t": "state", "icon": "⚠", "title": "Нода crm.search упала", "sub": "HTTP 503 upstream · 3 retries · session #1040", "action": "Повторить"}]),
        _sc("editor-loading", "Редактор — загрузка", [
            {"t": "skeleton", "n": 6}]),
    ],
    "sync": [
        _sc("channel-empty", "Канал — empty", [
            {"t": "state", "icon": "✉", "title": "Тихо пока", "sub": "Начните обсуждение — первое сообщение за вами"}]),
        _sc("chat-loading", "Диалог — загрузка", [
            {"t": "skeleton", "n": 7}]),
    ],
    "office": [
        _sc("recent-empty", "Документы — empty", [
            {"t": "state", "icon": "▤", "title": "Нет документов", "sub": "Загрузите файлы или создайте документ", "action": "Загрузить"}]),
        _sc("editor-error", "Редактор — ошибка", [
            {"t": "state", "icon": "⚠", "title": "Не удалось открыть редактор", "sub": "OnlyOffice-сессия истекла — обновите страницу", "action": "Обновить"}]),
    ],
    "worktracker": [
        _sc("board-empty", "Доска — empty", [
            {"t": "toolbar", "actions": [["Новая задача", True]]},
            {"t": "state", "icon": "✓", "title": "Задач нет", "sub": "Очередь пустая — красота", "action": "Новая задача"}]),
        _sc("item-error", "Задача — не найдена", [
            {"t": "state", "icon": "🗑", "title": "WT-404 удалена", "sub": "Задача была удалена или перенесена в архив", "action": "К доске"}]),
    ],
    "shop": [
        _sc("menu-empty", "Меню — empty", [
            {"t": "state", "icon": "🍕", "title": "Меню пустое", "sub": "Добавьте позиции в конструкторе", "action": "Конструктор"}]),
        _sc("orders-empty", "Заказы — empty", [
            {"t": "state", "icon": "🧾", "title": "Заказов пока нет", "sub": "Они появятся после первого оформления"}]),
    ],
    "stock": [
        _sc("products-empty", "Товары — empty", [
            {"t": "toolbar", "search": "SKU…", "actions": [["Новый товар", True]]},
            {"t": "state", "icon": "📦", "title": "Склад пуст", "sub": "Добавьте товары или запустите импорт", "action": "Импорт"}]),
        _sc("transfer-error", "Трансфер — конфликт", [
            {"t": "state", "icon": "⚠", "title": "Остаток изменился", "sub": "По SKU-1024 недостаточно: нужно 20, есть 14.2", "action": "Пересчитать"}]),
    ],
    "geo": [
        _sc("addresses-empty", "Адреса — empty", [
            {"t": "toolbar", "search": "Адрес…", "actions": [["Импорт", True]]},
            {"t": "state", "icon": "📮", "title": "База пустая", "sub": "Импортируйте адреса клиентов", "action": "Импорт"}]),
    ],
    "rag": [
        _sc("search-empty", "Поиск — пусто", [
            {"t": "toolbar", "search": "экзотерический запрос…"},
            {"t": "state", "icon": "🧠", "title": "Нет совпадений", "sub": "Порог score 0.6 — доиндексируйте документы или уточните запрос"}]),
        _sc("namespace-error", "Индексация — ошибка", [
            {"t": "state", "icon": "⚠", "title": "Reembed упал", "sub": "embedding-сервис недоступен · 3 документа в очереди", "action": "Повторить"}]),
    ],
    "wiki": [
        _sc("page-empty", "Страница — черновик", [
            {"t": "state", "icon": "📄", "title": "Пустая страница", "sub": "Начните писать — поддерживается markdown", "action": "Редактировать"}]),
    ],
    "litserve": [
        _sc("services-error", "Воркер — падение", [
            {"t": "state", "icon": "⚠", "title": "whisper-large не поднялся", "sub": "CUDA OOM · воркер перезапускается (3/5)", "action": "Логи"}]),
    ],
}


if __name__ == "__main__":
    raise SystemExit(main())
