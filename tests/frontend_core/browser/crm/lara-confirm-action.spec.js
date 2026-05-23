/**
 * Lara embed: flows-chat-block-action без actionHandlers -> POST flows Lara pending apply (default path).
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, aTimeout } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../core/frontend/static/lib/embed-chat/platform-embed-chat.js';

describe('crm lara confirm action (embed-chat default apply)', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    afterEach(() => {
        document.querySelectorAll('platform-embed-chat').forEach((el) => el.remove());
        fixtureCleanup();
    });

    it('POST /api/v1/lara/pending-actions/apply с pending_action_id и contextId', async () => {
        /** @type {{ url: string, opts: RequestInit }[]} */
        const calls = [];
        const prevFetch = globalThis.fetch;
        globalThis.fetch = async (url, opts) => {
            calls.push({ url: String(url), opts: opts && typeof opts === 'object' ? opts : {} });
            return new Response(
                JSON.stringify({
                    status: 'applied',
                    result: {
                        message: 'Заметка создана.',
                        entity: { entity_id: 'e1', name: 'N' },
                    },
                }),
                { status: 200, headers: { 'Content-Type': 'application/json' } },
            );
        };

        try {
            const el = await fixture(html`
                <platform-embed-chat flows-base-url="/flows"></platform-embed-chat>
            `);
            await el.updateComplete;
            const ctxId =
                typeof el.getA2aContextId === 'function'
                    ? el.getA2aContextId()
                    : '';

            el.dispatchEvent(
                new CustomEvent('flows-chat-block-action', {
                    bubbles: false,
                    composed: true,
                    detail: {
                        action_id: 'crm.note.create.apply',
                        action_kind: 'apply',
                        pending_action_id: 'pending-lara-99',
                        arguments: {},
                        context: {},
                    },
                }),
            );

            await aTimeout(80);
            const applyCalls = calls.filter((c) => c.url.includes('lara/pending-actions/apply'));
            expect(applyCalls.length).to.equal(1);
            expect(applyCalls[0].url).to.include('/flows/api/v1/lara/pending-actions/apply');
            /** @type {Record<string, unknown>} */
            const body = JSON.parse(String(applyCalls[0].opts.body || '{}'));
            expect(body.pending_action_id).to.equal('pending-lara-99');
            expect(body.context_id).to.equal(ctxId);
            expect(Object.prototype.hasOwnProperty.call(body, 'idempotency_key')).to.equal(false);

            await elementUpdated(el);
        } finally {
            globalThis.fetch = prevFetch;
        }
    });
});
