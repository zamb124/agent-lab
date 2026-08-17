import { describe, it, expect } from 'vitest';
import {
    buildNodeRunChangeRows,
    buildNodeRunDiffPreviewLines,
    buildNodeRunHeadline,
    buildNodeRunPrimaryLine,
    buildNodeRunViewModel,
    classifyNodeRunValue,
    countNodeRunDiffChanges,
    findDiffEntryByPath,
    findNodeRunResult,
    formatCanvasValue,
    formatDiffPathLabel,
    getNodeRunResultPillHeight,
    isLatestNodeRun,
    jsonTreeChildPath,
    nodeRunDiffHasPath,
    nodeRunResultExpandKey,
    nodeRunValueKindLabel,
    pickLatestNodeRunResult,
    resolveInspectValue,
    serializeNodeRunValue,
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

    it('classifyNodeRunValue отличает json, markdown, status_map и контейнеры', () => {
        expect(classifyNodeRunValue(null).kind).toBe('null');
        expect(classifyNodeRunValue('').kind).toBe('empty');
        expect(classifyNodeRunValue(true).kind).toBe('boolean');
        expect(classifyNodeRunValue(12).kind).toBe('number');
        expect(classifyNodeRunValue('plain text').kind).toBe('string');
        expect(classifyNodeRunValue('{"hits":[1,2]}').kind).toBe('json_string');
        expect(classifyNodeRunValue('# Title\n\nSee [docs](https://example.com)').kind).toBe('markdown');
        expect(classifyNodeRunValue({ index: { ok: true, latency_ms: 10 } }).kind).toBe('status_map');
        expect(classifyNodeRunValue([1, 2, 3]).kind).toBe('array');
        expect(classifyNodeRunValue({ title: 'x' }).kind).toBe('object');
        expect(classifyNodeRunValue('[{"title":"a"}]').kind).toBe('json_string');
    });

    it('nodeRunValueKindLabel для array и object включает count', () => {
        expect(nodeRunValueKindLabel(classifyNodeRunValue([1, 2]))).toContain('2');
        expect(nodeRunValueKindLabel(classifyNodeRunValue({ a: 1, b: 2, c: 3 }))).toContain('3');
    });

    it('canvas change rows не показывают сырой JSON', () => {
        const rows = buildNodeRunChangeRows({
            kind: 'ok',
            primary_field: 'result',
            diff: [
                {
                    path: 'result',
                    old_value: null,
                    new_value: [{ title: 'hit' }, { title: 'two' }],
                    change_type: 'added',
                },
            ],
        });
        expect(rows).toHaveLength(1);
        expect(rows[0].typeLabel.toLowerCase()).toContain('array');
        expect(rows[0].detail).not.toContain('{');
        expect(rows[0].detail).not.toContain('[');
    });

    it('buildNodeRunChangeRows без limit возвращает все строки', () => {
        const diff = Array.from({ length: 12 }, (_, index) => ({
            path: `field_${index}`,
            old_value: 1,
            new_value: 2,
            change_type: 'changed',
        }));
        const rows = buildNodeRunChangeRows({ kind: 'ok', diff });
        expect(rows).toHaveLength(12);
        const limited = buildNodeRunChangeRows({ kind: 'ok', diff }, undefined, { limit: 8 });
        expect(limited).toHaveLength(8);
        const viewModel = buildNodeRunViewModel({ kind: 'ok', diff });
        expect(viewModel.changeRows).toHaveLength(8);
        expect(viewModel.omittedCount).toBe(4);
    });

    it('classifyNodeRunValue: JSON выигрывает у markdown, не-JSON остаётся string', () => {
        expect(classifyNodeRunValue('{"title":"# heading"}').kind).toBe('json_string');
        expect(classifyNodeRunValue('[{"title":"# heading"}]').kind).toBe('json_string');
        expect(classifyNodeRunValue('{not-json').kind).toBe('string');
        expect(classifyNodeRunValue('42').kind).toBe('string');
        expect(classifyNodeRunValue('see [docs](https://example.com/a)').kind).toBe('markdown');
        expect(classifyNodeRunValue('1. [docs](https://example.com/a)').kind).toBe('markdown');
        expect(classifyNodeRunValue(false).kind).toBe('boolean');
        expect(classifyNodeRunValue({})).toEqual({ kind: 'object', preview: '', parsed: {} });
        expect(classifyNodeRunValue([])).toEqual({ kind: 'array', preview: '', parsed: [] });
    });

    it('classifyNodeRunValue падает на undefined и неподдерживаемом типе', () => {
        expect(() => classifyNodeRunValue(undefined)).toThrow(/undefined/);
        expect(() => classifyNodeRunValue(() => 1)).toThrow(/unsupported type/);
    });

    it('getNodeRunResultPillHeight не растёт от длины JSON', () => {
        const short = {
            kind: 'ok',
            result_preview: 'ok',
            diff: [{ path: 'result', old_value: null, new_value: { a: 1 }, change_type: 'added' }],
        };
        const long = {
            kind: 'ok',
            result_preview: 'ok',
            diff: [{
                path: 'result',
                old_value: null,
                new_value: { hits: Array.from({ length: 80 }, (_, index) => ({ title: `hit-${index}-${'x'.repeat(200)}` })) },
                change_type: 'added',
            }],
        };
        expect(getNodeRunResultPillHeight(short, true)).toBe(getNodeRunResultPillHeight(long, true));
    });

    it('serializeNodeRunValue и resolveInspectValue отдают полное значение', () => {
        const payload = { title: 'hit', items: [1, 2, 3] };
        const serialized = serializeNodeRunValue(payload);
        expect(serialized).toContain('"title": "hit"');
        expect(serialized).toContain('"items"');
        expect(resolveInspectValue({ old_value: 'was', new_value: payload }, 'new')).toEqual(payload);
        expect(resolveInspectValue({ old_value: 'was', new_value: payload }, 'old')).toBe('was');
        expect(() => resolveInspectValue({ old_value: 1, new_value: 2 }, 'side')).toThrow(/side/);
    });

    it('findNodeRunResult и isLatestNodeRun работают по run_index', () => {
        const first = { kind: 'ok', run_index: 0, diff: [] };
        const second = { kind: 'ok', run_index: 2, diff: [] };
        const results = [first, second];
        expect(findNodeRunResult(results, 2)).toBe(second);
        expect(isLatestNodeRun(results, 2)).toBe(true);
        expect(isLatestNodeRun(results, 0)).toBe(false);
        expect(() => findNodeRunResult(results, 1)).toThrow(/run_index 1/);
        expect(() => findNodeRunResult([], 0)).toThrow(/non-empty/);
    });

    it('findDiffEntryByPath и nodeRunDiffHasPath fail-closed', () => {
        const result = {
            kind: 'ok',
            diff: [{ path: 'result', old_value: null, new_value: 'x', change_type: 'added' }],
        };
        expect(findDiffEntryByPath(result, 'result').new_value).toBe('x');
        expect(nodeRunDiffHasPath(result, 'result')).toBe(true);
        expect(nodeRunDiffHasPath(result, 'missing')).toBe(false);
        expect(() => findDiffEntryByPath(result, 'missing')).toThrow(/missing/);
        expect(() => nodeRunDiffHasPath(result, '')).toThrow(/non-empty/);
    });

    it('jsonTreeChildPath строит path для объекта и массива', () => {
        expect(jsonTreeChildPath('result', 'nested', false)).toBe('result.nested');
        expect(jsonTreeChildPath('', 'root', false)).toBe('root');
        expect(jsonTreeChildPath('hits', 2, true)).toBe('hits[2]');
        expect(() => jsonTreeChildPath('hits', -1, true)).toThrow(/non-negative/);
        expect(() => jsonTreeChildPath('result', '', false)).toThrow(/non-empty/);
    });
});
