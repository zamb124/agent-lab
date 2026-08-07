import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { interfaceEditorSlice } from '../../../../apps/flows/ui/events/resources/interface-editor.resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { buildBus } from '../../helpers/bus-fixtures.js';

beforeEach(() => resetFactories());
afterEach(() => resetFactories());

function build() {
    registerFactory(interfaceEditorSlice);
    const collected = collectFactories([interfaceEditorSlice]);
    return buildBus({ slices: collected.slices });
}

describe('flows/interface_editor quiet chrome defaults', () => {
    it('starts with overlays off and guides on for snap', () => {
        const { getState } = build();
        const state = getState().flowsInterfaceEditor;
        expect(state.gridVisible).toBe(false);
        expect(state.baselineVisible).toBe(false);
        expect(state.rulersVisible).toBe(false);
        expect(state.dataFlowVisible).toBe(false);
        expect(state.guidesVisible).toBe(true);
        expect(state.snapEnabled).toBe(true);
    });
});
