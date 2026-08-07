import { describe, expect, it, vi } from 'vitest';

import {
    evaluateFlowUIChecks,
    evaluateFlowUICheck,
    isEmptyCheckValue,
} from '../../../../core/frontend/static/lib/flow-ui/runtime/flow-ui-checks.js';
import { FlowUIController } from '../../../../core/frontend/static/lib/flow-ui/runtime/flow-ui-controller.js';
import { createLocalFlowUIProfile } from '../../../../core/frontend/static/lib/flow-ui/runtime/flow-ui-profile.js';

function surfaceWithRequiredField(message = '') {
    return {
        surface_id: 'main',
        root_component_id: 'root',
        components: {
            root: {
                component_id: 'root',
                type: 'PageShell',
                kind: 'container',
                properties: {},
                children: ['field', 'submit'],
                container_layout: null,
                placement: { base: {}, overrides: {} },
                bindings: {},
                actions: {},
                checks: [],
            },
            field: {
                component_id: 'field',
                type: 'TextField',
                kind: 'leaf',
                properties: { label: 'Name' },
                children: [],
                container_layout: null,
                placement: { base: {}, overrides: {} },
                bindings: { value: '/values/name' },
                actions: {},
                checks: [{ function: 'required', message }],
            },
            submit: {
                component_id: 'submit',
                type: 'Button',
                kind: 'leaf',
                properties: { label: 'Send' },
                children: [],
                container_layout: null,
                placement: { base: {}, overrides: {} },
                bindings: {},
                actions: {
                    press: { kind: 'event', name: 'platform.ui.submit', context: {} },
                },
                checks: [],
            },
        },
        data_model: { content: {}, values: { name: '' }, system: {} },
    };
}

function documentSnapshot() {
    return {
        schema_version: 1,
        document_id: 'flow-ui:context-1',
        revision: 1,
        template_version: '1.0.0',
        catalog_id: 'https://linnex.io/a2ui/catalog/platform/v1',
        active_page_id: 'main',
        session_view_state: {},
        pages: {
            main: { page_id: 'main', title: { default: 'Main' }, root_surface_id: 'main' },
        },
        surfaces: { main: surfaceWithRequiredField('Name is required') },
        global_data_model: { content: {}, values: {}, system: {} },
        policy: {},
    };
}

describe('flow-ui-checks', () => {
    it('treats blank strings and empty arrays as empty', () => {
        expect(isEmptyCheckValue('')).toBe(true);
        expect(isEmptyCheckValue('  ')).toBe(true);
        expect(isEmptyCheckValue([])).toBe(true);
        expect(isEmptyCheckValue(false)).toBe(true);
        expect(isEmptyCheckValue('x')).toBe(false);
        expect(isEmptyCheckValue(0)).toBe(false);
    });

    it('evaluates required with custom and default messages', () => {
        expect(evaluateFlowUICheck({ function: 'required', message: 'Need it' }, '', 'en'))
            .toBe('Need it');
        expect(evaluateFlowUICheck({ function: 'required', message: '' }, null, 'en'))
            .toBe('This field is required');
        expect(evaluateFlowUICheck({ function: 'required', message: '' }, null, 'ru'))
            .toBe('Обязательное поле');
        expect(evaluateFlowUICheck({ function: 'required', message: '' }, 'ok', 'en')).toBeNull();
    });

    it('returns first failing check per component on a surface', () => {
        const surface = surfaceWithRequiredField('Name is required');
        expect(evaluateFlowUIChecks(surface, { locale: 'en' })).toEqual({
            field: 'Name is required',
        });
        surface.data_model.values.name = 'Alex';
        expect(evaluateFlowUIChecks(surface, { locale: 'en' })).toEqual({});
    });
});

describe('FlowUIController submit gate', () => {
    it('blocks submit when required field is empty and sets fieldErrors', async () => {
        const controller = new FlowUIController({
            flowId: 'flow-1',
            initialDocument: documentSnapshot(),
            profile: createLocalFlowUIProfile('editor_test'),
        });
        await controller.connect();
        const sendSpy = vi.spyOn(controller, '_sendControl');

        const blocked = await controller.submit('main', 'submit');
        expect(blocked).toEqual({
            blocked: true,
            fieldErrors: Object.freeze({ field: 'Name is required' }),
        });
        expect(controller.fieldErrors).toEqual({ field: 'Name is required' });
        expect(sendSpy).not.toHaveBeenCalled();

        controller.setValue('main', '/values/name', 'Alex');
        expect(controller.fieldErrors).toEqual({});
        const preview = await controller.submit('main', 'submit');
        expect(preview.preview).toBe(true);
        expect(sendSpy).not.toHaveBeenCalled();
    });
});
