/**
 * platform-work-item-badge: обязательный work-item-id, variant/size validation.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import '@platform/lib/components/platform-work-item-badge.js';
import {
    platformWorkItemGetOp,
    platformWorkItemFactories,
} from '@platform/lib/events/resources/platform-work-item.resource.js';

describe('platform-work-item-badge', () => {
    beforeEach(() => {
        resetPlatformState();
        for (const factory of platformWorkItemFactories) {
            registerFactory(factory);
        }
        bootstrapTestBus({
            slices: {
                [platformWorkItemGetOp.sliceKey]: platformWorkItemGetOp.slice,
            },
        });
    });

    it('без work-item-id и .item — throw при render', async () => {
        const el = document.createElement('platform-work-item-badge');
        document.body.appendChild(el);
        let caught = null;
        try {
            await el.updateComplete;
        } catch (error) {
            caught = error;
        }
        expect(caught).to.exist;
        el.remove();
    });

    it('рендерит title из .item', async () => {
        const el = await fixture(html`
            <platform-work-item-badge
                work-item-id="wi_test"
                .item=${{ work_item_id: 'wi_test', title: 'Fix inbox', priority: 'high', state: 'open', kind: 'generic' }}
                variant="chip"
            ></platform-work-item-badge>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.textContent).to.contain('Fix inbox');
    });

    it('row/card: data-state на badge, left bar не от priority', async () => {
        const el = await fixture(html`
            <platform-work-item-badge
                work-item-id="wi_state"
                .item=${{ work_item_id: 'wi_state', title: 'In progress task', priority: 'normal', state: 'in_progress', kind: 'generic' }}
                variant="row"
            ></platform-work-item-badge>
        `);
        await elementUpdated(el);
        const badge = el.shadowRoot.querySelector('.badge');
        expect(badge).to.exist;
        expect(badge.getAttribute('data-state')).to.equal('in_progress');
        expect(badge.hasAttribute('data-priority')).to.equal(false);
        const stateDot = el.shadowRoot.querySelector('.state-dot');
        expect(stateDot).to.exist;
        expect(stateDot.getAttribute('data-state')).to.equal('in_progress');
    });

    it('meta: priority mark только для high/urgent', async () => {
        const normalEl = await fixture(html`
            <platform-work-item-badge
                work-item-id="wi_normal"
                .item=${{ work_item_id: 'wi_normal', title: 'Normal', priority: 'normal', state: 'open', kind: 'generic' }}
                variant="row"
            ></platform-work-item-badge>
        `);
        await elementUpdated(normalEl);
        expect(normalEl.shadowRoot.querySelector('.priority-mark')).to.equal(null);

        const urgentEl = await fixture(html`
            <platform-work-item-badge
                work-item-id="wi_urgent"
                .item=${{ work_item_id: 'wi_urgent', title: 'Urgent', priority: 'urgent', state: 'open', kind: 'generic' }}
                variant="row"
            ></platform-work-item-badge>
        `);
        await elementUpdated(urgentEl);
        const mark = urgentEl.shadowRoot.querySelector('.priority-mark');
        expect(mark).to.exist;
        expect(mark.getAttribute('data-priority')).to.equal('urgent');
    });

    it('invalid variant — throw при updated', async () => {
        const el = await fixture(html`
            <platform-work-item-badge
                work-item-id="wi_test"
                .item=${{ work_item_id: 'wi_test', title: 'A', priority: 'normal', state: 'open', kind: 'generic' }}
                variant="chip"
            ></platform-work-item-badge>
        `);
        await elementUpdated(el);
        let caught = null;
        try {
            el.variant = 'table';
            await el.updateComplete;
        } catch (error) {
            caught = error;
        }
        expect(caught).to.exist;
    });
});
