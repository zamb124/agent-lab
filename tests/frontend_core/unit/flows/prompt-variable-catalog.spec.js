import { describe, expect, it } from 'vitest';
import {
    buildPromptVariableContext,
    buildRuntimeDatetimePreview,
} from '../../../../apps/flows/ui/_helpers/prompt-variable-catalog.js';

describe('prompt variable catalog', () => {
    it('builds deterministic runtime datetime preview values', () => {
        const values = buildRuntimeDatetimePreview(new Date(2026, 6, 15, 9, 7, 5));
        expect(values).toEqual({
            current_date: '2026-07-15',
            current_time: '09:07',
            current_datetime: '2026-07-15 09:07:05',
            current_year: 2026,
            current_month: 7,
            current_day: 15,
        });
    });

    it('uses the runtime state timezone, including calendar-day rollover', () => {
        const values = buildRuntimeDatetimePreview(
            new Date('2026-07-15T23:07:05Z'),
            'Asia/Tokyo',
        );
        expect(values.current_date).toBe('2026-07-16');
        expect(values.current_time).toBe('08:07');
        expect(values.current_datetime).toBe('2026-07-16 08:07:05');
    });

    it('only exposes variables.* upstream paths and explicit mapped inputs', () => {
        const result = buildPromptVariableContext({
            dataflowNode: {
                incoming_state: [
                    { path: 'topic', type: 'string', sample_value: 'must-not-leak', availability: 'guaranteed' },
                    { path: 'variables.audience', type: 'string', sample_value: 'engineers', availability: 'guaranteed' },
                ],
                input_mapping: [
                    { target: 'topic', status: 'ok', type: 'string', sample_value: 'AI' },
                    { target: 'missing', status: 'missing', type: 'string', sample_value: 'no' },
                ],
            },
            now: new Date(2026, 0, 2, 3, 4, 5),
        });

        expect(result.values.topic).toBe('AI');
        expect(result.values.audience).toBe('engineers');
        expect(result.values.missing).toBeUndefined();
        expect(result.catalog.some((entry) => entry.name === 'missing')).toBe(false);
    });

    it('matches runtime precedence: local > mapped input > preview/flow > system', () => {
        const result = buildPromptVariableContext({
            flowVariables: { topic: { value: 'flow' }, company: { value: 'ACME' } },
            previewExecutionState: { variables: { topic: 'preview' } },
            dataflowNode: {
                incoming_state: [],
                input_mapping: [{ target: 'topic', status: 'ok', type: 'string', sample_value: 'mapped' }],
            },
            nodeLocalVariables: { topic: 'local' },
            now: new Date(2026, 0, 2, 3, 4, 5),
        });

        expect(result.values.topic).toBe('local');
        expect(result.values.company).toBe('ACME');
        expect(result.values.current_date).toBe('2026-01-02');
        expect(result.catalog.find((entry) => entry.name === 'topic').source).toBe('local');
    });

    it('catalogs interface fields from incoming_state as plain top-level values', () => {
        const result = buildPromptVariableContext({
            dataflowNode: {
                incoming_state: [
                    {
                        path: 'email',
                        type: 'string',
                        source: 'interface',
                        sample_value: 'lead@example.com',
                        availability: 'guaranteed',
                    },
                    { path: 'topic', type: 'string', sample_value: 'must-not-leak', availability: 'guaranteed' },
                ],
                input_mapping: [],
            },
            now: new Date(2026, 0, 2, 3, 4, 5),
        });

        expect(result.values.email).toBe('lead@example.com');
        expect(result.values.topic).toBeUndefined();
        expect(result.catalog.find((entry) => entry.name === 'email')).toMatchObject({
            source: 'interface',
            availability: 'guaranteed',
            hasValue: true,
        });
    });

    it('takes observed interface values from previewExecutionState top-level paths', () => {
        const result = buildPromptVariableContext({
            dataflowNode: {
                incoming_state: [{ path: 'email', type: 'string', source: 'interface', availability: 'guaranteed' }],
                input_mapping: [],
            },
            previewExecutionState: { email: 'preview@example.com', content: 'ignored' },
            now: new Date(2026, 0, 2, 3, 4, 5),
        });
        expect(result.values.email).toBe('preview@example.com');
        expect(result.catalog.find((entry) => entry.name === 'email')).toMatchObject({ source: 'interface', availability: 'observed' });
        expect(result.catalog.find((entry) => entry.name === 'content')).toBeUndefined();
    });

    it('catalogs context variables without inventing preview values', () => {
        const result = buildPromptVariableContext({ now: new Date(2026, 0, 2, 3, 4, 5) });
        const userName = result.catalog.find((entry) => entry.name === 'user_name');
        expect(userName).toMatchObject({ source: 'system', availability: 'runtime', hasValue: false });
        expect(Object.hasOwn(result.values, 'user_name')).toBe(false);
    });
});
