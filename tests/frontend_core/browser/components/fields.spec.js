/**
 * platform-field-* — поля типизированного отображения/редактирования.
 */

import { fixture, html, expect, oneEvent } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/fields/platform-field-string.js';
import '@platform/lib/components/fields/platform-field-number.js';
import '@platform/lib/components/fields/platform-field-boolean.js';
import '@platform/lib/components/fields/platform-field-date.js';
import '@platform/lib/components/fields/platform-field-enum.js';
import '@platform/lib/components/fields/platform-field-text.js';
import '@platform/lib/components/fields/platform-field-array.js';
import '@platform/lib/components/fields/platform-field-object.js';

beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

describe('platform-field-string', () => {
    it('view mode рендерит значение', async () => {
        const el = await fixture(html`<platform-field-string mode="view" value="hello"></platform-field-string>`);
        expect(el.shadowRoot.querySelector('.view-value').textContent).to.equal('hello');
    });

    it('edit mode рендерит input и эмитит change', async () => {
        const el = await fixture(html`<platform-field-string mode="edit" value="x"></platform-field-string>`);
        const inp = el.shadowRoot.querySelector('input');
        const promise = oneEvent(el, 'change');
        inp.value = 'updated';
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        const ev = await promise;
        expect(ev.detail.value).to.equal('updated');
    });
});

describe('platform-field-number', () => {
    it('рендерится в обоих режимах', async () => {
        const view = await fixture(html`<platform-field-number mode="view" value="42"></platform-field-number>`);
        expect(view.shadowRoot).to.exist;
        const edit = await fixture(html`<platform-field-number mode="edit" value="42"></platform-field-number>`);
        expect(edit.shadowRoot.querySelector('input')).to.exist;
    });
});

describe('platform-field-boolean / date / enum / text / array / object: smoke', () => {
    it('boolean рендерится', async () => {
        const el = await fixture(html`<platform-field-boolean mode="view" .value=${true}></platform-field-boolean>`);
        expect(el.shadowRoot).to.exist;
    });

    it('date рендерится', async () => {
        const el = await fixture(html`<platform-field-date mode="view" value="2026-01-01"></platform-field-date>`);
        expect(el.shadowRoot).to.exist;
    });

    it('enum рендерится', async () => {
        const el = await fixture(html`<platform-field-enum mode="view" value="a" .options=${[{ value: 'a', label: 'A' }]}></platform-field-enum>`);
        expect(el.shadowRoot).to.exist;
    });

    it('text рендерится', async () => {
        const el = await fixture(html`<platform-field-text mode="view" value="t"></platform-field-text>`);
        expect(el.shadowRoot).to.exist;
    });

    it('array рендерится', async () => {
        const el = await fixture(html`<platform-field-array mode="view" .value=${[1, 2]}></platform-field-array>`);
        expect(el.shadowRoot).to.exist;
    });

    it('object рендерится', async () => {
        const el = await fixture(html`<platform-field-object mode="view" .value=${{ a: 1 }}></platform-field-object>`);
        expect(el.shadowRoot).to.exist;
    });
});
