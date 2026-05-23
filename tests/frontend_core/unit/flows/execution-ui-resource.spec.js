import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { executionUiSlice } from '../../../../apps/flows/ui/events/resources/execution-ui.resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { buildBus } from '../../helpers/bus-fixtures.js';

beforeEach(() => resetFactories());
afterEach(() => resetFactories());

function build() {
    registerFactory(executionUiSlice);
    const collected = collectFactories([executionUiSlice]);
    return buildBus({ slices: collected.slices });
}

describe('flows/execution_ui slice', () => {
    it('хранит только настройки execution-чата, без composer state в slice', () => {
        const { getState } = build();
        const s = getState().flowsExecutionUi;
        expect(s).toEqual({
            persistContext: true,
            mockResponses: [],
        });
        expect(executionUiSlice.actions.setInputText).toBeUndefined();
        expect(executionUiSlice.actions.addFiles).toBeUndefined();
        expect(executionUiSlice.actions.removeFile).toBeUndefined();
        expect(executionUiSlice.actions.clear).toBeUndefined();
    });

    it('persistContext и mockResponses остаются единственными mutable controls', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/execution_ui/persist_context_toggled', { value: false });
        bus.dispatch('flows/execution_ui/mocks_set', {
            mocks: [
                { match: 'hello', response: 'world' },
                { match: 123, response: null },
            ],
        });
        expect(getState().flowsExecutionUi.persistContext).toBe(false);
        expect(getState().flowsExecutionUi.mockResponses).toEqual([
            { match: 'hello', response: 'world' },
            { match: '', response: '' },
        ]);
    });
});
