/**
 * trace-view-model — нормализация spans для platform-trace-viewer.
 */

import { describe, it, expect } from 'vitest';
import {
    normalizeTraceRoots,
    inferUiKind,
    spanMatchesQuery,
    computeTraceTimeRangeMs,
    pruneTraceViewNodes,
    collectMatchingSpanIds,
    treeDurationBarPct,
} from '@platform/lib/utils/trace-view-model.js';

describe('trace-view-model', () => {
    it('normalizeTraceRoots: operation_name и service_name в title/subtitle', () => {
        const roots = [
            {
                span_id: 'a1',
                trace_id: 't1',
                operation_name: 'llm_call',
                service_name: 'flows',
                start_time: '2025-01-01T10:00:00.000Z',
                end_time: '2025-01-01T10:00:01.000Z',
                duration_ms: 1000,
                status: 'OK',
                event_type: 'react.iteration',
                attributes: {},
                children: [],
            },
        ];
        const n = normalizeTraceRoots(roots);
        expect(n).to.have.length(1);
        expect(n[0]?.title).to.equal('llm_call');
        expect(n[0]?.subtitle).to.include('flows');
        expect(n[0]?.subtitle).to.include('react.iteration');
        expect(n[0]?.durationMs).to.equal(1000);
        expect(n[0]?.raw).to.deep.equal(roots[0]);
    });

    it('inferUiKind: gen_ai.operation.name chat -> generation', () => {
        const k = inferUiKind({
            span_id: 'x',
            attributes: { 'gen_ai.operation.name': 'chat' },
        });
        expect(k).to.equal('generation');
    });

    it('inferUiKind: execute_tool -> tool', () => {
        const k = inferUiKind({
            span_id: 'x',
            attributes: { 'gen_ai.operation.name': 'execute_tool' },
        });
        expect(k).to.equal('tool');
    });

    it('spanMatchesQuery находит по operation_name', () => {
        const raw = {
            span_id: 's1',
            operation_name: 'node_span',
            service_name: 'flows',
            attributes: {},
        };
        expect(spanMatchesQuery(raw, 'node')).to.be.true;
        expect(spanMatchesQuery(raw, 'zzz')).to.be.false;
    });

    it('computeTraceTimeRangeMs по дереву', () => {
        const roots = [
            {
                span_id: 'r',
                start_time: '2025-01-01T10:00:00.000Z',
                end_time: '2025-01-01T10:00:02.000Z',
                attributes: {},
                children: [
                    {
                        span_id: 'c',
                        start_time: '2025-01-01T10:00:00.500Z',
                        end_time: '2025-01-01T10:00:01.500Z',
                        attributes: {},
                        children: [],
                    },
                ],
            },
        ];
        const r = computeTraceTimeRangeMs(roots);
        if (r === null) throw new Error('expected non-null range');
        expect(r.min).to.be.lessThan(r.max);
    });

    it('pruneTraceViewNodes оставляет ветки с совпадениями', () => {
        const roots = [
            {
                span_id: 'root',
                operation_name: 'root',
                service_name: 's',
                start_time: '2025-01-01T10:00:00.000Z',
                end_time: '2025-01-01T10:00:03.000Z',
                duration_ms: 3000,
                status: 'OK',
                attributes: {},
                children: [
                    {
                        span_id: 'keep',
                        operation_name: 'llm_call',
                        service_name: 's',
                        start_time: '2025-01-01T10:00:01.000Z',
                        end_time: '2025-01-01T10:00:02.000Z',
                        duration_ms: 1000,
                        status: 'OK',
                        attributes: {},
                        children: [],
                    },
                    {
                        span_id: 'drop',
                        operation_name: 'other',
                        service_name: 's',
                        start_time: '2025-01-01T10:00:01.000Z',
                        end_time: '2025-01-01T10:00:02.000Z',
                        duration_ms: 1000,
                        status: 'OK',
                        attributes: {},
                        children: [],
                    },
                ],
            },
        ];
        const norm = normalizeTraceRoots(roots);
        const matched = collectMatchingSpanIds(roots, (rr) => spanMatchesQuery(rr, 'llm'));
        const pruned = pruneTraceViewNodes(norm, matched);
        expect(pruned).to.have.length(1);
        expect(pruned[0]?.children).to.have.length(1);
        expect(pruned[0]?.children[0]?.id).to.equal('keep');
    });

    it('normalizeSpanNode: RUNNING-спан без end_time — isRunning, live duration', () => {
        const roots = [
            {
                span_id: 'r1',
                trace_id: 't1',
                operation_name: 'files.read.parse',
                service_name: 'capability_gateway',
                start_time: '2025-01-01T10:00:00.000Z',
                end_time: null,
                duration_ms: null,
                status: 'RUNNING',
                attributes: {},
                children: [],
            },
            {
                span_id: 'r2',
                trace_id: 't1',
                operation_name: 'flows.flow.run',
                service_name: 'flows',
                start_time: '2025-01-01T10:00:00.000Z',
                end_time: '2025-01-01T10:00:01.000Z',
                duration_ms: 1000,
                status: 'OK',
                attributes: {},
                children: [],
            },
        ];
        const n = normalizeTraceRoots(roots);
        expect(n[0]?.isRunning).to.be.true;
        expect(n[0]?.endMs).to.equal(null);
        expect(n[0]?.durationMs).to.equal(null);
        expect(n[1]?.isRunning).to.be.false;
    });

    it('computeTraceTimeRangeMs: RUNNING-спан тянет диапазон до now', () => {
        const roots = [
            {
                span_id: 'r',
                start_time: '2025-01-01T10:00:00.000Z',
                end_time: null,
                duration_ms: null,
                status: 'RUNNING',
                attributes: {},
                children: [],
            },
        ];
        const r = computeTraceTimeRangeMs(roots);
        if (r === null) throw new Error('expected non-null range');
        expect(r.max).to.be.greaterThan(Date.parse('2025-01-01T10:00:00.000Z'));
    });

    it('treeDurationBarPct относительно родителя', () => {
        const roots = [
            {
                span_id: 'p',
                operation_name: 'p',
                service_name: 's',
                start_time: '2025-01-01T10:00:00.000Z',
                end_time: '2025-01-01T10:00:04.000Z',
                duration_ms: 4000,
                status: 'OK',
                attributes: {},
                children: [
                    {
                        span_id: 'c',
                        operation_name: 'c',
                        service_name: 's',
                        start_time: '2025-01-01T10:00:01.000Z',
                        end_time: '2025-01-01T10:00:02.000Z',
                        duration_ms: 1000,
                        status: 'OK',
                        attributes: {},
                        children: [],
                    },
                ],
            },
        ];
        const norm = normalizeTraceRoots(roots);
        const parent = norm[0];
        const child = parent?.children[0];
        if (parent === undefined || child === undefined) throw new Error('expected parent+child');
        const pct = treeDurationBarPct(child, parent, 4000);
        expect(pct).to.be.closeTo(25, 0.1);
    });
});
