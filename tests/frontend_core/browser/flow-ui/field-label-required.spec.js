/**
 * Browser: required asterisk stays inline with the caption inside one .field-label.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import {
    renderFieldError,
    renderInputLabelText,
} from '@platform/lib/flow-ui/catalog/render-helpers.js';

describe('flow-ui field label required chrome', () => {
    afterEach(() => {
        fixtureCleanup();
    });

    it('keeps required asterisk inside one .field-label node', async () => {
        const component = {
            component_id: 'name',
            checks: [{ function: 'required', message: 'need name' }],
        };
        const el = await fixture(html`<div>${renderInputLabelText({}, component, 'Name')}</div>`);
        await elementUpdated(el);
        const label = el.querySelector('.field-label');
        expect(label).to.exist;
        expect(label.textContent).to.equal('Name*');
        expect(label.querySelector('.field-required')?.textContent).to.equal('*');
        expect(el.children).to.have.length(1);
    });

    it('renders field error below as a separate alert node', async () => {
        const component = { component_id: 'name' };
        const host = { controller: { fieldErrors: { name: 'required' } } };
        const el = await fixture(html`<div>${renderFieldError(host, component)}</div>`);
        await elementUpdated(el);
        const error = el.querySelector('.field-error');
        expect(error).to.exist;
        expect(error.getAttribute('role')).to.equal('alert');
        expect(error.textContent).to.equal('required');
    });
});
