/**
 * Smoke: flows-args-schema-form — рендер по типам, emit change.
 */

import { fixture, fixtureCleanup, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../apps/flows/ui/components/editors/flows-args-schema-form.js';

describe('flows-args-schema-form', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });
    afterEach(() => fixtureCleanup());

    it('пустая схема рендерит empty', async () => {
        const el = await fixture(html`<flows-args-schema-form .schema=${{}}></flows-args-schema-form>`);
        expect(el.shadowRoot.querySelector('.empty')).to.not.be.null;
    });

    it('string поле эмитит change', async () => {
        const schema = { name: { type: 'string', description: 'имя', required: true } };
        const el = await fixture(html`<flows-args-schema-form .schema=${schema} .values=${{}}></flows-args-schema-form>`);
        let last = null;
        el.addEventListener('change', (e) => {
            if (e.detail && typeof e.detail.values === 'object' && e.detail.values !== null) {
                last = e.detail;
            }
        });
        const pf = el.shadowRoot.querySelector('platform-field[type="string"]');
        const inner = pf.shadowRoot.querySelector('platform-field-string');
        const input = inner.shadowRoot.querySelector('input');
        input.value = 'Vova';
        input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        expect(last).to.deep.equal({ values: { name: 'Vova' } });
    });

    it('boolean поле — checkbox', async () => {
        const schema = { active: { type: 'boolean' } };
        const el = await fixture(html`<flows-args-schema-form .schema=${schema} .values=${{ active: true }}></flows-args-schema-form>`);
        const cb = el.shadowRoot.querySelector('input[type="checkbox"]');
        expect(cb.checked).to.equal(true);
    });
});
