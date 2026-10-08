/**
 * platform-field-* — поля типизированного отображения/редактирования.
 *
 * Платформа имеет один канон pill: <platform-field> рендерит типизированный
 * подкомпонент внутри <platform-field-shell> — floating label (Material
 * outlined) с notch в бордере через <fieldset>/<legend>, фокус-ринг и
 * error-сообщение. Подкомпоненты используют классы
 * field-pill-input/-textarea/-select или enum-combobox (.field-pill-enum-*),
 * у platform-field-string есть property inputType (text|email|password|url|tel|search).
 */

import { fixture, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus } from '@platform/lib/events/index.js';
import { formatPlatformDate } from '@platform/lib/utils/format-platform-date.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/fields/platform-field-shell.js';
import '@platform/lib/components/fields/platform-field-string.js';
import '@platform/lib/components/fields/platform-field-text.js';
import '@platform/lib/components/fields/platform-field-number.js';
import '@platform/lib/components/fields/platform-field-boolean.js';
import '@platform/lib/components/fields/platform-field-date.js';
import '@platform/lib/components/fields/platform-field-enum.js';
import '@platform/lib/components/fields/platform-field-array.js';
import '@platform/lib/components/fields/platform-field-object.js';
import '@platform/lib/components/fields/platform-field-external-refs.js';

beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

const shellRoot = (el) => el.shadowRoot.querySelector('platform-field-shell').shadowRoot;

describe('platform-field dispatcher', () => {
    it('edit + label: shell, floating label и field-pill-input в shadowRoot', async () => {
        const el = await fixture(html`
            <platform-field
                type="string"
                mode="edit"
                label="TestLabel"
                value="x"
            ></platform-field>
        `);
        const pill = shellRoot(el).querySelector('fieldset.field-pill');
        expect(pill).to.exist;
        const lab = shellRoot(el).querySelector('.field-pill-label');
        expect(lab).to.exist;
        expect(lab.textContent).to.equal('TestLabel');
        expect(shellRoot(el).querySelector('.field-pill-control')).to.exist;
        expect(shellRoot(el).querySelector('.field-pill-control-main')).to.exist;
        const inner = el.shadowRoot.querySelector('platform-field-string');
        expect(inner).to.exist;
        const inp = inner.shadowRoot.querySelector('input.field-pill-input');
        expect(inp).to.exist;
        expect(inp.getAttribute('type')).to.equal('text');
    });

    it('pill-density="compact" добавляет field-pill--compact', async () => {
        const el = await fixture(html`
            <platform-field type="string" mode="edit" value="" pill-density="compact"></platform-field>
        `);
        const pill = shellRoot(el).querySelector('.field-pill');
        expect(pill.classList.contains('field-pill--compact')).to.equal(true);
    });

    it('pill-density="dense" добавляет field-pill--compact и field-pill--dense', async () => {
        const el = await fixture(html`
            <platform-field type="string" mode="edit" value="" pill-density="dense"></platform-field>
        `);
        const pill = shellRoot(el).querySelector('.field-pill');
        expect(pill.classList.contains('field-pill--compact')).to.equal(true);
        expect(pill.classList.contains('field-pill--dense')).to.equal(true);
    });

    it('pill-embed добавляет field-pill--embed', async () => {
        const el = await fixture(html`
            <platform-field type="string" mode="edit" value="" pill-embed label="InCard"></platform-field>
        `);
        const pill = shellRoot(el).querySelector('.field-pill');
        expect(pill.classList.contains('field-pill--embed')).to.equal(true);
    });

    it('без label не рендерит field-pill-label, но рисует pill', async () => {
        const el = await fixture(html`<platform-field type="string" mode="edit" value=""></platform-field>`);
        expect(shellRoot(el).querySelector('.field-pill')).to.exist;
        expect(shellRoot(el).querySelector('.field-pill-label')).to.be.null;
    });

    it('пробрасывает inputType="email" в подкомпонент', async () => {
        const el = await fixture(html`
            <platform-field type="string" input-type="email" mode="edit" value="a@b.c"></platform-field>
        `);
        const inner = el.shadowRoot.querySelector('platform-field-string');
        const inp = inner.shadowRoot.querySelector('input.field-pill-input');
        expect(inp.getAttribute('type')).to.equal('email');
    });

    it('пробрасывает suggestions в string-подкомпонент как datalist', async () => {
        const el = await fixture(html`
            <platform-field
                type="string"
                mode="edit"
                value=""
                .suggestions=${['state.user.name', '', 'state.order.total']}
            ></platform-field>
        `);
        const inner = el.shadowRoot.querySelector('platform-field-string');
        const inp = inner.shadowRoot.querySelector('input.field-pill-input');
        const listId = inp.getAttribute('list');
        const list = inner.shadowRoot.querySelector(`datalist#${listId}`);
        const options = Array.from(list.querySelectorAll('option')).map((option) => option.value);
        expect(options).to.deep.equal(['state.user.name', 'state.order.total']);
    });

    it('view-режим рендерит pill + field-pill-readonly-text', async () => {
        const el = await fixture(html`<platform-field type="string" mode="view" label="L" value="visible"></platform-field>`);
        expect(shellRoot(el).querySelector('.field-pill')).to.exist;
        expect(shellRoot(el).querySelector('.field-pill-label').textContent).to.equal('L');
        const inner = el.shadowRoot.querySelector('platform-field-string');
        expect(inner.shadowRoot.querySelector('.field-pill-readonly-text').textContent).to.equal('visible');
    });

    it('hint property рисует <platform-help-hint> рядом с floating label', async () => {
        const el = await fixture(html`
            <platform-field
                type="string"
                mode="edit"
                .label=${'X'}
                .value=${'v'}
                .hint=${'tooltip text'}
            ></platform-field>
        `);
        const float = shellRoot(el).querySelector('.field-pill-float');
        expect(float).to.exist;
        const hint = float.querySelector('platform-help-hint');
        expect(hint).to.exist;
        expect(hint.text).to.equal('tooltip text');
    });

    it('без hint — не рендерит <platform-help-hint>', async () => {
        const el = await fixture(html`<platform-field type="string" mode="edit" label="X" value=""></platform-field>`);
        expect(shellRoot(el).querySelector('platform-help-hint')).to.be.null;
    });

    it('slot prefix: элемент с slot=prefix попадает в named slot', async () => {
        const el = await fixture(html`
            <platform-field type="string" mode="edit" value="">
                <span slot="prefix" class="prefix-marker">P</span>
            </platform-field>
        `);
        const slotEl = el.shadowRoot.querySelector('slot[name="prefix"]');
        expect(slotEl).to.exist;
        const assigned = slotEl.assignedElements().find((n) => n.classList.contains('prefix-marker'));
        expect(assigned).to.exist;
    });

    it('slot suffix: элемент с slot=suffix попадает в named slot', async () => {
        const el = await fixture(html`
            <platform-field type="string" mode="view" label="L" value="id1">
                <span slot="suffix" class="suffix-marker">S</span>
            </platform-field>
        `);
        const slotEl = el.shadowRoot.querySelector('slot[name="suffix"]');
        expect(slotEl).to.exist;
        const assigned = slotEl.assignedElements().find((n) => n.classList.contains('suffix-marker'));
        expect(assigned).to.exist;
    });

    it('type=array: allowed_values — combobox и change.detail.value', async () => {
        const el = await fixture(html`
            <platform-field
                type="array"
                mode="edit"
                .value=${[]}
                .config=${{ allowed_values: ['A', 'B'] }}
                .placeholder=${'Pick'}
            ></platform-field>
        `);
        const inner = el.shadowRoot.querySelector('platform-field-array');
        const sel = inner.shadowRoot.querySelector('select[data-canon="combobox"]');
        expect(sel).to.exist;
        sel.value = 'A';
        const p = oneEvent(el, 'change');
        sel.dispatchEvent(new Event('change', { bubbles: true }));
        const ev = await p;
        expect(ev.detail.value).to.deep.equal(['A']);
    });

    it('type=array: preserve_case на tag-input', async () => {
        const el = await fixture(html`
            <platform-field
                type="array"
                mode="edit"
                .value=${[]}
                .config=${{ preserve_case: true }}
            ></platform-field>
        `);
        const inner = el.shadowRoot.querySelector('platform-field-array');
        const ti = inner.shadowRoot.querySelector('tag-input');
        expect(ti.preserveCase).to.equal(true);
    });
});

describe('platform-field-string inputType', () => {
    const ALLOWED = ['text', 'email', 'password', 'url', 'tel', 'search'];

    for (const t of ALLOWED) {
        it(`inputType="${t}" рендерит <input type="${t}">`, async () => {
            const el = await fixture(html`
                <platform-field-string mode="edit" value="" .inputType=${t}></platform-field-string>
            `);
            const inp = el.shadowRoot.querySelector('input.field-pill-input');
            expect(inp.getAttribute('type')).to.equal(t);
        });
    }

    it('inputType вне списка — fails fast в валидаторе', () => {
        const el = document.createElement('platform-field-string');
        el.inputType = 'date';
        expect(() => el._resolvedInputType()).to.throw(/inputType/);
    });

    it('password в view-режиме маскирует значение', async () => {
        const el = await fixture(html`
            <platform-field-string mode="view" value="secret" .inputType=${'password'}></platform-field-string>
        `);
        const text = el.shadowRoot.querySelector('.field-pill-readonly-text').textContent;
        expect(text).to.match(/^•+$/);
    });
});

describe('platform-field-string base', () => {
    it('view mode без значения рендерит field-pill-empty', async () => {
        const el = await fixture(html`<platform-field-string mode="view" value=""></platform-field-string>`);
        expect(el.shadowRoot.querySelector('.field-pill-empty')).to.exist;
    });

    it('edit mode рендерит input и эмитит change', async () => {
        const el = await fixture(html`<platform-field-string mode="edit" value="x"></platform-field-string>`);
        const inp = el.shadowRoot.querySelector('input.field-pill-input');
        const promise = oneEvent(el, 'change');
        inp.value = 'updated';
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        const ev = await promise;
        expect(ev.detail.value).to.equal('updated');
    });

    it('disabled пробрасывается на input', async () => {
        const el = await fixture(html`<platform-field-string mode="edit" value="x" ?disabled=${true}></platform-field-string>`);
        const inp = el.shadowRoot.querySelector('input.field-pill-input');
        expect(inp.disabled).to.equal(true);
    });

    it('placeholder пробрасывается на input', async () => {
        const el = await fixture(html`
            <platform-field-string mode="edit" value="" .placeholder=${'hint here'}></platform-field-string>
        `);
        const inp = el.shadowRoot.querySelector('input.field-pill-input');
        expect(inp.placeholder).to.equal('hint here');
    });
});

describe('platform-field-text', () => {
    it('view-mode рендерит field-pill-readonly-text', async () => {
        const el = await fixture(html`<platform-field-text mode="view" value="multi"></platform-field-text>`);
        expect(el.shadowRoot.querySelector('.field-pill-readonly-text').textContent).to.equal('multi');
    });

    it('edit-mode рендерит textarea.field-pill-textarea', async () => {
        const el = await fixture(html`<platform-field-text mode="edit" value=""></platform-field-text>`);
        const ta = el.shadowRoot.querySelector('textarea.field-pill-textarea');
        expect(ta).to.exist;
    });
});

describe('platform-field-number', () => {
    it('рендерится в обоих режимах', async () => {
        const view = await fixture(html`<platform-field-number mode="view" value="42"></platform-field-number>`);
        expect(view.shadowRoot).to.exist;
        const edit = await fixture(html`<platform-field-number mode="edit" value="42"></platform-field-number>`);
        const inp = edit.shadowRoot.querySelector('input.field-pill-input');
        expect(inp).to.exist;
        expect(inp.getAttribute('type')).to.equal('number');
    });
});

describe('platform-field-enum', () => {
    it('view: empty', async () => {
        const el = await fixture(html`<platform-field-enum mode="view" value=""></platform-field-enum>`);
        expect(el.shadowRoot.querySelector('.field-pill-empty')).to.exist;
    });

    it('view с массивом строк: chip отображает value', async () => {
        const el = await fixture(html`
            <platform-field-enum mode="view" value="a" .config=${{ values: ['a', 'b'] }}></platform-field-enum>
        `);
        expect(el.shadowRoot.querySelector('.enum-chip').textContent).to.equal('a');
    });

    it('view с массивом {value,label}: chip отображает label', async () => {
        const el = await fixture(html`
            <platform-field-enum
                mode="view"
                value="active"
                .config=${{ values: [{ value: 'active', label: 'Активно' }, { value: 'archived', label: 'В архиве' }] }}
            ></platform-field-enum>
        `);
        expect(el.shadowRoot.querySelector('.enum-chip').textContent).to.equal('Активно');
    });

    it('edit: combobox и список label при фокусе', async () => {
        const el = await fixture(html`
            <platform-field-enum
                mode="edit"
                value="x"
                .config=${{ values: [{ value: 'x', label: 'X-Label' }, { value: 'y', label: 'Y-Label' }] }}
            ></platform-field-enum>
        `);
        const inp = el.shadowRoot.querySelector('input.field-pill-enum-input');
        expect(inp).to.exist;
        inp.focus();
        await elementUpdated(el);
        const rowX = el.shadowRoot.querySelector('[data-enum-value="x"]');
        const rowY = el.shadowRoot.querySelector('[data-enum-value="y"]');
        expect(rowX).to.exist;
        expect(rowY).to.exist;
        expect(rowX.textContent.trim()).to.equal('X-Label');
        expect(rowY.textContent.trim()).to.equal('Y-Label');
    });

    it('edit с массивом строк: data-enum-value совпадает с value опции', async () => {
        const el = await fixture(html`
            <platform-field-enum mode="edit" value="a" .config=${{ values: ['a', 'b'] }}></platform-field-enum>
        `);
        const inp = el.shadowRoot.querySelector('input.field-pill-enum-input');
        inp.focus();
        await elementUpdated(el);
        const rows = Array.from(el.shadowRoot.querySelectorAll('[data-enum-value]'));
        expect(rows.length).to.equal(3);
        expect(rows.some((li) => li.getAttribute('data-enum-value') === '')).to.equal(true);
        expect(rows.some((li) => li.getAttribute('data-enum-value') === 'a')).to.equal(true);
        expect(rows.some((li) => li.getAttribute('data-enum-value') === 'b')).to.equal(true);
    });

    it('edit: {value: "", label} без дублирующей синтетической пустой строки', async () => {
        const el = await fixture(html`
            <platform-field-enum
                mode="edit"
                value=""
                .config=${{ values: [{ value: '', label: 'Default row' }, { value: 'x', label: 'X' }] }}
            ></platform-field-enum>
        `);
        const inp = el.shadowRoot.querySelector('input.field-pill-enum-input');
        inp.focus();
        await elementUpdated(el);
        const rows = Array.from(el.shadowRoot.querySelectorAll('[data-enum-value]'));
        expect(rows.length).to.equal(2);
        const emptyRow = rows.find((li) => li.getAttribute('data-enum-value') === '');
        expect(emptyRow.textContent.trim()).to.equal('Default row');
        const xRow = rows.find((li) => li.getAttribute('data-enum-value') === 'x');
        expect(xRow.textContent.trim()).to.equal('X');
    });

    it('edit: фильтрует опции при вводе', async () => {
        const el = await fixture(html`
            <platform-field-enum
                mode="edit"
                value="a"
                .config=${{ values: [{ value: 'a', label: 'Alpha' }, { value: 'b', label: 'Beta' }] }}
            ></platform-field-enum>
        `);
        const inp = el.shadowRoot.querySelector('input.field-pill-enum-input');
        inp.focus();
        await elementUpdated(el);
        inp.value = 'Bet';
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        await elementUpdated(el);
        const items = el.shadowRoot.querySelectorAll('[data-enum-value]');
        expect(items.length).to.equal(1);
        expect(items[0].getAttribute('data-enum-value')).to.equal('b');
    });

    it('edit: выбор опции испускает change', async () => {
        const el = await fixture(html`
            <platform-field-enum mode="edit" value="a" .config=${{ values: ['a', 'b'] }}></platform-field-enum>
        `);
        const inp = el.shadowRoot.querySelector('input.field-pill-enum-input');
        inp.focus();
        await elementUpdated(el);
        const p = oneEvent(el, 'change');
        const row = el.shadowRoot.querySelector('[data-enum-value="b"]');
        expect(row).to.exist;
        row.click();
        const ev = await p;
        expect(ev.detail.value).to.equal('b');
    });

    it('edit: chevron после выбора открывает полный список без очистки текста', async () => {
        const el = await fixture(html`
            <platform-field-enum
                mode="edit"
                value="a"
                .config=${{ values: [{ value: 'a', label: 'Alpha' }, { value: 'b', label: 'Beta' }] }}
            ></platform-field-enum>
        `);
        const inp = el.shadowRoot.querySelector('input.field-pill-enum-input');
        inp.focus();
        await elementUpdated(el);
        inp.value = 'Bet';
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        await elementUpdated(el);
        const change = oneEvent(el, 'change');
        el.shadowRoot.querySelector('[data-enum-value="b"]').click();
        await change;
        await elementUpdated(el);

        const chevron = el.shadowRoot.querySelector('.field-pill-enum-chevron');
        chevron.click();
        await elementUpdated(el);

        const values = Array.from(el.shadowRoot.querySelectorAll('[data-enum-value]'))
            .map((li) => li.getAttribute('data-enum-value'));
        expect(values).to.deep.equal(['', 'a', 'b']);
    });
});

describe('platform-field-boolean / date / array / object: smoke', () => {
    it('boolean рендерится', async () => {
        const el = await fixture(html`<platform-field-boolean mode="view" .value=${true}></platform-field-boolean>`);
        expect(el.shadowRoot).to.exist;
    });

    it('date рендерится в view', async () => {
        const el = await fixture(html`<platform-field-date mode="view" value="2026-01-01"></platform-field-date>`);
        const locale = getPlatformBus().getState().i18n.locale;
        const expected = formatPlatformDate('2026-01-01', locale);
        expect(el.shadowRoot.querySelector('.field-pill-readonly-text').textContent).to.equal(expected);
    });

    it('array рендерится', async () => {
        const el = await fixture(html`<platform-field-array mode="view" .value=${['x', 'y']}></platform-field-array>`);
        expect(el.shadowRoot).to.exist;
    });

    it('object рендерится', async () => {
        const el = await fixture(html`<platform-field-object mode="view" .value=${{ a: 1 }}></platform-field-object>`);
        expect(el.shadowRoot.querySelector('.view-json')).to.exist;
    });

    it('external_refs view рендерит empty при отсутствии данных', async () => {
        const el = await fixture(html`
            <platform-field-external-refs mode="view" .value=${null}></platform-field-external-refs>
        `);
        expect(el.shadowRoot.querySelector('.field-pill-empty')).to.exist;
    });
});

describe('platform-field-shell', () => {
    it('label: <fieldset>+<legend> notch и resting label внутри контрола', async () => {
        const el = await fixture(html`
            <platform-field-shell label="Notch" editable>
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        const fs = el.shadowRoot.querySelector('fieldset.field-pill');
        expect(fs).to.exist;
        expect(fs.getAttribute('aria-label')).to.equal('Notch');
        const legend = fs.querySelector('legend.field-pill-legend .field-pill-legend-text');
        expect(legend).to.exist;
        expect(legend.textContent).to.equal('Notch');
        const float = fs.querySelector('.field-pill-float .field-pill-label');
        expect(float).to.exist;
        expect(float.textContent).to.equal('Notch');
    });

    it('floated: fieldset получает field-pill--float', async () => {
        const el = await fixture(html`
            <platform-field-shell label="L" floated>
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        expect(el.shadowRoot.querySelector('fieldset').classList.contains('field-pill--float')).to.equal(true);
    });

    it('без floated: resting label без field-pill--float', async () => {
        const el = await fixture(html`
            <platform-field-shell label="L">
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        expect(el.shadowRoot.querySelector('fieldset').classList.contains('field-pill--float')).to.equal(false);
    });

    it('error: field-pill--error + .field-pill-message[role=alert]', async () => {
        const el = await fixture(html`
            <platform-field-shell label="L" error="boom">
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        expect(el.shadowRoot.querySelector('fieldset').classList.contains('field-pill--error')).to.equal(true);
        const msg = el.shadowRoot.querySelector('.field-pill-message');
        expect(msg).to.exist;
        expect(msg.getAttribute('role')).to.equal('alert');
        expect(msg.textContent).to.equal('boom');
    });

    it('disabled: field-pill--disabled', async () => {
        const el = await fixture(html`
            <platform-field-shell label="L" disabled>
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        expect(el.shadowRoot.querySelector('fieldset').classList.contains('field-pill--disabled')).to.equal(true);
    });

    it('density вне списка — fails fast', async () => {
        const el = document.createElement('platform-field-shell');
        el.density = 'huge';
        expect(() => el.willUpdate(new Map([['density', 'huge']]))).to.throw(/density/);
    });

    it('editable: клик по pill фокусирует slotted input', async () => {
        const el = await fixture(html`
            <platform-field-shell label="L" editable>
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        el.shadowRoot.querySelector('fieldset').dispatchEvent(new MouseEvent('click', { bubbles: true }));
        const inp = el.querySelector('input');
        expect(document.activeElement === inp || el.contains(document.activeElement)).to.equal(true);
    });

    it('не editable: клик по pill не забирает фокус', async () => {
        const el = await fixture(html`
            <platform-field-shell label="L">
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        el.shadowRoot.querySelector('fieldset').dispatchEvent(new MouseEvent('click', { bubbles: true }));
        expect(document.activeElement).to.not.equal(el.querySelector('input'));
    });
});

describe('platform-field floating label', () => {
    it('edit + пустое значение: resting label (без --float), placeholder подавлен', async () => {
        const el = await fixture(html`
            <platform-field
                type="string"
                mode="edit"
                label="Name"
                placeholder="type here"
                value=""
            ></platform-field>
        `);
        const fs = shellRoot(el).querySelector('fieldset');
        expect(fs.classList.contains('field-pill--float')).to.equal(false);
        const inp = el.shadowRoot.querySelector('platform-field-string').shadowRoot.querySelector('input');
        expect(inp.placeholder).to.equal('');
    });

    it('edit + значение: label улетел (field-pill--float), placeholder виден', async () => {
        const el = await fixture(html`
            <platform-field
                type="string"
                mode="edit"
                label="Name"
                placeholder="type here"
                value="v"
            ></platform-field>
        `);
        const fs = shellRoot(el).querySelector('fieldset');
        expect(fs.classList.contains('field-pill--float')).to.equal(true);
        const inp = el.shadowRoot.querySelector('platform-field-string').shadowRoot.querySelector('input');
        expect(inp.placeholder).to.equal('type here');
    });

    it('view-режим: label всегда floated', async () => {
        const el = await fixture(html`
            <platform-field type="string" mode="view" label="Name" value=""></platform-field>
        `);
        expect(shellRoot(el).querySelector('fieldset').classList.contains('field-pill--float')).to.equal(true);
    });

    it('focusin внутри поднимает placeholder и метит _focused', async () => {
        const el = await fixture(html`
            <platform-field
                type="string"
                mode="edit"
                label="Name"
                placeholder="type here"
                value=""
            ></platform-field>
        `);
        const inner = el.shadowRoot.querySelector('platform-field-string');
        const inp = inner.shadowRoot.querySelector('input');
        inp.dispatchEvent(new FocusEvent('focusin', { bubbles: true, composed: true }));
        await elementUpdated(el);
        expect(el._focused).to.equal(true);
        await elementUpdated(inner);
        expect(inp.placeholder).to.equal('type here');
    });

    it('error property: field-pill--error + сообщение под полем', async () => {
        const el = await fixture(html`
            <platform-field type="string" mode="edit" label="Name" value="" .error=${'required'}></platform-field>
        `);
        const fs = shellRoot(el).querySelector('fieldset');
        expect(fs.classList.contains('field-pill--error')).to.equal(true);
        const msg = shellRoot(el).querySelector('.field-pill-message');
        expect(msg).to.exist;
        expect(msg.textContent).to.equal('required');
    });

    it('editable: клик по pill прокидывает фокус во вложенный input', async () => {
        const el = await fixture(html`
            <platform-field type="string" mode="edit" label="Name" value=""></platform-field>
        `);
        shellRoot(el).querySelector('fieldset').dispatchEvent(new MouseEvent('click', { bubbles: true }));
        const inp = el.shadowRoot.querySelector('platform-field-string').shadowRoot.querySelector('input');
        expect(document.activeElement === inp || el.contains(document.activeElement)).to.equal(true);
    });
});
