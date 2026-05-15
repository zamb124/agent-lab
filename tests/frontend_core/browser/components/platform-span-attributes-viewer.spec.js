/**
 * platform-span-attributes-viewer — человекочитаемый рендер span attributes.
 */

import { fixture, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-span-attributes-viewer.js';

describe('platform-span-attributes-viewer', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('рендерит LLM request/response и оставляет raw attributes', async () => {
        const span = {
            span_id: 's1',
            trace_id: 't1',
            operation_name: 'llm.qwen',
            duration_ms: 25,
            attributes: {
                'platform.flow_id': 'crm',
                'platform.llm.model': 'qwen/qwen3.5',
                'platform.llm.request': JSON.stringify({
                    messages: [{ role: 'user', parts: [{ kind: 'text', text: 'Daily summary: chunk' }] }],
                    tools: [],
                }),
                'platform.llm.response': JSON.stringify({
                    content: JSON.stringify({ summary: 'Краткая сводка', entities: ['CRM'] }),
                    tool_calls: [],
                }),
            },
        };

        const el = await fixture(html`
            <platform-span-attributes-viewer .span=${span}></platform-span-attributes-viewer>
        `);

        const text = el.shadowRoot.textContent;
        expect(text).to.include('crm');
        expect(text).to.include('qwen/qwen3.5');
        expect(text).to.include('Daily summary: chunk');
        expect(text).to.include('Краткая сводка');
        expect(text).to.include('platform.llm.request');
    });

    it('показывает readable response для обрезанной JSON-оболочки', async () => {
        const rawResponse = [
            '{"content": "{\\n  \\"summary\\": \\"Краткая сводка\\",\\n',
            '  \\"entities\\": [\\"CRM\\"]\\n',
            '}", "tool_calls": []',
        ].join('');
        const span = {
            span_id: 's1',
            attributes: {
                'platform.llm.response': rawResponse,
            },
        };

        const el = await fixture(html`
            <platform-span-attributes-viewer .span=${span}></platform-span-attributes-viewer>
        `);

        const text = el.shadowRoot.textContent;
        expect(text).to.include('Краткая сводка');
        expect(text).to.include('"content": {');
        expect(text).to.not.include('Unterminated string');
    });
});
