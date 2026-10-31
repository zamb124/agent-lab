/**
 * Smoke: flows-parameters-schema-form — рендер по типам, emit change.
 */

import { fixture, fixtureCleanup, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../apps/flows/ui/components/editors/flows-parameters-schema-form.js';
import {q, qs, shadow, type TestEl} from '../helpers/dom.js';

describe('flows-parameters-schema-form', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });
    afterEach(() => fixtureCleanup());

    it('пустая схема рендерит empty', async () => {
        const el = await fixture<TestEl>(html`<flows-parameters-schema-form .schema=${{}}></flows-parameters-schema-form>`);
        expect(q(shadow(el), 'platform-empty-state')).to.not.be.null;
    });

    it('string поле эмитит change', async () => {
        const schema = { name: { type: 'string', description: 'имя', required: true } };
        const el = await fixture<TestEl>(html`<flows-parameters-schema-form .schema=${schema} .values=${{}}></flows-parameters-schema-form>`);
        let last = null;
        el.addEventListener('change', (e) => {
            if ((e as CustomEvent).detail && typeof (e as CustomEvent).detail.values === 'object' && (e as CustomEvent).detail.values !== null) {
                last = (e as CustomEvent).detail;
            }
        });
        const pf = qs(shadow(el), 'platform-field[type="string"]');
        const inner = qs(shadow(pf), 'platform-field-string');
        const input = qs(shadow(inner), 'input');
        (input as TestEl).value = 'Vova';
        input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        expect(last).to.deep.equal({ values: { name: 'Vova' } });
    });

    it('boolean поле — platform-field', async () => {
        const schema = { active: { type: 'boolean' } };
        const el = await fixture<TestEl>(html`<flows-parameters-schema-form .schema=${schema} .values=${{ active: true }}></flows-parameters-schema-form>`);
        const pf = q(shadow(el), 'platform-field[type="boolean"]');
        expect(pf).to.not.equal(null);
        expect((pf as TestEl).value).to.equal(true);
    });
});
