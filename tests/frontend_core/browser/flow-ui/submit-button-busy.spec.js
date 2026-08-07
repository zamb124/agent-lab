/**
 * Browser: platform.ui.submit Button reflects context.submitting with spinner + disabled.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { renderButton } from '@platform/lib/flow-ui/catalog/basic/form.js';
import { FLOW_UI_ACTIONS } from '@platform/lib/flow-ui/protocol/constants.js';

function submitButtonComponent() {
    return {
        component_id: 'form-submit',
        type: 'Button',
        kind: 'leaf',
        properties: { label: 'Send request', variant: 'primary' },
        children: [],
        container_layout: null,
        placement: { base: {}, overrides: {} },
        bindings: {},
        actions: {
            press: { kind: 'event', name: FLOW_UI_ACTIONS.submit, context: {} },
        },
    };
}

function host(submitting) {
    return {
        locale: 'en',
        readonly: false,
        selectedComponentId: null,
        surface: { surface_id: 'main', data_model: { values: {} } },
        tasks: [],
        controller: { activeContext: { submitting } },
        _action() {},
    };
}

describe('flow-ui submit Button busy chrome', () => {
    afterEach(() => {
        fixtureCleanup();
    });

    it('disables submit Button with spinner while context is submitting', async () => {
        const el = await fixture(html`<div>${renderButton(host(true), submitButtonComponent())}</div>`);
        await elementUpdated(el);
        const button = el.querySelector('button');
        expect(button).to.exist;
        expect(button.disabled).to.equal(true);
        expect(button.getAttribute('aria-busy')).to.equal('true');
        expect(button.querySelector('.button-spinner')).to.exist;
        expect(button.textContent).to.contain('Send request');
    });

    it('keeps idle submit Button enabled without spinner', async () => {
        const el = await fixture(html`<div>${renderButton(host(false), submitButtonComponent())}</div>`);
        await elementUpdated(el);
        const button = el.querySelector('button');
        expect(button.disabled).to.equal(false);
        expect(button.getAttribute('aria-busy')).to.equal('false');
        expect(button.querySelector('.button-spinner')).to.equal(null);
    });

    it('does not treat non-submit Button as busy from submitting flag', async () => {
        const component = {
            ...submitButtonComponent(),
            component_id: 'badge',
            properties: { label: 'Badge', variant: 'secondary' },
            actions: {
                press: { kind: 'local', name: 'values.set', context: { value: 'x' } },
            },
        };
        const el = await fixture(html`<div>${renderButton(host(true), component)}</div>`);
        await elementUpdated(el);
        const button = el.querySelector('button');
        expect(button.disabled).to.equal(false);
        expect(button.querySelector('.button-spinner')).to.equal(null);
    });
});
