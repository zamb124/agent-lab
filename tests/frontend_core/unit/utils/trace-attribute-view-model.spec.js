/**
 * trace-attribute-view-model — нормализация span.attributes для читаемого UI.
 */

import { describe, it, expect } from 'vitest';
import {
    buildSpanAttributeViewModel,
    parseTraceJsonValue,
    prettyTraceJsonText,
} from '@platform/lib/utils/trace-attribute-view-model.js';

describe('trace-attribute-view-model', () => {
    it('парсит LLM request с A2A parts в список сообщений', () => {
        const span = {
            span_id: 's1',
            trace_id: 't1',
            operation_name: 'llm.qwen',
            duration_ms: 123,
            attributes: {
                'platform.flow_id': 'crm',
                'platform.branch_id': 'summarize_chunk',
                'platform.llm.model': 'qwen/qwen3.5',
                'platform.llm.request': JSON.stringify({
                    messages: [
                        {
                            role: 'agent',
                            messageId: 'm1',
                            metadata: { system: true },
                            parts: [{ kind: 'text', text: 'Системный промпт' }],
                        },
                        {
                            role: 'user',
                            messageId: 'm2',
                            parts: [{ kind: 'text', text: 'Daily summary: chunk' }],
                        },
                    ],
                    tools: [],
                }),
            },
        };

        const vm = buildSpanAttributeViewModel(span);

        expect(vm.quickFacts.some((item) => item.key === 'flow' && item.value === 'crm')).to.equal(true);
        expect(vm.llmRequest.messages).to.have.length(2);
        expect(vm.llmRequest.messages[0].system).to.equal(true);
        expect(vm.llmRequest.messages[0].text).to.equal('Системный промпт');
        expect(vm.llmRequest.messages[1].text).to.equal('Daily summary: chunk');
    });

    it('раскрывает JSON внутри LLM response.content как structured output', () => {
        const span = {
            span_id: 's1',
            attributes: {
                'platform.llm.response': JSON.stringify({
                    content: JSON.stringify({
                        summary: 'Краткая сводка',
                        entities: ['Виктор'],
                        highlights: ['Важный факт'],
                        key_events: ['Создана заметка'],
                        statistics: { notes_added: 1 },
                    }),
                    tool_calls: [],
                }),
            },
        };

        const vm = buildSpanAttributeViewModel(span);

        expect(vm.llmResponse.structuredContent.summary).to.equal('Краткая сводка');
        expect(vm.llmResponse.structuredContent.entities).to.deep.equal(['Виктор']);
        expect(vm.llmResponse.structuredContent.statistics.notes_added).to.equal(1);
    });

    it('возвращает ошибку парсинга для битой JSON-строки', () => {
        const parsed = parseTraceJsonValue('{"messages": [');

        expect(parsed.ok).to.equal(false);
        expect(parsed.error).to.be.a('string');
    });

    it('восстанавливает content из обрезанной LLM response оболочки', () => {
        const raw = [
            '{"content": "{\\n  \\"summary\\": \\"Краткая сводка\\",\\n',
            '  \\"entities\\": [\\"CRM\\"],\\n',
            '  \\"statistics\\": { \\"notes_added\\": 1 }\\n',
            '}", "tool_calls": []',
        ].join('');
        const span = {
            span_id: 's1',
            attributes: {
                'platform.llm.response': raw,
            },
        };

        const vm = buildSpanAttributeViewModel(span);

        expect(vm.llmResponse.parsed.ok).to.equal(false);
        expect(vm.llmResponse.recovered).to.equal(true);
        expect(vm.llmResponse.structuredContent.summary).to.equal('Краткая сводка');
        expect(vm.llmResponse.structuredContent.entities).to.deep.equal(['CRM']);
    });

    it('prettyTraceJsonText форматирует escaped JSON даже когда внешняя оболочка битая', () => {
        const raw = '{"content": "{\\n  \\"summary\\": \\"Краткая сводка\\"\\n}", "tool_calls": []';

        const pretty = prettyTraceJsonText(raw);

        expect(pretty).to.include('"content": {');
        expect(pretty).to.include('"summary": "Краткая сводка"');
        expect(pretty).to.not.include('\\n');
    });
});
