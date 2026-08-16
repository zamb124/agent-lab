import { describe, expect, it } from 'vitest';

import { flowUIDocumentHasMessageComposer, overlayFlowUILocalValues } from '../../../../core/frontend/static/lib/flow-ui/runtime/document-composer.js';
import { buildDefaultChatDocument } from '../../../../core/frontend/static/lib/flow-ui/templates/chat-template.js';
import { FLOW_UI_ACTIONS } from '../../../../core/frontend/static/lib/flow-ui/protocol/constants.js';

function leaf(componentId, type, properties, actions = {}) {
    return {
        component_id: componentId,
        type,
        kind: 'leaf',
        properties,
        children: [],
        container_layout: null,
        placement: { base: {}, overrides: {} },
        bindings: {},
        actions,
    };
}

describe('flowUIDocumentHasMessageComposer', () => {
    it('detects default chat composer + submit', () => {
        expect(flowUIDocumentHasMessageComposer(buildDefaultChatDocument({ greetingMessage: '' }))).toBe(true);
    });

    it('returns false for submit without composer', () => {
        const document = {
            surfaces: {
                main: {
                    components: {
                        submit: leaf('submit', 'Button', { label: 'Go' }, {
                            press: { kind: 'event', name: FLOW_UI_ACTIONS.submit },
                        }),
                    },
                },
            },
        };
        expect(flowUIDocumentHasMessageComposer(document)).toBe(false);
    });
});

describe('overlayFlowUILocalValues', () => {
    it('keeps local composer values over an incoming snapshot', () => {
        const local = {
            surfaces: {
                main: { data_model: { values: { message: 'draft', files: [{ file_id: 'f1' }] } } },
            },
        };
        const incoming = {
            document_id: 'ui',
            surfaces: {
                main: { data_model: { values: { message: '', files: [] } } },
            },
        };
        const next = overlayFlowUILocalValues(local, incoming);
        expect(next.surfaces.main.data_model.values.message).toBe('draft');
        expect(next.surfaces.main.data_model.values.files).toEqual([{ file_id: 'f1' }]);
        expect(next.document_id).toBe('ui');
    });

    it('returns incoming when there is no local document', () => {
        const incoming = { surfaces: { main: { data_model: { values: { message: '' } } } } };
        expect(overlayFlowUILocalValues(null, incoming)).toBe(incoming);
    });
});
