/// <reference types="node" />
/**
 * ``openFlowUIBrowserPreview``: ``browser-preview-open`` несёт интерактивный ``viewer_url``
 * (не статический screenshot); без обработчика на хосте — fallback ``window.open``.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { openFlowUIBrowserPreview } from '@platform/lib/flow-ui/runtime/browser-preview.js';

const VIEWER = '/flows/api/v1/browser-preview/sessions/sess%201/viewer?token=tok.en';
const SHOT = '/flows/api/v1/browser-preview/sessions/sess%201/screenshot?token=tok.en';

function host(events: CustomEvent[] = []) {
    return {
        flowId: 'flow-1',
        contextId: 'ctx-1',
        events,
        dispatchEvent(event: Event) {
            events.push(event as CustomEvent);
            return true;
        },
    };
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('openFlowUIBrowserPreview', () => {
    it('dispatches browser-preview-open with the interactive viewer URL and session id', () => {
        const open = vi.fn();
        vi.stubGlobal('window', { open });
        const events: CustomEvent[] = [];
        openFlowUIBrowserPreview(host(events), { url: VIEWER, title: 'https://example.com', status: 'running' });
        expect(events).toHaveLength(1);
        const event = events[0]!;
        expect(event.type).to.equal('browser-preview-open');
        expect(event.detail).toEqual({
            viewerUrl: VIEWER,
            sessionId: 'sess 1',
            currentUrl: 'https://example.com',
            status: 'running',
        });
        expect(open).toHaveBeenCalledWith(VIEWER, '_blank', 'noopener,noreferrer');
    });

    it('skips the window.open fallback when a host handler prevents default', () => {
        const open = vi.fn();
        vi.stubGlobal('window', { open });
        const target = {
            flowId: 'flow-1',
            contextId: 'ctx-1',
            dispatchEvent(event: Event) {
                event.preventDefault();
                return false;
            },
        };
        openFlowUIBrowserPreview(target, { url: VIEWER });
        expect(open).not.toHaveBeenCalled();
    });

    it('ignores empty viewer URL and falls back to flow session for non-viewer URLs', () => {
        const open = vi.fn();
        vi.stubGlobal('window', { open });
        const events: CustomEvent[] = [];
        const target = host(events);
        openFlowUIBrowserPreview(target, { url: '  ' });
        expect(events).toHaveLength(0);
        openFlowUIBrowserPreview(target, { url: SHOT });
        expect(events[0]!.detail.sessionId).to.equal('flow-1:ctx-1');
        openFlowUIBrowserPreview(target, { url: 'https://elsewhere.test/view' });
        expect(events[1]!.detail.currentUrl).to.equal('https://elsewhere.test/view');
    });
});
