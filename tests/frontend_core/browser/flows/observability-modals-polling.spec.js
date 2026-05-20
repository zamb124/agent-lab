/**
 * Модалки tracing/logs flows — polling, пока Tempo/Loki ещё индексируют.
 */

import { fixture, fixtureCleanup, html, expect, waitUntil, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, registerFactory, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import '@platform/lib/components/platform-modal-stack.js';
import {
    tracesBySessionOp,
    tracesByTaskOp,
    tracesByTraceOp,
} from '../../../../apps/flows/ui/events/resources/traces.resource.js';
import {
    logsBySessionOp,
    logsByTraceOp,
} from '../../../../apps/flows/ui/events/resources/logs.resource.js';
import {
    FlowsTracingModal,
} from '../../../../apps/flows/ui/modals/flows-tracing-modal.js';
import {
    FlowsLogsModal,
} from '../../../../apps/flows/ui/modals/flows-logs-modal.js';

const FACTORIES = [
    tracesBySessionOp,
    tracesByTaskOp,
    tracesByTraceOp,
    logsBySessionOp,
    logsByTraceOp,
];

const SVG_RESPONSE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"></svg>';

function jsonResponse(body) {
    return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
    });
}

function svgResponse() {
    return new Response(SVG_RESPONSE, {
        status: 200,
        headers: { 'content-type': 'image/svg+xml' },
    });
}

function bootstrap() {
    for (const factory of FACTORIES) {
        registerFactory(factory);
    }
    const collected = collectFactories(FACTORIES);
    bootstrapTestBus({ slices: collected.slices, effects: collected.effects });
}

function traceRoot() {
    return {
        span_id: 'span_1',
        trace_id: 'trace_1',
        operation_name: 'root',
        kind: 'SPAN_KIND_SERVER',
        start_time: '2026-05-15T10:00:00.000Z',
        end_time: '2026-05-15T10:00:00.010Z',
        duration_ms: 10,
        status: 'UNSET',
        service_name: 'flows',
        attributes: {},
        events: [],
        children: [],
    };
}

function cleanupPortaledModals() {
    for (const el of document.querySelectorAll('flows-tracing-modal, flows-logs-modal')) {
        el.remove();
    }
}

describe('flows observability modals polling', () => {
    let originalFetch;
    let originalTraceInterval;
    let originalTraceMax;
    let originalLogsInterval;
    let originalLogsMax;

    beforeEach(() => {
        originalFetch = window.fetch;
        originalTraceInterval = FlowsTracingModal.pollIntervalMs;
        originalTraceMax = FlowsTracingModal.pollMaxAttempts;
        originalLogsInterval = FlowsLogsModal.pollIntervalMs;
        originalLogsMax = FlowsLogsModal.pollMaxAttempts;
        resetPlatformState();
        bootstrap();
        FlowsTracingModal.pollIntervalMs = 10;
        FlowsTracingModal.pollMaxAttempts = 4;
        FlowsLogsModal.pollIntervalMs = 10;
        FlowsLogsModal.pollMaxAttempts = 4;
    });

    afterEach(() => {
        window.fetch = originalFetch;
        FlowsTracingModal.pollIntervalMs = originalTraceInterval;
        FlowsTracingModal.pollMaxAttempts = originalTraceMax;
        FlowsLogsModal.pollIntervalMs = originalLogsInterval;
        FlowsLogsModal.pollMaxAttempts = originalLogsMax;
        cleanupPortaledModals();
        fixtureCleanup();
    });

    it('tracing modal keeps loading and retries until spans appear', async () => {
        let sessionCalls = 0;
        window.fetch = async (url) => {
            const href = String(url);
            if (href.includes('/flows/api/v1/traces/session/session_1')) {
                sessionCalls += 1;
                return jsonResponse(sessionCalls < 2 ? { spans: [] } : { spans: [traceRoot()] });
            }
            return svgResponse();
        };

        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, {
            kind: 'flows.tracing',
            props: { sessionId: 'session_1' },
        });
        await elementUpdated(stack);
        const modal = document.querySelector('flows-tracing-modal');
        await waitUntil(() => modal?.shadowRoot?.querySelector('.tracing-loading'), 'tracing loading state');
        await waitUntil(
            () => modal.shadowRoot.querySelector('platform-trace-viewer'),
            'trace viewer after polling',
            { timeout: 1000 },
        );

        expect(sessionCalls).to.be.at.least(2);
        expect(modal.shadowRoot.querySelector('.tracing-empty')).to.equal(null);
    });

    it('logs modal keeps loading and retries until session log entries appear', async () => {
        let logsCalls = 0;
        window.fetch = async (url) => {
            const href = String(url);
            if (href.includes('/flows/api/v1/observability/logs/by-session/session_1')) {
                logsCalls += 1;
                return jsonResponse(logsCalls < 2
                    ? { entries: [], count: 0 }
                    : {
                          entries: [{
                              timestamp: '2026-05-15T10:00:00.000Z',
                              level: 'info',
                              service: 'flows',
                              message: 'indexed log line',
                              raw: { message: 'indexed log line' },
                          }],
                          count: 1,
                      });
            }
            if (href.includes('/flows/api/v1/traces/session/session_1')) {
                return jsonResponse({ spans: [] });
            }
            return svgResponse();
        };

        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, {
            kind: 'flows.logs',
            props: { sessionId: 'session_1' },
        });
        await elementUpdated(stack);
        const modal = document.querySelector('flows-logs-modal');
        await waitUntil(() => modal?.shadowRoot?.querySelector('.logs-loading'), 'logs loading state');
        await waitUntil(() => {
            const viewer = modal.shadowRoot.querySelector('platform-log-viewer');
            return viewer?.shadowRoot?.textContent.includes('indexed log line');
        }, 'log viewer after polling', { timeout: 1000 });

        expect(logsCalls).to.be.at.least(2);
    });
});
