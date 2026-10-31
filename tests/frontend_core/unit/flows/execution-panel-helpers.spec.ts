import { describe, it, expect } from 'vitest';
import {
    deriveRunPanelStatus,
    humanReadableErrorSummary,
} from '../../../../apps/flows/ui/_helpers/flows-resolvers.js';

describe('deriveRunPanelStatus', () => {
    it('returns running when runInFlight', () => {
        expect(
            deriveRunPanelStatus({
                runInFlight: true,
                taskId: null,
                activeAssistant: null,
                runTrace: [],
            }),
        ).toBe('running');
    });

    it('returns failed when assistant.error is non-empty', () => {
        expect(
            deriveRunPanelStatus({
                runInFlight: false,
                taskId: 't1',
                activeAssistant: { error: 'boom', streaming: false },
                runTrace: [],
            }),
        ).toBe('failed');
    });

    it('returns passed when trace has completed terminal', () => {
        expect(
            deriveRunPanelStatus({
                runInFlight: false,
                taskId: 't1',
                activeAssistant: { streaming: false, content: '' },
                runTrace: [
                    {
                        id: 'a',
                        ts: 1,
                        kind: 'status_terminal',
                        task_id: 't1',
                        terminal_state: 'completed',
                        message_preview: '',
                    },
                ],
            }),
        ).toBe('passed');
    });

    it('returns failed when trace has failed terminal', () => {
        expect(
            deriveRunPanelStatus({
                runInFlight: false,
                taskId: 't1',
                activeAssistant: { streaming: false, content: '' },
                runTrace: [
                    {
                        id: 'a',
                        ts: 1,
                        kind: 'status_terminal',
                        task_id: 't1',
                        terminal_state: 'failed',
                        message_preview: '',
                    },
                ],
            }),
        ).toBe('failed');
    });

    it('returns idle when waiting for input', () => {
        expect(
            deriveRunPanelStatus({
                runInFlight: false,
                taskId: 't1',
                activeAssistant: { streaming: false, content: '', inputRequired: {} },
                runTrace: [],
            }),
        ).toBe('idle');
    });

    it('returns passed when assistant has content and streaming false', () => {
        expect(
            deriveRunPanelStatus({
                runInFlight: false,
                taskId: 't1',
                activeAssistant: { streaming: false, content: 'ok' },
                runTrace: [],
            }),
        ).toBe('passed');
    });
});

describe('humanReadableErrorSummary', () => {
    it('parses Client error 403', () => {
        const s = "Client error '403 Forbidden' for url 'https://example.com'";
        expect(humanReadableErrorSummary(s)).toBe('HTTP 403: Forbidden');
    });

    it('uses first line for generic errors', () => {
        expect(humanReadableErrorSummary('Something broke\nmore')).toBe('Something broke');
    });
});
