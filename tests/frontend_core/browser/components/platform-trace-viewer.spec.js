/**
 * platform-trace-viewer — рендер и событие выбора span.
 */

import { fixture, html, expect, oneEvent } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-trace-viewer.js';

describe('platform-trace-viewer', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('эмитит trace-span-select при клике по заголовку', async () => {
        const roots = [
            {
                span_id: 's1',
                trace_id: 't1',
                operation_name: 'op',
                service_name: 'flows',
                start_time: '2025-01-01T10:00:00.000Z',
                end_time: '2025-01-01T10:00:01.000Z',
                duration_ms: 1000,
                status: 'OK',
                attributes: {},
                children: [],
            },
        ];
        const el = await fixture(html`
            <platform-trace-viewer .roots=${roots}></platform-trace-viewer>
        `);
        const title = el.shadowRoot.querySelector('.title');
        expect(title).to.exist;
        const p = oneEvent(el, 'trace-span-select');
        title.click();
        const ev = await p;
        expect(ev.detail.span).to.equal(roots[0]);
    });
});
