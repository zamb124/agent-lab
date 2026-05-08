/**
 * platform-field-* — поля типизированного отображения/редактирования.
 *
 * После PHASE 1.5: платформа имеет один канон pill (<platform-field>),
 * подкомпоненты используют классы field-pill-input/-textarea/-select,
 * у platform-field-string есть property inputType (text|email|password|url|tel|search).
 */

import { fixture, html, expect, oneEvent } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/fields/platform-field.js';
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

describe('platform-field dispatcher', () => {
    it('edit + label: pill, label и field-pill-input в shadowRoot', async () => {
        const el = await fixture(html`
            <platform-field
                type="string"
                mode="edit"
                label="TestLabel"
                value="x"
            ></platform-field>
        `);
        const pill = el.shadowRoot.querySelector('.field-pill');
        expect(pill).to.exist;
        const lab = el.shadowRoot.querySelector('.field-pill-label');
        expect(lab).to.exist;
        expect(lab.textContent).to.equal('TestLabel');
        expect(el.shadowRoot.querySelector('.field-pill-control')).to.exist;
        expect(el.shadowRoot.querySelector('.field-pill-control-main')).to.exist;
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
        const pill = el.shadowRoot.querySelector('.field-pill');
        expect(pill.classList.contains('field-pill--compact')).to.equal(true);
    });

    it('без label не рендерит field-pill-label, но рисует pill', async () => {
        const el = await fixture(html`<platform-field type="string" mode="edit" value=""></platform-field>`);
        expect(el.shadowRoot.querySelector('.field-pill')).to.exist;
        expect(el.shadowRoot.querySelector('.field-pill-label')).to.be.null;
    });

    it('пробрасывает inputType="email" в подкомпонент', async () => {
        const el = await fixture(html`
            <platform-field type="string" input-type="email" mode="edit" value="a@b.c"></platform-field>
        `);
        const inner = el.shadowRoot.querySelector('platform-field-string');
        const inp = inner.shadowRoot.querySelector('input.field-pill-input');
        expect(inp.getAttribute('type')).to.equal('email');
    });

    it('view-режим рендерит pill + field-pill-readonly-text', async () => {
        const el = await fixture(html`<platform-field type="string" mode="view" label="L" value="visible"></platform-field>`);
        expect(el.shadowRoot.querySelector('.field-pill')).to.exist;
        expect(el.shadowRoot.querySelector('.field-pill-label').textContent).to.equal('L');
        const inner = el.shadowRoot.querySelector('platform-field-string');
        expect(inner.shadowRoot.querySelector('.field-pill-readonly-text').textContent).to.equal('visible');
    });

    it('hint property рисует <platform-help-hint> рядом с label', async () => {
        const el = await fixture(html`
            <platform-field
                type="string"
                mode="edit"
                .label=${'X'}
                .value=${'v'}
                .hint=${'tooltip text'}
            ></platform-field>
        `);
        const head = el.shadowRoot.querySelector('.field-pill-head');
        expect(head).to.exist;
        const hint = head.querySelector('platform-help-hint');
        expect(hint).to.exist;
        expect(hint.text).to.equal('tooltip text');
    });

    it('без hint — не рендерит <platform-help-hint>', async () => {
        const el = await fixture(html`<platform-field type="string" mode="edit" label="X" value=""></platform-field>`);
        expect(el.shadowRoot.querySelector('platform-help-hint')).to.be.null;
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

    it('inputType вне списка — throws при render', async () => {
        let caught = null;
        try {
            await fixture(html`
                <platform-field-string mode="edit" value="" .inputType=${'date'}></platform-field-string>
            `);
        } catch (err) {
            caught = err;
        }
        expect(caught).to.be.an('error');
        expect(String(caught.message)).to.match(/inputType/);
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

    it('edit с {value,label}: option рендерит label', async () => {
        const el = await fixture(html`
            <platform-field-enum
                mode="edit"
                value="x"
                .config=${{ values: [{ value: 'x', label: 'X-Label' }, { value: 'y', label: 'Y-Label' }] }}
            ></platform-field-enum>
        `);
        const sel = el.shadowRoot.querySelector('select.field-pill-select');
        expect(sel).to.exist;
        const options = sel.querySelectorAll('option');
        expect(options[1].value).to.equal('x');
        expect(options[1].textContent.trim()).to.equal('X-Label');
        expect(options[2].value).to.equal('y');
        expect(options[2].textContent.trim()).to.equal('Y-Label');
    });

    it('edit с массивом строк: option value=label', async () => {
        const el = await fixture(html`
            <platform-field-enum mode="edit" value="a" .config=${{ values: ['a', 'b'] }}></platform-field-enum>
        `);
        const options = el.shadowRoot.querySelectorAll('option');
        expect(options[1].value).to.equal('a');
        expect(options[1].textContent.trim()).to.equal('a');
    });

    it('edit: {value: "", label} без дублирующего --', async () => {
        const el = await fixture(html`
            <platform-field-enum
                mode="edit"
                value=""
                .config=${{ values: [{ value: '', label: 'Default row' }, { value: 'x', label: 'X' }] }}
            ></platform-field-enum>
        `);
        const options = el.shadowRoot.querySelectorAll('option');
        expect(options.length).to.equal(2);
        expect(options[0].value).to.equal('');
        expect(options[0].textContent.trim()).to.equal('Default row');
        expect(options[1].value).to.equal('x');
    });
});

describe('platform-field-boolean / date / array / object: smoke', () => {
    it('boolean рендерится', async () => {
        const el = await fixture(html`<platform-field-boolean mode="view" .value=${true}></platform-field-boolean>`);
        expect(el.shadowRoot).to.exist;
    });

    it('date рендерится в view', async () => {
        const el = await fixture(html`<platform-field-date mode="view" value="2026-01-01"></platform-field-date>`);
        expect(el.shadowRoot.querySelector('.field-pill-readonly-text').textContent).to.equal('2026-01-01');
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
