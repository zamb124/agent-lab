import { describe, it, expect } from 'vitest';
import {
    buildNodeRunChangeRows,
    buildNodeRunDiffPreviewLines,
    buildNodeRunHeadline,
    buildNodeRunPrimaryLine,
    countNodeRunDiffChanges,
    formatCanvasValue,
    formatDiffPathLabel,
    getNodeRunResultPillHeight,
    nodeRunResultExpandKey,
    pickLatestNodeRunResult,
    truncateForCanvas,
} from '../../../../apps/flows/ui/_helpers/flows-node-run-result.js';

const MCP_STATUS_DIFF = Object.freeze({
    kind: 'ok',
    node_type: 'mcp',
    result_preview: '{"index":{"ok":true,"latency_ms":14770}}',
    primary_field: 'mcp_result',
    diff: Object.freeze([
        {
            path: 'variables.search_providers_status',
            old_value: null,
            new_value: {
                index: { ok: true, latency_ms: 14770 },
            },
            change_type: 'added',
        },
        {
            path: 'variables.query',
            old_value: 'old',
            new_value: 'new',
            change_type: 'changed',
        },
        {
            path: 'mcp_result',
            old_value: null,
            new_value: { hits: 2, total: 2 },
            change_type: 'added',
        },
    ]),
});

describe('flows-node-run-result', () => {
    it('truncateForCanvas обрезает длинный текст', () => {
        expect(truncateForCanvas('hello world', 8)).toBe('hello w…');
    });

    it('formatDiffPathLabel убирает префикс variables.', () => {
        expect(formatDiffPathLabel('variables.search_providers_status')).toBe('search_providers_status');
        expect(formatDiffPathLabel('response')).toBe('response');
    });

    it('formatCanvasValue сжимает status-map без JSON', () => {
        const text = formatCanvasValue({
            index: { ok: true, latency_ms: 14770 },
        });
        expect(text).toBe('index: ok · 14770 ms');
        expect(text).not.toContain('{');
    });

    it('buildNodeRunHeadline для MCP не показывает сырой JSON', () => {
        const headline = buildNodeRunHeadline(MCP_STATUS_DIFF);
        expect(headline).not.toContain('{');
        expect(headline).toContain('index: ok');
    });

    it('buildNodeRunPrimaryLine берёт result_preview для llm_node', () => {
        const line = buildNodeRunPrimaryLine({
            kind: 'ok',
            node_type: 'llm_node',
            result_preview: 'Mock LLM ответ',
            diff: [],
        });
        expect(line).toBe('Mock LLM ответ');
    });

    it('buildNodeRunPrimaryLine для error берёт error', () => {
        const line = buildNodeRunPrimaryLine({
            kind: 'error',
            error: 'ValueError: boom',
            diff: [],
        });
        expect(line).toBe('ValueError: boom');
    });

    it('countNodeRunDiffChanges считает diff', () => {
        expect(countNodeRunDiffChanges({
            kind: 'ok',
            diff: [
                { path: 'response', old_value: null, new_value: 'x', change_type: 'added' },
            ],
        })).toBe(1);
    });

    it('buildNodeRunChangeRows возвращает badge и detail', () => {
        const rows = buildNodeRunChangeRows(MCP_STATUS_DIFF);
        expect(rows.length).toBeGreaterThan(0);
        expect(rows[0].badge).toBe('+');
        expect(rows[0].label).toBe('mcp_result');
        expect(rows.some((row) => row.changeType === 'changed' && row.label === 'query')).toBe(true);
    });

    it('buildNodeRunDiffPreviewLines возвращает до 8 строк', () => {
        const lines = buildNodeRunDiffPreviewLines({
            kind: 'ok',
            diff: [
                { path: 'a', old_value: 1, new_value: 2, change_type: 'changed' },
                { path: 'b', old_value: 1, new_value: 2, change_type: 'changed' },
                { path: 'c', old_value: 1, new_value: 2, change_type: 'changed' },
                { path: 'd', old_value: 1, new_value: 2, change_type: 'changed' },
                { path: 'e', old_value: 1, new_value: 2, change_type: 'changed' },
                { path: 'f', old_value: 1, new_value: 2, change_type: 'changed' },
                { path: 'g', old_value: 1, new_value: 2, change_type: 'changed' },
                { path: 'h', old_value: 1, new_value: 2, change_type: 'changed' },
                { path: 'i', old_value: 1, new_value: 2, change_type: 'changed' },
            ],
        });
        expect(lines).toHaveLength(8);
    });

    it('getNodeRunResultPillHeight растёт при expanded diff rows', () => {
        const collapsed = getNodeRunResultPillHeight(MCP_STATUS_DIFF, false);
        const expanded = getNodeRunResultPillHeight(MCP_STATUS_DIFF, true);
        expect(expanded).toBeGreaterThan(collapsed);
        expect(collapsed).toBeGreaterThanOrEqual(44);
    });

    it('getNodeRunResultPillHeight учитывает label+detail для каждой строки diff', () => {
        const diff = Object.freeze([
            { path: 'variables.a', old_value: null, new_value: 'x', change_type: 'added' },
            { path: 'variables.b', old_value: null, new_value: 'y', change_type: 'added' },
            { path: 'variables.c', old_value: null, new_value: 'z', change_type: 'added' },
            { path: 'variables.d', old_value: null, new_value: 'w', change_type: 'added' },
            { path: 'variables.e', old_value: null, new_value: 'v', change_type: 'added' },
        ]);
        const result = { kind: 'ok', node_type: 'mcp', result_preview: 'hello', diff };
        const expandedHeight = getNodeRunResultPillHeight(result, true);
        expect(expandedHeight).toBeGreaterThan(180);
    });

    it('pickLatestNodeRunResult возвращает последний элемент', () => {
        const first = { kind: 'ok', run_index: 0, diff: [] };
        const second = { kind: 'ok', run_index: 1, diff: [] };
        expect(pickLatestNodeRunResult([first, second])).toBe(second);
    });

    it('nodeRunResultExpandKey формирует ключ', () => {
        expect(nodeRunResultExpandKey('node_a', 2)).toBe('node_a:2');
    });
});
