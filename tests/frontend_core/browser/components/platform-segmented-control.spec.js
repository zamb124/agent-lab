/**
 * platform-segmented-control — pill segmented selector smoke tests.
 */

import { fixture, html, expect, oneEvent } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-segmented-control.js';

describe('platform-segmented-control', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('renders items and marks active segment', async () => {
        const el = await fixture(html`
            <platform-segmented-control
                value="run"
                .items=${[
                    { value: 'edit', icon: 'edit', title: 'Edit' },
                    { value: 'run', icon: 'play', title: 'Run' },
                ]}
                icon-only
                density="dense"
            ></platform-segmented-control>
        `);
        const active = el.shadowRoot.querySelector('.segment[data-active="true"]');
        expect(active).to.exist;
        expect(active.getAttribute('aria-pressed')).to.equal('true');
    });

    it('emits change with selected value', async () => {
        const el = await fixture(html`
            <platform-segmented-control
                value="edit"
                .items=${[
                    { value: 'edit', label: 'Edit' },
                    { value: 'run', label: 'Run' },
                ]}
            ></platform-segmented-control>
        `);
        const segments = el.shadowRoot.querySelectorAll('.segment');
        setTimeout(() => segments[1].click());
        const ev = await oneEvent(el, 'change');
        expect(ev.detail.value).to.equal('run');
    });

    it('emits segment-close for closable items', async () => {
        const el = await fixture(html`
            <platform-segmented-control
                value="b1"
                .items=${[
                    { value: 'base', label: 'Base' },
                    { value: 'b1', label: 'Branch 1', closable: true },
                ]}
            ></platform-segmented-control>
        `);
        const closeBtn = el.shadowRoot.querySelector('.segment-close');
        expect(closeBtn).to.exist;
        setTimeout(() => closeBtn.click());
        const ev = await oneEvent(el, 'segment-close');
        expect(ev.detail.value).to.equal('b1');
    });
});
