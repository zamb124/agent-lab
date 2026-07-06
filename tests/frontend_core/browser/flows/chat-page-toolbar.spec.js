/**
 * chat-page: toolbar + platform-chat mount + observability bubble → modals.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { flowsResource } from '../../../../apps/flows/ui/events/resources/flows.resource.js';
import { sessionStateOp } from '../../../../apps/flows/ui/events/resources/sessions.resource.js';
import {
    tracesBySessionOp,
    tracesByTaskOp,
    tracesByTraceOp,
} from '../../../../apps/flows/ui/events/resources/traces.resource.js';
import {
    logsBySessionOp,
    logsByTraceOp,
    logsByRequestOp,
    logsBySpanOp,
    logsByUserOp,
} from '../../../../apps/flows/ui/events/resources/logs.resource.js';
import { installChatProfileFetchStub } from '../helpers/chat-profile-stub.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-modal-stack.js';
import '../../../../apps/flows/ui/pages/chat-page.js';
import '../../../../apps/flows/ui/modals/flows-tracing-modal.js';
import '../../../../apps/flows/ui/modals/flows-logs-modal.js';

const FACTORIES = [
    flowsResource,
    sessionStateOp,
    tracesBySessionOp,
    tracesByTaskOp,
    tracesByTraceOp,
    logsBySessionOp,
    logsByTraceOp,
    logsByRequestOp,
    logsBySpanOp,
    logsByUserOp,
];

function cleanupPortaledModals() {
    for (const el of document.querySelectorAll('flows-tracing-modal, flows-logs-modal')) {
        el.remove();
    }
}

describe('chat-page toolbar', () => {
    let restoreProfileFetch;

    beforeEach(() => {
        cleanupPortaledModals();
        resetPlatformState();
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        bootstrapTestBus({ slices: collected.slices, effects: [] });
        restoreProfileFetch = installChatProfileFetchStub({ flowId: 'demo_flow' });
    });

    afterEach(() => {
        restoreProfileFetch();
        cleanupPortaledModals();
        fixtureCleanup();
    });

    it('desktop header actions render platform-button', async () => {
        const el = await fixture(html`
            <chat-page flow-id="demo_flow" branch-id="base"></chat-page>
        `);
        await elementUpdated(el);

        const actions = el.shadowRoot.querySelector('.flow-chat-header-actions');
        expect(actions).to.not.equal(null);
        const buttons = actions.querySelectorAll('platform-button');
        expect(buttons.length).to.be.greaterThan(0);

        const settingsBtn = actions.querySelector('[data-action="flow-settings"]');
        expect(settingsBtn).to.not.equal(null);
        expect(settingsBtn.localName).to.equal('platform-button');
    });

    it('mounts platform-chat display=page profile=spa without chat-profile 404', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        const el = await fixture(html`
            <chat-page flow-id="demo_flow" branch-id="base"></chat-page>
        `);
        await elementUpdated(el);

        const chat = el.shadowRoot.querySelector('platform-chat');
        expect(chat).to.not.equal(null);
        expect(chat.getAttribute('display')).to.equal('page');
        expect(chat.getAttribute('profile')).to.equal('spa');

        await chat.updateComplete;
        await waitUntil(
            () => chat.shadowRoot?.querySelector('flows-chat-input'),
            'composer after chat-profile stub',
            { timeout: 2000 },
        );
        expect(stack).to.not.equal(null);
    });

    it('bubble show-tracing and show-logs open flows modals via chat-page handlers', async () => {
        await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        const el = await fixture(html`
            <chat-page flow-id="demo_flow" branch-id="base"></chat-page>
        `);
        await elementUpdated(el);

        const chat = el.shadowRoot.querySelector('platform-chat');
        await chat.updateComplete;

        chat.dispatchEvent(new CustomEvent('show-tracing', {
            bubbles: true,
            composed: true,
            detail: { taskId: 'task-toolbar-1', traceId: 'trace-toolbar-1' },
        }));
        await elementUpdated(el);
        await waitUntil(
            () => document.querySelector('flows-tracing-modal'),
            'tracing modal after show-tracing',
            { timeout: 2000 },
        );

        getPlatformBus().dispatch(CoreEvents.UI_MODAL_CLOSE, { kind: 'flows.tracing' });
        await elementUpdated(el);

        chat.dispatchEvent(new CustomEvent('show-logs', {
            bubbles: true,
            composed: true,
            detail: { sessionId: 'demo_flow:ctx-toolbar', taskId: 'task-toolbar-1' },
        }));
        await elementUpdated(el);
        await waitUntil(
            () => document.querySelector('flows-logs-modal'),
            'logs modal after show-logs',
            { timeout: 2000 },
        );
    });
});
