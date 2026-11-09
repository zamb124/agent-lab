"""Figma UI Kit — генерация страницы «🧱 UI Kit» нативными компонентами.

Компоненты собираются из спеки (1:1 с runtime-токенами `tokens.css` и
`platform-button.ts` / field-pill), заливаются через Desktop Bridge и
привязываются к переменным «Platform · Dark». Повторный прогон пересобирает
страницу — идемпотентно, без дублей.
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
)

_HELPERS_JS = r"""
const spec = SPEC;
const FONT_R = { family: 'Inter', style: 'Regular' };
const FONT_M = { family: 'Inter', style: 'Medium' };
const FONT_S = { family: 'Inter', style: 'Semi Bold' };
const FONT_B = { family: 'Inter', style: 'Bold' };
for (const f of [FONT_R, FONT_M, FONT_S, FONT_B]) await figma.loadFontAsync(f);
await figma.loadAllPagesAsync();
let page = figma.root.children.find(p => p.name === spec.page);
if (!page) {
  const p1 = figma.root.children.find(p => /^Page \d+$/.test(p.name) && p.children.length === 0);
  if (p1) { p1.name = spec.page; page = p1; }
}
if (!page) { page = figma.createPage(); page.name = spec.page; }
await page.loadAsync();
let container = page;
if (spec.zone) {
  let board = page.findOne(n => n.name === 'screens-board' && n.parent === page);
  if (!board) {
    board = figma.createFrame();
    board.name = 'screens-board';
    board.layoutMode = 'HORIZONTAL'; board.layoutWrap = 'WRAP';
    board.itemSpacing = 48; board.counterAxisSpacing = 48;
    board.paddingLeft = board.paddingTop = board.paddingRight = board.paddingBottom = 32;
    board.resize(3200, 100);
    board.primaryAxisSizingMode = 'FIXED'; board.counterAxisSizingMode = 'AUTO';
    board.fills = [{ type: 'SOLID', color: { r: 0.04, g: 0.04, b: 0.07 } }];
    page.appendChild(board);
  }
  let zone = board.children.find(n => n.name === spec.zone);
  if (!zone) {
    zone = figma.createFrame();
    zone.name = spec.zone;
    zone.layoutMode = 'VERTICAL'; zone.itemSpacing = 32;
    zone.primaryAxisSizingMode = 'AUTO'; zone.counterAxisSizingMode = 'AUTO';
    zone.fills = [];
    board.appendChild(zone);
  } else {
    for (const n of [...zone.children]) n.remove();
  }
  container = zone;
} else {
  for (const n of [...page.children]) n.remove();
}
const colls = await figma.variables.getLocalVariableCollectionsAsync();
const allVars = await figma.variables.getLocalVariablesAsync();
const V = {};
for (const c of colls) if (c.name === spec.collDark) for (const v of allVars) if (v.variableCollectionId === c.id) V[v.name] = v;
const rgba = (a) => a ? { r: a[0], g: a[1], b: a[2], a: a.length > 3 ? a[3] : 1 } : { r: 1, g: 0, b: 1, a: 1 };
const T = spec.tokens;
function tok(name) { return T[name] && T[name].Dark ? T[name].Dark : null; }
function cval(name) { const t = tok(name); return (t && typeof t === 'object' && 'r' in t) ? t : null; }
function paint(name, fallback) {
  const c = cval(name); if (c) return { type: 'SOLID', color: { r: c.r, g: c.g, b: c.b }, opacity: c.a == null ? 1 : c.a, _var: name };
  return { type: 'SOLID', color: fallback || { r: 0.5, g: 0.5, b: 0.5 } };
}
function boundFill(node, name, fallback) {
  const v = V[name];
  const fb = cval(name) || fallback || { r: 0.5, g: 0.5, b: 0.5 };
  if (v) {
    try { node.fills = [{ type: 'SOLID', color: { r: fb.r, g: fb.g, b: fb.b }, opacity: fb.a == null ? 1 : fb.a, boundVariables: { color: { type: 'VARIABLE_ALIAS', id: v.id } } }]; return; } catch (e) {}
  }
  node.fills = [{ type: 'SOLID', color: { r: fb.r, g: fb.g, b: fb.b }, opacity: fb.a == null ? 1 : fb.a }];
}
function boundStroke(node, name, fallback) {
  const c = cval(name) || fallback || { r: 1, g: 1, b: 1, a: 0.1 };
  node.strokes = [{ type: 'SOLID', color: { r: c.r, g: c.g, b: c.b }, opacity: c.a == null ? 1 : c.a }];
  node.strokeWeight = 1;
}
function bindRadius(node, name, fallback) {
  const v = V[name];
  if (v) { try { node.setBoundVariable('topLeftRadius', v); node.setBoundVariable('topRightRadius', v); node.setBoundVariable('bottomLeftRadius', v); node.setBoundVariable('bottomRightRadius', v); return; } catch (e) {} }
  const t = tok(name);
  node.cornerRadius = typeof t === 'number' ? t : (fallback || 8);
}
function txt(str, font, size, colorName, fallback) {
  const t = figma.createText();
  t.fontName = font; t.characters = str; t.fontSize = size;
  boundFill(t, colorName || 'text/primary', fallback || { r: 0.9, g: 0.9, b: 0.95 });
  return t;
}
function section(title) {
  const s = figma.createFrame();
  s.name = 'section/' + title;
  s.layoutMode = 'VERTICAL'; s.itemSpacing = 18; s.paddingLeft = s.paddingRight = s.paddingTop = s.paddingBottom = 28;
  s.primaryAxisSizingMode = 'AUTO'; s.counterAxisSizingMode = 'AUTO';
  s.fills = [{ type: 'SOLID', color: { r: 0.07, g: 0.07, b: 0.11 } }];
  s.cornerRadius = 16; s.clipsContent = false;
  s.appendChild(txt(title, FONT_S, 20, 'text/primary'));
  return s;
}
function row(gap) {
  const r = figma.createFrame();
  r.layoutMode = 'HORIZONTAL'; r.itemSpacing = gap || 12;
  r.primaryAxisSizingMode = 'AUTO'; r.counterAxisSizingMode = 'AUTO';
  r.counterAxisAlignItems = 'CENTER';
  r.fills = [];
  return r;
}
function col(gap) {
  const c = figma.createFrame();
  c.layoutMode = 'VERTICAL'; c.itemSpacing = gap || 10;
  c.primaryAxisSizingMode = 'AUTO'; c.counterAxisSizingMode = 'AUTO';
  c.fills = [];
  return c;
}
function labeled(title, node) {
  const c = col(8);
  c.appendChild(node);
  c.appendChild(txt(title, FONT_R, 10, 'text/tertiary'));
  return c;
}
function comp(name) {
  const c = figma.createComponent();
  c.name = name; c.clipsContent = false;
  return c;
}
function autoComp(name, dir, gap, pad) {
  const c = comp(name);
  c.layoutMode = dir || 'HORIZONTAL'; c.itemSpacing = gap == null ? 8 : gap;
  c.paddingLeft = c.paddingRight = c.paddingTop = c.paddingBottom = pad == null ? 0 : pad;
  c.primaryAxisSizingMode = 'AUTO'; c.counterAxisSizingMode = 'AUTO';
  c.counterAxisAlignItems = 'CENTER'; c.primaryAxisAlignItems = 'CENTER';
  return c;
}
"""

_UKIT_JS = _HELPERS_JS + r"""
// ---------- Button ----------
function makeButton(variant, label, bgName, textName, opts) {
  const b = autoComp('Button/' + variant, 'HORIZONTAL', 8, 0);
  b.paddingLeft = b.paddingRight = 24; b.paddingTop = b.paddingBottom = 8;
  bindRadius(b, 'btn/radius', 22);
  if (opts && opts.hover) {
    boundFill(b, bgName, { r: 0.53, g: 0.58, b: 0.94 });
  } else {
    boundFill(b, bgName, { r: 0.6, g: 0.65, b: 0.98 });
  }
  if (opts && opts.transparent) b.fills = [];
  if (opts && opts.glow) b.effects = [{ type: 'DROP_SHADOW', color: opts.glow, offset: { x: 0, y: 0 }, radius: 10, spread: 0, visible: true, blendMode: 'NORMAL' }];
  const t = txt(label || 'Действие', FONT_R, 16, textName);
  b.appendChild(t);
  return b;
}
// ---------- FieldPill ----------
function makeField(variant) {
  const f = autoComp('Field/' + variant, 'VERTICAL', 4, 0);
  f.primaryAxisAlignItems = 'MIN'; f.counterAxisAlignItems = 'MIN';
  if (variant === 'Compact') { f.paddingLeft = f.paddingRight = 12; f.paddingTop = f.paddingBottom = 6; bindRadius(f, 'radius/md', 12); }
  else { f.paddingLeft = f.paddingRight = 18; f.paddingTop = f.paddingBottom = 14; bindRadius(f, 'field/pill/radius', 18); }
  boundFill(f, 'field/pill/bg', { r: 1, g: 1, b: 1, a: 0.05 });
  boundStroke(f, 'field/pill/border');
  f.resize(320, f.height);
  f.counterAxisSizingMode = 'FIXED';
  if (variant === 'Resting') {
    f.layoutMode = 'HORIZONTAL'; f.counterAxisAlignItems = 'CENTER'; f.itemSpacing = 8;
    f.appendChild(txt('Искать или ввести…', FONT_R, 17, 'field/pill/resting/color'));
  } else {
    f.appendChild(txt('НАЗВАНИЕ', FONT_M, 11, 'field/pill/label/color'));
    f.appendChild(txt('Значение поля', FONT_M, 17, 'field/pill/input/color'));
    if (variant === 'Hint') f.appendChild(txt('Подсказка под полем', FONT_R, 12, 'field/pill/hint/color'));
  }
  return f;
}
// ---------- Card ----------
function makeCard(variant, fillName, elevated) {
  const c = autoComp('Card/' + variant, 'VERTICAL', 8, 20);
  c.primaryAxisAlignItems = 'MIN'; c.counterAxisAlignItems = 'MIN';
  bindRadius(c, 'radius/xl', 20);
  boundFill(c, fillName, { r: 1, g: 1, b: 1, a: 0.05 });
  boundStroke(c, 'glass/border/subtle');
  c.resize(220, c.height); c.counterAxisSizingMode = 'FIXED';
  const effs = [{ type: 'BACKGROUND_BLUR', radius: 12, visible: true }];
  if (elevated) effs.push({ type: 'DROP_SHADOW', color: { r: 0, g: 0, b: 0, a: 0.35 }, offset: { x: 0, y: 8 }, radius: 24, spread: 0, visible: true, blendMode: 'NORMAL' });
  c.effects = effs;
  c.appendChild(txt(variant, FONT_S, 14, 'text/primary'));
  c.appendChild(txt(fillName.replaceAll('/', ' · '), FONT_R, 10, 'text/tertiary'));
  return c;
}
// ---------- Badge ----------
function makeBadge(variant, label, textName, bgName) {
  const b = autoComp('Badge/' + variant, 'HORIZONTAL', 6, 0);
  b.paddingLeft = b.paddingRight = 10; b.paddingTop = b.paddingBottom = 4;
  b.cornerRadius = 999;
  if (bgName) boundFill(b, bgName, { r: 0.6, g: 0.65, b: 0.98, a: 0.15 });
  else boundStroke(b, 'glass/border/medium');
  const t = txt(label, FONT_M, 11, textName);
  b.appendChild(t);
  return b;
}
// ---------- Avatar ----------
function makeAvatar(size, initials, gradient) {
  const a = comp('Avatar/' + size + (gradient ? ' Gradient' : ''));
  a.resize(size, size); a.cornerRadius = size / 2;
  a.layoutMode = 'HORIZONTAL'; a.primaryAxisAlignItems = 'CENTER'; a.counterAxisAlignItems = 'CENTER';
  if (gradient) {
    a.fills = [{ type: 'GRADIENT_LINEAR', gradientTransform: [[1, -1, 0.5], [1, 1, 0.5]], gradientStops: [{ color: { r: 0.6, g: 0.65, b: 0.98, a: 1 }, position: 0 }, { color: { r: 0.55, g: 0.36, b: 0.96, a: 1 }, position: 1 }] }];
  } else {
    boundFill(a, 'glass/tint/strong', { r: 1, g: 1, b: 1, a: 0.08 });
    boundStroke(a, 'glass/border/medium');
  }
  const t = txt(initials, FONT_M, Math.round(size * 0.4), gradient ? 'platform/btn/primary/text' : 'text/secondary');
  a.appendChild(t);
  return a;
}
// ---------- ListRow ----------
function makeListRow(variant, title, sub) {
  const r = autoComp('ListRow/' + variant, 'HORIZONTAL', 12, 0);
  r.paddingLeft = r.paddingRight = 16; r.paddingTop = r.paddingBottom = 12;
  r.counterAxisAlignItems = 'CENTER'; r.primaryAxisAlignItems = 'MIN';
  bindRadius(r, 'radius/md', 12);
  r.resize(360, r.height); r.primaryAxisSizingMode = 'FIXED';
  if (variant === 'Selected') { boundFill(r, 'crm/selected/bg', { r: 0.6, g: 0.65, b: 0.98, a: 0.2 }); boundStroke(r, 'platform/btn/primary/bg'); }
  else r.fills = [];
  const icon = figma.createFrame();
  icon.resize(36, 36); icon.cornerRadius = 10;
  boundFill(icon, 'glass/tint/medium', { r: 1, g: 1, b: 1, a: 0.05 });
  icon.layoutMode = 'HORIZONTAL'; icon.primaryAxisAlignItems = 'CENTER'; icon.counterAxisAlignItems = 'CENTER';
  icon.appendChild(txt('◆', FONT_R, 14, 'accent'));
  r.appendChild(icon);
  const texts = col(2);
  texts.layoutAlign = 'STRETCH'; texts.layoutGrow = 1;
  texts.appendChild(txt(title, FONT_M, 14, 'text/primary'));
  texts.appendChild(txt(sub, FONT_R, 12, 'text/tertiary'));
  r.appendChild(texts);
  r.appendChild(txt('›', FONT_R, 18, 'text/tertiary'));
  return r;
}
// ---------- Table ----------
function makeTable() {
  const t = comp('Table/Default');
  t.layoutMode = 'VERTICAL'; t.itemSpacing = 0;
  t.primaryAxisSizingMode = 'AUTO'; t.counterAxisSizingMode = 'AUTO';
  bindRadius(t, 'radius/md', 12);
  boundFill(t, 'glass/solid/subtle', { r: 0.11, g: 0.11, b: 0.18, a: 0.75 });
  boundStroke(t, 'glass/border/subtle');
  t.clipsContent = true;
  t.resize(560, t.height); t.counterAxisSizingMode = 'FIXED';
  const widths = [200, 120, 120, 90];
  const mkRow = (cells, head) => {
    const r = figma.createFrame();
    r.layoutMode = 'HORIZONTAL'; r.itemSpacing = 0;
    r.paddingLeft = r.paddingRight = 16; r.paddingTop = r.paddingBottom = head ? 12 : 13;
    r.primaryAxisSizingMode = 'AUTO'; r.counterAxisSizingMode = 'FIXED';
    r.resize(560, 40); r.counterAxisAlignItems = 'CENTER';
    r.fills = head ? [{ type: 'SOLID', color: { r: 1, g: 1, b: 1, a: 0.03 } }] : [];
    if (!head) r.strokes = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1, a: 0.06 } }], r.strokeWeight = 1, r.strokeAlign = 'INSIDE';
    cells.forEach((cstr, i) => {
      const cell = figma.createFrame(); cell.fills = [];
      cell.layoutMode = 'HORIZONTAL'; cell.counterAxisAlignItems = 'CENTER';
      cell.primaryAxisSizingMode = 'FIXED'; cell.counterAxisSizingMode = 'FIXED';
      cell.resize(widths[i], 20);
      cell.appendChild(txt(cstr, head ? FONT_M : FONT_R, head ? 11 : 13, head ? 'text/tertiary' : 'text/secondary'));
      r.appendChild(cell);
    });
    return r;
  };
  t.appendChild(mkRow(['НАЗВАНИЕ', 'СТАТУС', 'ОБНОВЛЕНО', ''], true));
  t.appendChild(mkRow(['Счёт №1042', 'Оплачен', '2 часа назад', '›'], false));
  t.appendChild(mkRow(['Поставка Б-17', 'В пути', 'Вчера', '›'], false));
  t.appendChild(mkRow(['Договор аренды', 'Черновик', '12 мая', '›'], false));
  return t;
}
// ---------- Modal ----------
function makeModal() {
  const m = comp('Modal/Default');
  m.layoutMode = 'VERTICAL'; m.itemSpacing = 16;
  m.paddingLeft = m.paddingRight = m.paddingTop = m.paddingBottom = 24;
  m.primaryAxisSizingMode = 'AUTO'; m.counterAxisSizingMode = 'FIXED';
  m.resize(420, 200);
  bindRadius(m, 'radius/2xl', 24);
  boundFill(m, 'glass/solid/strong', { r: 0.16, g: 0.16, b: 0.25, a: 0.92 });
  boundStroke(m, 'glass/border/medium');
  m.effects = [
    { type: 'BACKGROUND_BLUR', radius: 20, visible: true },
    { type: 'DROP_SHADOW', color: { r: 0, g: 0, b: 0, a: 0.45 }, offset: { x: 0, y: 16 }, radius: 48, spread: 0, visible: true, blendMode: 'NORMAL' },
  ];
  const head = figma.createFrame(); head.layoutMode = 'HORIZONTAL'; head.counterAxisAlignItems = 'CENTER';
  head.primaryAxisSizingMode = 'AUTO'; head.counterAxisSizingMode = 'FIXED'; head.resize(372, 28); head.fills = [];
  head.appendChild(txt('Создать сущность', FONT_S, 18, 'text/primary'));
  const spacer = figma.createFrame(); spacer.fills = []; spacer.layoutGrow = 1; spacer.resize(10, 10); head.appendChild(spacer);
  head.appendChild(txt('✕', FONT_R, 14, 'text/tertiary'));
  m.appendChild(head);
  const fld = makeField('Filled').createInstance(); fld.name = 'field'; fld.layoutAlign = 'STRETCH'; m.appendChild(fld);
  const foot = row(12); foot.primaryAxisAlignItems = 'MAX';
  const cancelB = makeButton('Ghost', 'Отмена', 'glass/tint/subtle', 'text/secondary'); cancelB.fills = [];
  const okB = makeButton('Primary', 'Сохранить', 'platform/btn/primary/bg', 'platform/btn/primary/text');
  foot.appendChild(cancelB.createInstance()); foot.appendChild(okB.createInstance());
  m.appendChild(foot);
  return m;
}
// ---------- Toast ----------
function makeToast(variant, text, dotName) {
  const t = autoComp('Toast/' + variant, 'HORIZONTAL', 10, 0);
  t.paddingLeft = 16; t.paddingRight = 18; t.paddingTop = t.paddingBottom = 12;
  t.cornerRadius = 999;
  boundFill(t, 'glass/solid/strong', { r: 0.16, g: 0.16, b: 0.25, a: 0.95 });
  boundStroke(t, 'glass/border/medium');
  t.effects = [{ type: 'DROP_SHADOW', color: { r: 0, g: 0, b: 0, a: 0.4 }, offset: { x: 0, y: 8 }, radius: 24, spread: 0, visible: true, blendMode: 'NORMAL' }];
  const dot = figma.createEllipse(); dot.resize(8, 8); boundFill(dot, dotName, { r: 0.06, g: 0.72, b: 0.5 });
  t.appendChild(dot);
  t.appendChild(txt(text, FONT_M, 13, 'text/primary'));
  return t;
}
// ---------- build ----------
try {
const root = figma.createFrame();
root.name = 'uikit-board';
root.layoutMode = 'HORIZONTAL'; root.layoutWrap = 'WRAP'; root.itemSpacing = 32; root.counterAxisSpacing = 32;
root.paddingLeft = root.paddingTop = root.paddingRight = root.paddingBottom = 32;
root.resize(2600, 100);
root.primaryAxisSizingMode = 'FIXED'; root.counterAxisSizingMode = 'AUTO';
root.fills = [{ type: 'SOLID', color: { r: 0.05, g: 0.05, b: 0.08 } }];
const headCol = col(8);
headCol.appendChild(txt('Linnex · Liquid Glass — UI Kit', FONT_S, 28, 'text/primary'));
headCol.appendChild(txt('Нативные компоненты 1:1 с platform-button / field-pill, привязаны к «Platform · Dark»', FONT_R, 13, 'text/secondary'));
root.appendChild(headCol);
const btns = section('Кнопки — PlatformButton');
const bRow1 = row(12);
bRow1.appendChild(labeled('primary', makeButton('Primary', 'Сохранить', 'platform/btn/primary/bg', 'platform/btn/primary/text')));
bRow1.appendChild(labeled('primary:hover', makeButton('Primary Hover', 'Сохранить', 'platform/btn/primary/bg/hover', 'platform/btn/primary/text', { glow: { r: 0.6, g: 0.65, b: 0.98, a: 0.6 } })));
bRow1.appendChild(labeled('accent', makeButton('Accent', 'Заказать', 'platform/btn/accent/bg', 'platform/btn/accent/text')));
bRow1.appendChild(labeled('accent:hover', makeButton('Accent Hover', 'Заказать', 'platform/btn/accent/bg/hover', 'platform/btn/accent/text', { glow: { r: 1, g: 0.53, b: 0.36, a: 0.6 } })));
btns.appendChild(bRow1);
const bRow2 = row(12);
bRow2.appendChild(labeled('secondary', makeButton('Secondary', 'Подробнее', 'platform/btn/secondary/bg', 'platform/btn/secondary/text')));
bRow2.appendChild(labeled('secondary:hover', makeButton('Secondary Hover', 'Подробнее', 'platform/btn/secondary/bg/hover', 'platform/btn/secondary/text', { glow: { r: 0.6, g: 0.65, b: 0.98, a: 0.2 } })));
bRow2.appendChild(labeled('danger', makeButton('Danger', 'Удалить', 'error', 'platform/btn/primary/text')));
bRow2.appendChild(labeled('ghost', makeButton('Ghost', 'Отмена', 'glass/tint/subtle', 'text/secondary', { transparent: true })));
bRow2.appendChild(labeled('ghost-danger', makeButton('Ghost Danger', 'Удалить', 'error/bg', 'error', { transparent: true })));
btns.appendChild(bRow2);
root.appendChild(btns);
const fields = section('Поля — Field Pill');
const fRow = row(16);
fRow.appendChild(labeled('resting', makeField('Resting')));
fRow.appendChild(labeled('filled', makeField('Filled')));
fRow.appendChild(labeled('filled + hint', makeField('Hint')));
fRow.appendChild(labeled('compact', makeField('Compact')));
fields.appendChild(fRow);
root.appendChild(fields);
const cards = section('Карточки — Glass');
const cRow = row(16);
cRow.appendChild(labeled('subtle', makeCard('Subtle', 'glass/tint/subtle')));
cRow.appendChild(labeled('medium', makeCard('Medium', 'glass/tint/medium')));
cRow.appendChild(labeled('solid', makeCard('Solid', 'glass/solid/medium')));
cRow.appendChild(labeled('elevated', makeCard('Elevated', 'glass/solid/strong', true)));
cards.appendChild(cRow);
root.appendChild(cards);
const misc = section('Бейджи · Аватары · Тосты');
const gRow = row(10);
gRow.appendChild(makeBadge('Accent', 'Новый', 'accent', null));
gRow.appendChild(makeBadge('Success', 'Активен', 'success', 'success/bg'));
gRow.appendChild(makeBadge('Warning', 'Ожидает', 'warning', 'warning/bg'));
gRow.appendChild(makeBadge('Error', 'Ошибка', 'error', 'error/bg'));
gRow.appendChild(makeBadge('Info', 'Инфо', 'info', 'info/bg'));
misc.appendChild(gRow);
const aRow = row(16);
aRow.appendChild(labeled('56 gradient', makeAvatar(56, 'ВШ', true)));
aRow.appendChild(labeled('40 gradient', makeAvatar(40, 'АК', true)));
aRow.appendChild(labeled('32 neutral', makeAvatar(32, 'ИП', false)));
aRow.appendChild(labeled('24 neutral', makeAvatar(24, 'МС', false)));
misc.appendChild(aRow);
const tRow = row(12);
tRow.appendChild(makeToast('Success', 'Сохранено', 'success'));
tRow.appendChild(makeToast('Error', 'Не удалось сохранить', 'error'));
tRow.appendChild(makeToast('Info', 'Обновление доступно', 'info'));
misc.appendChild(tRow);
root.appendChild(misc);
const lists = section('Списки и таблицы');
const lRow = row(16);
lRow.appendChild(labeled('default', makeListRow('Default', 'Заметка о встрече', 'CRM · сегодня 14:20')));
lRow.appendChild(labeled('selected', makeListRow('Selected', 'Договор с ООО «Вега»', 'Сущности · обновлено вчера')));
lists.appendChild(lRow);
lists.appendChild(labeled('table', makeTable()));
lists.appendChild(labeled('modal', makeModal()));
root.appendChild(lists);
page.appendChild(root);
return { pageId: page.id, components: page.findAll(n => n.type === 'COMPONENT').length };
} catch (e) {
  return { error: String(e), stack: e.stack ? String(e.stack).slice(0, 1500) : null };
}
"""

_SHELL_JS = _HELPERS_JS + r"""
function icon(glyph, size, colorName) {
  const t = txt(glyph, FONT_R, size || 18, colorName || 'text/secondary');
  return t;
}
function navItem(label, glyph, active) {
  const n = figma.createComponent();
  n.name = 'Shell/NavItem' + (active ? ' Active' : '');
  n.layoutMode = 'HORIZONTAL'; n.itemSpacing = 12;
  n.paddingLeft = n.paddingRight = 12; n.paddingTop = n.paddingBottom = 9;
  n.primaryAxisSizingMode = 'FIXED'; n.counterAxisSizingMode = 'AUTO';
  n.counterAxisAlignItems = 'CENTER';
  n.resize(224, 40);
  bindRadius(n, 'radius/lg', 16);
  if (active) boundFill(n, 'accent/subtle', { r: 0.6, g: 0.65, b: 0.98, a: 0.16 });
  else n.fills = [];
  const ic = figma.createFrame();
  ic.resize(20, 20); ic.fills = [];
  ic.layoutMode = 'HORIZONTAL'; ic.primaryAxisAlignItems = 'CENTER'; ic.counterAxisAlignItems = 'CENTER';
  ic.appendChild(icon(glyph, 16, active ? 'accent' : 'text/secondary'));
  n.appendChild(ic);
  n.appendChild(txt(label, FONT_M, 14, active ? 'accent' : 'text/secondary'));
  return n;
}
function makeSidebar() {
  const sb = figma.createComponent();
  sb.name = 'Shell/Sidebar';
  sb.layoutMode = 'VERTICAL'; sb.itemSpacing = 0;
  sb.primaryAxisSizingMode = 'FIXED'; sb.counterAxisSizingMode = 'FIXED';
  sb.resize(280, 1024);
  sb.paddingLeft = sb.paddingRight = 16; sb.paddingTop = 16;
  sb.fills = [];
  const logo = figma.createFrame();
  logo.layoutMode = 'HORIZONTAL'; logo.itemSpacing = 12; logo.counterAxisAlignItems = 'CENTER';
  logo.paddingLeft = logo.paddingRight = 12; logo.paddingTop = logo.paddingBottom = 16;
  logo.primaryAxisSizingMode = 'FIXED'; logo.counterAxisSizingMode = 'AUTO';
  logo.resize(248, 60); logo.fills = []; logo.itemSpacing = 12;
  const li = figma.createFrame();
  li.resize(36, 36); bindRadius(li, 'radius/lg', 16);
  li.fills = [{ type: 'GRADIENT_LINEAR', gradientTransform: [[1, -1, 0.5], [1, 1, 0.5]], gradientStops: [{ color: { r: 0.6, g: 0.65, b: 0.98, a: 1 }, position: 0 }, { color: { r: 0.55, g: 0.36, b: 0.96, a: 1 }, position: 1 }] }];
  li.layoutMode = 'HORIZONTAL'; li.primaryAxisAlignItems = 'CENTER'; li.counterAxisAlignItems = 'CENTER';
  li.appendChild(txt('L', FONT_B, 18, 'platform/btn/primary/text'));
  logo.appendChild(li);
  logo.appendChild(txt('Linnex', FONT_B, 20, 'text/primary'));
  sb.appendChild(logo);
  const head = figma.createFrame();
  head.layoutMode = 'HORIZONTAL'; head.itemSpacing = 8;
  head.primaryAxisSizingMode = 'FIXED'; head.counterAxisSizingMode = 'AUTO';
  head.resize(248, 40); head.paddingBottom = 8; head.fills = [];
  sb.appendChild(head);
  const nav = figma.createFrame();
  nav.layoutMode = 'VERTICAL'; nav.itemSpacing = 4;
  nav.paddingLeft = nav.paddingRight = 12;
  nav.primaryAxisSizingMode = 'AUTO'; nav.counterAxisSizingMode = 'FIXED';
  nav.resize(248, 400); nav.fills = []; nav.layoutGrow = 1;
  const st = txt('РАБОЧЕЕ ПРОСТРАНСТВО', FONT_S, 12, 'text/tertiary');
  st.letterSpacing = { value: 8, unit: 'PERCENT' };
  const stWrap = figma.createFrame(); stWrap.layoutMode = 'HORIZONTAL';
  stWrap.paddingLeft = stWrap.paddingRight = 12; stWrap.paddingTop = stWrap.paddingBottom = 8;
  stWrap.primaryAxisSizingMode = 'FIXED'; stWrap.counterAxisSizingMode = 'AUTO';
  stWrap.resize(224, 30); stWrap.fills = [];
  stWrap.appendChild(st);
  nav.appendChild(stWrap);
  const items = spec.nav;
  for (const it of items) nav.appendChild(navItem(it[0], it[1], it[2]).createInstance());
  sb.appendChild(nav);
  const foot = figma.createFrame();
  foot.layoutMode = 'HORIZONTAL'; foot.itemSpacing = 12; foot.counterAxisAlignItems = 'CENTER';
  foot.paddingLeft = foot.paddingRight = foot.paddingTop = foot.paddingBottom = 16;
  foot.primaryAxisSizingMode = 'FIXED'; foot.counterAxisSizingMode = 'AUTO';
  foot.resize(280, 68); foot.x = 0;
  foot.strokes = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1, a: 0.08 } }]; foot.strokeWeight = 1; foot.strokeAlign = 'INSIDE';
  foot.fills = [];
  const av = figma.createFrame(); av.resize(36, 36); av.cornerRadius = 18;
  av.fills = [{ type: 'GRADIENT_LINEAR', gradientTransform: [[1, -1, 0.5], [1, 1, 0.5]], gradientStops: [{ color: { r: 1, g: 0.53, b: 0.36, a: 1 }, position: 0 }, { color: { r: 0.96, g: 0.25, b: 0.37, a: 1 }, position: 1 }] }];
  av.layoutMode = 'HORIZONTAL'; av.primaryAxisAlignItems = 'CENTER'; av.counterAxisAlignItems = 'CENTER';
  av.appendChild(txt('ВШ', FONT_M, 13, 'platform/btn/primary/text'));
  foot.appendChild(av);
  const un = col(2); un.layoutGrow = 1;
  un.appendChild(txt('Виктор Швед', FONT_M, 13, 'text/primary'));
  un.appendChild(txt('Администратор', FONT_R, 11, 'text/tertiary'));
  foot.appendChild(un);
  foot.appendChild(icon('◔', 16, 'text/secondary'));
  sb.appendChild(foot);
  foot.absoluteTransform = [[1, 0, 0], [0, 1, 956]];
  foot.layoutPositioning = 'ABSOLUTE';
  return sb;
}
function makeTopBar() {
  const tb = figma.createComponent();
  tb.name = 'Shell/TopBar';
  tb.layoutMode = 'HORIZONTAL'; tb.itemSpacing = 8;
  tb.primaryAxisSizingMode = 'FIXED'; tb.counterAxisSizingMode = 'AUTO';
  tb.counterAxisAlignItems = 'CENTER';
  tb.paddingLeft = tb.paddingRight = 12; tb.paddingTop = tb.paddingBottom = 8;
  tb.resize(390, 52);
  boundFill(tb, 'glass/solid/strong', { r: 0.16, g: 0.16, b: 0.25, a: 0.92 });
  boundStroke(tb, 'glass/border/subtle');
  const back = figma.createFrame(); back.resize(36, 36); bindRadius(back, 'radius/lg', 16);
  boundFill(back, 'glass/tint/medium', { r: 1, g: 1, b: 1, a: 0.05 }); boundStroke(back, 'glass/border/subtle');
  back.layoutMode = 'HORIZONTAL'; back.primaryAxisAlignItems = 'CENTER'; back.counterAxisAlignItems = 'CENTER';
  back.appendChild(txt('‹', FONT_M, 18, 'text/primary'));
  tb.appendChild(back);
  const mid = figma.createFrame(); mid.fills = []; mid.layoutGrow = 1;
  mid.layoutMode = 'HORIZONTAL'; mid.primaryAxisAlignItems = 'CENTER'; mid.counterAxisAlignItems = 'CENTER';
  mid.appendChild(txt('Дашборд', FONT_S, 16, 'text/primary'));
  tb.appendChild(mid);
  const bell = figma.createFrame(); bell.resize(36, 36); bindRadius(bell, 'radius/lg', 16);
  boundFill(bell, 'glass/tint/medium', { r: 1, g: 1, b: 1, a: 0.05 }); boundStroke(bell, 'glass/border/subtle');
  bell.layoutMode = 'HORIZONTAL'; bell.primaryAxisAlignItems = 'CENTER'; bell.counterAxisAlignItems = 'CENTER';
  bell.appendChild(txt('◉', FONT_R, 15, 'text/secondary'));
  tb.appendChild(bell);
  return tb;
}
function bottomNavItem(glyph, label, active) {
  const n = figma.createFrame();
  n.layoutMode = 'VERTICAL'; n.itemSpacing = 2;
  n.paddingLeft = n.paddingRight = 8; n.paddingTop = n.paddingBottom = 6;
  n.primaryAxisSizingMode = 'AUTO'; n.counterAxisSizingMode = 'AUTO';
  n.counterAxisAlignItems = 'CENTER'; n.primaryAxisAlignItems = 'CENTER';
  bindRadius(n, 'radius/xl', 20);
  if (active) boundFill(n, 'accent/subtle', { r: 0.6, g: 0.65, b: 0.98, a: 0.16 }); else n.fills = [];
  n.appendChild(icon(glyph, 22, active ? 'accent' : 'text/secondary'));
  n.appendChild(txt(label, FONT_R, 10, active ? 'accent' : 'text/secondary'));
  return n;
}
function makeBottomNav() {
  const bn = figma.createComponent();
  bn.name = 'Shell/BottomNav';
  bn.layoutMode = 'HORIZONTAL'; bn.itemSpacing = 2;
  bn.primaryAxisSizingMode = 'FIXED'; bn.counterAxisSizingMode = 'AUTO';
  bn.paddingLeft = bn.paddingRight = bn.paddingTop = bn.paddingBottom = 8;
  bn.primaryAxisAlignItems = 'CENTER';
  bn.resize(374, 64);
  bindRadius(bn, 'radius/2xl', 24);
  boundFill(bn, 'glass/solid/strong', { r: 0.16, g: 0.16, b: 0.25, a: 0.92 });
  boundStroke(bn, 'glass/border/subtle');
  bn.effects = [{ type: 'DROP_SHADOW', color: { r: 0, g: 0, b: 0, a: 0.35 }, offset: { x: 0, y: 8 }, radius: 24, spread: 0, visible: true, blendMode: 'NORMAL' }];
  const items = [['⌂', 'Главная', true], ['✉', 'Синк', false], ['◆', 'CRM', false], ['▤', 'Документы', false], ['☰', 'Ещё', false]];
  for (const it of items) {
    const ni = bottomNavItem(it[0], it[1], it[2]);
    ni.layoutGrow = 1;
    bn.appendChild(ni);
  }
  return bn;
}
try {
const root = figma.createFrame();
root.name = 'shell-board';
root.layoutMode = 'HORIZONTAL'; root.itemSpacing = 48;
root.paddingLeft = root.paddingTop = root.paddingRight = root.paddingBottom = 32;
root.primaryAxisSizingMode = 'AUTO'; root.counterAxisSizingMode = 'AUTO';
root.fills = [];
const headCol = col(8);
headCol.appendChild(txt('Linnex · App Shell', FONT_S, 28, 'text/primary'));
headCol.appendChild(txt('Desktop 1440 (sidebar 280 + content) · Mobile 390 (top-bar + bottom-nav)', FONT_R, 13, 'text/secondary'));
root.appendChild(headCol);
const desk = section('Desktop — 1440 × 1024');
const dwrap = figma.createFrame();
dwrap.name = 'Shell/Desktop';
dwrap.layoutMode = 'HORIZONTAL'; dwrap.itemSpacing = 0;
dwrap.primaryAxisSizingMode = 'FIXED'; dwrap.counterAxisSizingMode = 'FIXED';
dwrap.resize(1440, 1024); dwrap.clipsContent = true;
boundFill(dwrap, 'bg/primary', { r: 0.086, g: 0.13, b: 0.24 });
const sidebar = makeSidebar();
dwrap.appendChild(sidebar);
const main = figma.createFrame();
main.name = 'content';
main.layoutMode = 'VERTICAL'; main.itemSpacing = 24;
main.paddingLeft = main.paddingRight = main.paddingTop = 32;
main.primaryAxisSizingMode = 'FIXED'; main.counterAxisSizingMode = 'FIXED';
main.resize(1160, 1024); main.fills = [];
main.appendChild(txt('Дашборд', FONT_S, 28, 'text/primary'));
const phRow = row(16);
for (const t of ['Быстрые действия', 'Активность', 'Задачи']) {
  const card = figma.createFrame();
  card.layoutMode = 'VERTICAL'; card.itemSpacing = 8;
  card.paddingLeft = card.paddingRight = card.paddingTop = card.paddingBottom = 20;
  bindRadius(card, 'radius/xl', 20);
  boundFill(card, 'glass/tint/subtle', { r: 1, g: 1, b: 1, a: 0.03 });
  boundStroke(card, 'glass/border/subtle');
  card.resize(360, 160);
  card.appendChild(txt(t, FONT_M, 14, 'text/secondary'));
  card.appendChild(txt('…контент экрана сервиса…', FONT_R, 12, 'text/tertiary'));
  phRow.appendChild(card);
}
main.appendChild(phRow);
dwrap.appendChild(main);
desk.appendChild(dwrap);
root.appendChild(desk);
const mob = section('Mobile — 390 × 844');
const mwrap = figma.createFrame();
mwrap.name = 'Shell/Mobile';
mwrap.layoutMode = 'VERTICAL'; mwrap.itemSpacing = 0;
mwrap.primaryAxisSizingMode = 'FIXED'; mwrap.counterAxisSizingMode = 'FIXED';
mwrap.resize(390, 844); mwrap.clipsContent = true;
boundFill(mwrap, 'bg/primary', { r: 0.086, g: 0.13, b: 0.24 });
mwrap.appendChild(makeTopBar());
const mmain = figma.createFrame();
mmain.name = 'content';
mmain.layoutMode = 'VERTICAL'; mmain.itemSpacing = 12;
mmain.paddingLeft = mmain.paddingRight = 16; mmain.paddingTop = 20;
mmain.primaryAxisSizingMode = 'FIXED'; mmain.counterAxisSizingMode = 'AUTO';
mmain.resize(390, 660); mmain.fills = []; mmain.layoutGrow = 1;
for (const t of ['Быстрые действия', 'Активность', 'Задачи']) {
  const card = figma.createFrame();
  card.layoutMode = 'VERTICAL'; card.itemSpacing = 6;
  card.paddingLeft = card.paddingRight = card.paddingTop = card.paddingBottom = 16;
  bindRadius(card, 'radius/xl', 20);
  boundFill(card, 'glass/tint/subtle', { r: 1, g: 1, b: 1, a: 0.03 });
  boundStroke(card, 'glass/border/subtle');
  card.resize(358, 120);
  card.appendChild(txt(t, FONT_M, 14, 'text/secondary'));
  card.appendChild(txt('…контент…', FONT_R, 12, 'text/tertiary'));
  mmain.appendChild(card);
}
mwrap.appendChild(mmain);
const bnHolder = figma.createFrame();
bnHolder.layoutMode = 'HORIZONTAL'; bnHolder.primaryAxisAlignItems = 'CENTER'; bnHolder.counterAxisAlignItems = 'CENTER';
bnHolder.primaryAxisSizingMode = 'FIXED'; bnHolder.counterAxisSizingMode = 'FIXED';
bnHolder.resize(390, 96); bnHolder.fills = [];
bnHolder.appendChild(makeBottomNav());
mwrap.appendChild(bnHolder);
mob.appendChild(mwrap);
root.appendChild(mob);
container.appendChild(root);
return { pageId: page.id, components: page.findAll(n => n.type === 'COMPONENT').length };
} catch (e) {
  return { error: String(e), stack: e.stack ? String(e.stack).slice(0, 1500) : null };
}
"""


def _uikit_payload() -> Json:
    from scripts.tools.figma_tokens import extract

    spec = extract()
    tokens = {t["name"]: {"Dark": t["values"].get("Dark"), "Light": t["values"].get("Light")} for t in spec["tokens"]}
    return {
        "page": "🧱 UI Kit",
        "collDark": f"{spec['collection']} · Dark",
        "tokens": tokens,
    }


def _shell_payload() -> Json:
    from scripts.tools.figma_tokens import extract

    spec = extract()
    tokens = {t["name"]: {"Dark": t["values"].get("Dark"), "Light": t["values"].get("Light")} for t in spec["tokens"]}
    return {
        "page": "� Экраны",
        "zone": "zone/00 — App Shell",
        "collDark": f"{spec['collection']} · Dark",
        "tokens": tokens,
        "nav": [
            ["Дашборд", "⌂", True],
            ["Синк", "✉", False],
            ["NetWorkle", "◆", False],
            ["Документы", "▤", False],
            ["Wiki", "✎", False],
            ["Задачи", "☑", False],
            ["Flows", "⚡", False],
        ],
    }


def _run(js: str, tag: str, payload: Json, args: argparse.Namespace) -> int:
    file_key = str(args.file_key or "") or _project_file_key()
    server = _Server()
    try:
        if not server.start():
            print(f"{tag}: figma-console-mcp не инициализировался", file=sys.stderr)
            return 2
        _require_design_file(server, file_key or None, wait=float(args.wait_plugin or 30))
        code = js.replace("SPEC", json.dumps(payload, ensure_ascii=False), 1)
        result = _figma_exec(server, code, timeout_ms=300_000)
        print(f"{tag}: {json.dumps(result, ensure_ascii=False)[:400]}")
        return 0
    finally:
        server.stop()


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.tools.figma_uikit")
    parser.add_argument("command", nargs="?", default="uikit", choices=["uikit", "shell"])
    parser.add_argument("--file-key", default="")
    parser.add_argument("--wait-plugin", type=float, default=30)
    ns = parser.parse_args()
    if ns.command == "shell":
        return _run(_SHELL_JS, "shell", _shell_payload(), ns)
    return _run(_UKIT_JS, "uikit", _uikit_payload(), ns)


if __name__ == "__main__":
    raise SystemExit(main())
