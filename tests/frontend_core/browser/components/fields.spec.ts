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
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

const shellRoot = (el: any): ShadowRoot => shadow(qs(shadow(el), 'platform-field-shell'));

describe('platform-field dispatcher', () => {
    it('edit + label: shell, floating label и field-pill-input в shadowRoot', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field
                type="string"
                mode="edit"
                label="TestLabel"
                value="x"
            ></platform-field>
        `);
        const pill = qs(shellRoot(el), 'fieldset.field-pill');
        expect(pill).to.exist;
        const lab = qs(shellRoot(el), '.field-pill-label');
        expect(lab).to.exist;
        expect(lab.textContent).to.equal('TestLabel');
        expect(qs(shellRoot(el), '.field-pill-control')).to.exist;
        expect(qs(shellRoot(el), '.field-pill-control-main')).to.exist;
        const inner = qs(shadow(el), 'platform-field-string');
        expect(inner).to.exist;
        const inp = qs(shadow(inner), 'input.field-pill-input');
        expect(inp).to.exist;
        expect(inp.getAttribute('type')).to.equal('text');
    });

    it('pill-density="compact" добавляет field-pill--compact', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field type="string" mode="edit" value="" pill-density="compact"></platform-field>
        `);
        const pill = qs(shellRoot(el), '.field-pill');
        expect(pill.classList.contains('field-pill--compact')).to.equal(true);
    });

    it('pill-density="dense" добавляет field-pill--compact и field-pill--dense', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field type="string" mode="edit" value="" pill-density="dense"></platform-field>
        `);
        const pill = qs(shellRoot(el), '.field-pill');
        expect(pill.classList.contains('field-pill--compact')).to.equal(true);
        expect(pill.classList.contains('field-pill--dense')).to.equal(true);
    });

    it('pill-embed добавляет field-pill--embed', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field type="string" mode="edit" value="" pill-embed label="InCard"></platform-field>
        `);
        const pill = qs(shellRoot(el), '.field-pill');
        expect(pill.classList.contains('field-pill--embed')).to.equal(true);
    });

    it('без label не рендерит field-pill-label, но рисует pill', async () => {
        const el = await fixture<TestEl>(html`<platform-field type="string" mode="edit" value=""></platform-field>`);
        expect(q(shellRoot(el), '.field-pill')).to.exist;
        expect(q(shellRoot(el), '.field-pill-label')).to.be.null;
    });

    it('пробрасывает inputType="email" в подкомпонент', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field type="string" input-type="email" mode="edit" value="a@b.c"></platform-field>
        `);
        const inner = qs(shadow(el), 'platform-field-string');
        const inp = qs(shadow(inner), 'input.field-pill-input');
        expect(inp.getAttribute('type')).to.equal('email');
    });

    it('пробрасывает suggestions в string-подкомпонент как datalist', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field
                type="string"
                mode="edit"
                value=""
                .suggestions=${['state.user.name', '', 'state.order.total']}
            ></platform-field>
        `);
        const inner = qs(shadow(el), 'platform-field-string');
        const inp = qs(shadow(inner), 'input.field-pill-input');
        const listId = inp.getAttribute('list');
        const list = qs(shadow(inner), `datalist#${listId}`);
        const options = Array.from(qsa(list!, 'option')).map((option) => (option as TestEl).value);
        expect(options).to.deep.equal(['state.user.name', 'state.order.total']);
    });

    it('view-режим рендерит pill + field-pill-readonly-text', async () => {
        const el = await fixture<TestEl>(html`<platform-field type="string" mode="view" label="L" value="visible"></platform-field>`);
        expect(qs(shellRoot(el), '.field-pill')).to.exist;
        expect(qs(shellRoot(el), '.field-pill-label').textContent).to.equal('L');
        const inner = qs(shadow(el), 'platform-field-string');
        expect(qs(shadow(inner), '.field-pill-readonly-text').textContent).to.equal('visible');
    });

    it('hint property рисует <platform-help-hint> рядом с floating label', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field
                type="string"
                mode="edit"
                .label=${'X'}
                .value=${'v'}
                .hint=${'tooltip text'}
            ></platform-field>
        `);
        const float = qs(shellRoot(el), '.field-pill-float');
        expect(float).to.exist;
        const hint = qs(float!, 'platform-help-hint');
        expect(hint).to.exist;
        expect(hint.text).to.equal('tooltip text');
    });

    it('без hint — не рендерит <platform-help-hint>', async () => {
        const el = await fixture<TestEl>(html`<platform-field type="string" mode="edit" label="X" value=""></platform-field>`);
        expect(q(shellRoot(el), 'platform-help-hint')).to.be.null;
    });

    it('slot prefix: элемент с slot=prefix попадает в named slot', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field type="string" mode="edit" value="">
                <span slot="prefix" class="prefix-marker">P</span>
            </platform-field>
        `);
        const slotEl = qs(shadow(el), 'slot[name="prefix"]');
        expect(slotEl).to.exist;
        const assigned = slotEl.assignedElements().find((n: any) => n.classList.contains('prefix-marker'));
        expect(assigned).to.exist;
    });

    it('slot suffix: элемент с slot=suffix попадает в named slot', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field type="string" mode="view" label="L" value="id1">
                <span slot="suffix" class="suffix-marker">S</span>
            </platform-field>
        `);
        const slotEl = qs(shadow(el), 'slot[name="suffix"]');
        expect(slotEl).to.exist;
        const assigned = slotEl.assignedElements().find((n: any) => n.classList.contains('suffix-marker'));
        expect(assigned).to.exist;
    });

    it('type=array: allowed_values — combobox и change.(detail as TestEl).value', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field
                type="array"
                mode="edit"
                .value=${[]}
                .config=${{ allowed_values: ['A', 'B'] }}
                .placeholder=${'Pick'}
            ></platform-field>
        `);
        const inner = qs(shadow(el), 'platform-field-array');
        const sel = qs(shadow(inner), 'select[data-canon="combobox"]');
        expect(sel).to.exist;
        (sel as TestEl).value = 'A';
        const p = oneEvent(el, 'change');
        sel.dispatchEvent(new Event('change', { bubbles: true }));
        const ev = await p;
        expect((ev as CustomEvent).detail.value).to.deep.equal(['A']);
    });

    it('type=array: preserve_case на tag-input', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field
                type="array"
                mode="edit"
                .value=${[]}
                .config=${{ preserve_case: true }}
            ></platform-field>
        `);
        const inner = qs(shadow(el), 'platform-field-array');
        const ti = qs(shadow(inner), 'tag-input');
        expect(ti.preserveCase).to.equal(true);
    });
});

describe('platform-field-string inputType', () => {
    const ALLOWED = ['text', 'email', 'password', 'url', 'tel', 'search'];

    for (const t of ALLOWED) {
        it(`inputType="${t}" рендерит <input type="${t}">`, async () => {
            const el = await fixture<TestEl>(html`
                <platform-field-string mode="edit" value="" .inputType=${t}></platform-field-string>
            `);
            const inp = qs(shadow(el), 'input.field-pill-input');
            expect(inp.getAttribute('type')).to.equal(t);
        });
    }

    it('inputType вне списка — fails fast в валидаторе', () => {
        const el = (document.createElement('platform-field-string') as TestEl);
        el.inputType = 'date';
        expect(() => el._resolvedInputType()).to.throw(/inputType/);
    });

    it('password в view-режиме маскирует значение', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-string mode="view" value="secret" .inputType=${'password'}></platform-field-string>
        `);
        const text = qs(shadow(el), '.field-pill-readonly-text').textContent;
        expect(text).to.match(/^•+$/);
    });
});

describe('platform-field-string base', () => {
    it('view mode без значения рендерит field-pill-empty', async () => {
        const el = await fixture<TestEl>(html`<platform-field-string mode="view" value=""></platform-field-string>`);
        expect(qs(shadow(el), '.field-pill-empty')).to.exist;
    });

    it('edit mode рендерит input и эмитит change', async () => {
        const el = await fixture<TestEl>(html`<platform-field-string mode="edit" value="x"></platform-field-string>`);
        const inp = qs(shadow(el), 'input.field-pill-input');
        const promise = oneEvent(el, 'change');
        (inp as TestEl).value = 'updated';
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        const ev = await promise;
        expect((ev as CustomEvent).detail.value).to.equal('updated');
    });

    it('disabled пробрасывается на input', async () => {
        const el = await fixture<TestEl>(html`<platform-field-string mode="edit" value="x" ?disabled=${true}></platform-field-string>`);
        const inp = qs(shadow(el), 'input.field-pill-input');
        expect(inp.disabled).to.equal(true);
    });

    it('placeholder пробрасывается на input', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-string mode="edit" value="" .placeholder=${'hint here'}></platform-field-string>
        `);
        const inp = qs(shadow(el), 'input.field-pill-input');
        expect(inp.placeholder).to.equal('hint here');
    });
});

describe('platform-field-text', () => {
    it('view-mode рендерит field-pill-readonly-text', async () => {
        const el = await fixture<TestEl>(html`<platform-field-text mode="view" value="multi"></platform-field-text>`);
        expect(qs(shadow(el), '.field-pill-readonly-text').textContent).to.equal('multi');
    });

    it('edit-mode рендерит textarea.field-pill-textarea', async () => {
        const el = await fixture<TestEl>(html`<platform-field-text mode="edit" value=""></platform-field-text>`);
        const ta = qs(shadow(el), 'textarea.field-pill-textarea');
        expect(ta).to.exist;
    });
});

describe('platform-field-number', () => {
    it('рендерится в обоих режимах', async () => {
        const view = await fixture<TestEl>(html`<platform-field-number mode="view" value="42"></platform-field-number>`);
        expect(shadow(view)).to.exist;
        const edit = await fixture<TestEl>(html`<platform-field-number mode="edit" value="42"></platform-field-number>`);
        const inp = qs(shadow(edit), 'input.field-pill-input');
        expect(inp).to.exist;
        expect(inp.getAttribute('type')).to.equal('number');
    });
});

describe('platform-field-enum', () => {
    it('view: empty', async () => {
        const el = await fixture<TestEl>(html`<platform-field-enum mode="view" value=""></platform-field-enum>`);
        expect(qs(shadow(el), '.field-pill-empty')).to.exist;
    });

    it('view с массивом строк: chip отображает value', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-enum mode="view" value="a" .config=${{ values: ['a', 'b'] }}></platform-field-enum>
        `);
        expect(qs(shadow(el), '.enum-chip').textContent).to.equal('a');
    });

    it('view с массивом {value,label}: chip отображает label', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-enum
                mode="view"
                value="active"
                .config=${{ values: [{ value: 'active', label: 'Активно' }, { value: 'archived', label: 'В архиве' }] }}
            ></platform-field-enum>
        `);
        expect(qs(shadow(el), '.enum-chip').textContent).to.equal('Активно');
    });

    it('edit: input получает pill-стили (transparent, наследованный шрифт)', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-enum
                mode="edit"
                value="x"
                .config=${{ values: [{ value: 'x', label: 'X' }] }}
            ></platform-field-enum>
        `);
        const inp = qs(shadow(el), 'input.field-pill-enum-input');
        expect(inp).to.exist;
        const cs = getComputedStyle(inp);
        expect(cs.backgroundColor).to.equal('rgba(0, 0, 0, 0)');
        expect(cs.borderTopWidth).to.equal('0px');
        const chevron = qs(shadow(el), '.field-pill-enum-chevron');
        expect(getComputedStyle(chevron).position).to.equal('absolute');
    });

    it('edit: combobox и список label при фокусе', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-enum
                mode="edit"
                value="x"
                .config=${{ values: [{ value: 'x', label: 'X-Label' }, { value: 'y', label: 'Y-Label' }] }}
            ></platform-field-enum>
        `);
        const inp = qs(shadow(el), 'input.field-pill-enum-input');
        expect(inp).to.exist;
        inp.focus();
        await elementUpdated(el);
        const rowX = qs(shadow(el), '[data-enum-value="x"]');
        const rowY = qs(shadow(el), '[data-enum-value="y"]');
        expect(rowX).to.exist;
        expect(rowY).to.exist;
        expect(rowX.textContent.trim()).to.equal('X-Label');
        expect(rowY.textContent.trim()).to.equal('Y-Label');
    });

    it('edit: при открытии списка значение выделяется целиком, выбранная опция с галочкой', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-enum
                mode="edit"
                value="a"
                .config=${{ values: [{ value: 'a', label: 'Alpha' }, { value: 'b', label: 'Beta' }] }}
            ></platform-field-enum>
        `);
        const inp = qs(shadow(el), 'input.field-pill-enum-input') as HTMLInputElement;
        inp.focus();
        await elementUpdated(el);
        await new Promise((resolve) => { window.setTimeout(resolve, 0); });
        expect(inp.selectionStart).to.equal(0);
        expect(inp.selectionEnd).to.equal(inp.value.length);
        const selected = qs(shadow(el), '.enum-option--selected');
        expect(selected).to.exist;
        expect(qs(selected, 'platform-icon.enum-option-check')).to.exist;
    });

    it('edit с массивом строк: data-enum-value совпадает с value опции', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-enum mode="edit" value="a" .config=${{ values: ['a', 'b'] }}></platform-field-enum>
        `);
        const inp = qs(shadow(el), 'input.field-pill-enum-input');
        inp.focus();
        await elementUpdated(el);
        const rows = Array.from(qsa(shadow(el), '[data-enum-value]'));
        expect(rows.length).to.equal(3);
        expect(rows.some((li) => li.getAttribute('data-enum-value') === '')).to.equal(true);
        expect(rows.some((li) => li.getAttribute('data-enum-value') === 'a')).to.equal(true);
        expect(rows.some((li) => li.getAttribute('data-enum-value') === 'b')).to.equal(true);
    });

    it('edit: {value: "", label} без дублирующей синтетической пустой строки', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-enum
                mode="edit"
                value=""
                .config=${{ values: [{ value: '', label: 'Default row' }, { value: 'x', label: 'X' }] }}
            ></platform-field-enum>
        `);
        const inp = qs(shadow(el), 'input.field-pill-enum-input');
        inp.focus();
        await elementUpdated(el);
        const rows = Array.from(qsa(shadow(el), '[data-enum-value]'));
        expect(rows.length).to.equal(2);
        const emptyRow = rows.find((li) => li.getAttribute('data-enum-value') === '');
        expect(emptyRow!.textContent.trim()).to.equal('Default row');
        const xRow = rows.find((li) => li.getAttribute('data-enum-value') === 'x');
        expect(xRow!.textContent.trim()).to.equal('X');
    });

    it('edit: фильтрует опции при вводе', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-enum
                mode="edit"
                value="a"
                .config=${{ values: [{ value: 'a', label: 'Alpha' }, { value: 'b', label: 'Beta' }] }}
            ></platform-field-enum>
        `);
        const inp = qs(shadow(el), 'input.field-pill-enum-input');
        inp.focus();
        await elementUpdated(el);
        (inp as TestEl).value = 'Bet';
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        await elementUpdated(el);
        const items = qsa(shadow(el), '[data-enum-value]');
        expect(items.length).to.equal(1);
        expect(items[0]!.getAttribute('data-enum-value')).to.equal('b');
    });

    it('edit: выбор опции испускает change', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-enum mode="edit" value="a" .config=${{ values: ['a', 'b'] }}></platform-field-enum>
        `);
        const inp = qs(shadow(el), 'input.field-pill-enum-input');
        inp.focus();
        await elementUpdated(el);
        const p = oneEvent(el, 'change');
        const row = qs(shadow(el), '[data-enum-value="b"]');
        expect(row).to.exist;
        (row as TestEl).click();
        const ev = await p;
        expect((ev as CustomEvent).detail.value).to.equal('b');
    });

    it('edit: chevron после выбора открывает полный список без очистки текста', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-enum
                mode="edit"
                value="a"
                .config=${{ values: [{ value: 'a', label: 'Alpha' }, { value: 'b', label: 'Beta' }] }}
            ></platform-field-enum>
        `);
        const inp = qs(shadow(el), 'input.field-pill-enum-input');
        inp.focus();
        await elementUpdated(el);
        (inp as TestEl).value = 'Bet';
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        await elementUpdated(el);
        const change = oneEvent(el, 'change');
        qs(shadow(el), '[data-enum-value="b"]').click();
        await change;
        await elementUpdated(el);

        const chevron = qs(shadow(el), '.field-pill-enum-chevron');
        (chevron as TestEl).click();
        await elementUpdated(el);

        const values = Array.from(qsa(shadow(el), '[data-enum-value]'))
            .map((li) => li.getAttribute('data-enum-value'));
        expect(values).to.deep.equal(['', 'a', 'b']);
    });
});

describe('platform-field-boolean / date / array / object: smoke', () => {
    it('boolean рендерится', async () => {
        const el = await fixture<TestEl>(html`<platform-field-boolean mode="view" .value=${true}></platform-field-boolean>`);
        expect(shadow(el)).to.exist;
    });

    it('date рендерится в view', async () => {
        const el = await fixture<TestEl>(html`<platform-field-date mode="view" value="2026-01-01"></platform-field-date>`);
        const locale = (getPlatformBus().getState() as Record<string, any>).i18n.locale;
        const expected = formatPlatformDate('2026-01-01', locale);
        expect(qs(shadow(el), '.field-pill-readonly-text').textContent).to.equal(expected);
    });

    it('array рендерится', async () => {
        const el = await fixture<TestEl>(html`<platform-field-array mode="view" .value=${['x', 'y']}></platform-field-array>`);
        expect(shadow(el)).to.exist;
    });

    it('object рендерится', async () => {
        const el = await fixture<TestEl>(html`<platform-field-object mode="view" .value=${{ a: 1 }}></platform-field-object>`);
        expect(qs(shadow(el), '.view-json')).to.exist;
    });

    it('external_refs view рендерит empty при отсутствии данных', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-external-refs mode="view" .value=${null}></platform-field-external-refs>
        `);
        expect(qs(shadow(el), '.field-pill-empty')).to.exist;
    });
});

describe('platform-field-shell', () => {
    it('label: <fieldset>+<legend> notch и resting label внутри контрола', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-shell label="Notch" editable>
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        const fs = qs(shadow(el), 'fieldset.field-pill');
        expect(fs).to.exist;
        expect(fs.getAttribute('aria-label')).to.equal('Notch');
        const legend = qs(fs!, 'legend.field-pill-legend .field-pill-legend-text');
        expect(legend).to.exist;
        expect(legend.textContent).to.equal('Notch');
        const float = qs(fs!, '.field-pill-float .field-pill-label');
        expect(float).to.exist;
        expect(float.textContent).to.equal('Notch');
    });

    it('floated: fieldset получает field-pill--float', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-shell label="L" floated>
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        expect(qs(shadow(el), 'fieldset').classList.contains('field-pill--float')).to.equal(true);
    });

    it('без floated: resting label без field-pill--float', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-shell label="L">
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        expect(qs(shadow(el), 'fieldset').classList.contains('field-pill--float')).to.equal(false);
    });

    it('error: field-pill--error + .field-pill-message[role=alert]', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-shell label="L" error="boom">
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        expect(qs(shadow(el), 'fieldset').classList.contains('field-pill--error')).to.equal(true);
        const msg = qs(shadow(el), '.field-pill-message');
        expect(msg).to.exist;
        expect(msg.getAttribute('role')).to.equal('alert');
        expect(msg.textContent).to.equal('boom');
    });

    it('disabled: field-pill--disabled', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-shell label="L" disabled>
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        expect(qs(shadow(el), 'fieldset').classList.contains('field-pill--disabled')).to.equal(true);
    });

    it('density вне списка — fails fast', async () => {
        const el = (document.createElement('platform-field-shell') as TestEl);
        el.density = 'huge';
        expect(() => el.willUpdate(new Map([['density', 'huge']]))).to.throw(/density/);
    });

    it('editable: клик по pill фокусирует slotted input', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-shell label="L" editable>
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        qs(shadow(el), 'fieldset').dispatchEvent(new MouseEvent('click', { bubbles: true }));
        const inp = qs(el!, 'input');
        expect(document.activeElement === inp || el.contains(document.activeElement)).to.equal(true);
    });

    it('не editable: клик по pill не забирает фокус', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field-shell label="L">
                <input type="text" class="field-pill-input" />
            </platform-field-shell>
        `);
        qs(shadow(el), 'fieldset').dispatchEvent(new MouseEvent('click', { bubbles: true }));
        expect(document.activeElement).to.not.equal(qs(el!, 'input'));
    });
});

describe('platform-field floating label', () => {
    it('edit + пустое значение: resting label (без --float), placeholder подавлен', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field
                type="string"
                mode="edit"
                label="Name"
                placeholder="type here"
                value=""
            ></platform-field>
        `);
        const fs = qs(shellRoot(el), 'fieldset');
        expect(fs.classList.contains('field-pill--float')).to.equal(false);
        const inp = qs(shadow(qs(shadow(el), 'platform-field-string')), 'input');
        expect(inp.placeholder).to.equal('');
    });

    it('edit + значение: label улетел (field-pill--float), placeholder виден', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field
                type="string"
                mode="edit"
                label="Name"
                placeholder="type here"
                value="v"
            ></platform-field>
        `);
        const fs = qs(shellRoot(el), 'fieldset');
        expect(fs.classList.contains('field-pill--float')).to.equal(true);
        const inp = qs(shadow(qs(shadow(el), 'platform-field-string')), 'input');
        expect(inp.placeholder).to.equal('type here');
    });

    it('view-режим: label всегда floated', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field type="string" mode="view" label="Name" value=""></platform-field>
        `);
        expect(qs(shellRoot(el), 'fieldset').classList.contains('field-pill--float')).to.equal(true);
    });

    it('ввод текста без родительского ребиндинга .value: label улетает (mirror value)', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field type="string" mode="edit" label="Name" value=""></platform-field>
        `);
        const inner = qs(shadow(el), 'platform-field-string');
        const inp = qs(shadow(inner), 'input');
        inp.value = 'typed';
        inp.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true }));
        await elementUpdated(el);
        expect(el.value).to.equal('typed');
        await elementUpdated(el);
        const fs = qs(shellRoot(el), 'fieldset');
        expect(fs.classList.contains('field-pill--float')).to.equal(true);
    });

    it('blur после ввода: label остаётся floated, resting-текст не возвращается под значение', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field type="string" mode="edit" label="Name" value=""></platform-field>
        `);
        const inner = qs(shadow(el), 'platform-field-string');
        const inp = qs(shadow(inner), 'input');
        inp.dispatchEvent(new FocusEvent('focusin', { bubbles: true, composed: true }));
        inp.value = 'typed';
        inp.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true }));
        inp.dispatchEvent(new FocusEvent('focusout', { bubbles: true, composed: true }));
        await elementUpdated(el);
        await new Promise((r) => setTimeout(r, 20));
        await elementUpdated(el);
        const fs = qs(shellRoot(el), 'fieldset');
        expect(fs.classList.contains('field-pill--float')).to.equal(true);
    });

    it('focusin внутри поднимает placeholder и метит _focused', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field
                type="string"
                mode="edit"
                label="Name"
                placeholder="type here"
                value=""
            ></platform-field>
        `);
        const inner = qs(shadow(el), 'platform-field-string');
        const inp = qs(shadow(inner), 'input');
        inp.dispatchEvent(new FocusEvent('focusin', { bubbles: true, composed: true }));
        await elementUpdated(el);
        expect(el._focused).to.equal(true);
        await elementUpdated(inner);
        expect(inp.placeholder).to.equal('type here');
    });

    it('error property: field-pill--error + сообщение под полем', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field type="string" mode="edit" label="Name" value="" .error=${'required'}></platform-field>
        `);
        const fs = qs(shellRoot(el), 'fieldset');
        expect(fs.classList.contains('field-pill--error')).to.equal(true);
        const msg = qs(shellRoot(el), '.field-pill-message');
        expect(msg).to.exist;
        expect(msg.textContent).to.equal('required');
    });

    it('editable: клик по pill прокидывает фокус во вложенный input', async () => {
        const el = await fixture<TestEl>(html`
            <platform-field type="string" mode="edit" label="Name" value=""></platform-field>
        `);
        qs(shellRoot(el), 'fieldset').dispatchEvent(new MouseEvent('click', { bubbles: true }));
        const inp = qs(shadow(qs(shadow(el), 'platform-field-string')), 'input');
        expect(document.activeElement === inp || el.contains(document.activeElement)).to.equal(true);
    });
});
