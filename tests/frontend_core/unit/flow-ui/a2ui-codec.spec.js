import { describe, expect, it } from 'vitest';

import { decodeA2UIComponent } from '../../../../core/frontend/static/lib/flow-ui/protocol/a2ui-0-9-1-codec.js';

describe('a2ui-0-9-1-codec', () => {
    it('decodes bindings, children and press actions', () => {
        const component = decodeA2UIComponent({
            id: 'field',
            component: 'TextField',
            text: { path: '/values/message' },
            children: ['child'],
            action: { event: { name: 'platform.ui.submit', context: { intent: 'send' } } },
        });
        expect(component).toMatchObject({
            component_id: 'field',
            type: 'TextField',
            bindings: { text: '/values/message' },
            children: ['child'],
            actions: {
                press: { kind: 'event', name: 'platform.ui.submit', context: { intent: 'send' } },
            },
        });
    });

    it('rejects components without id', () => {
        expect(() => decodeA2UIComponent({ component: 'Text' })).toThrow(/invalid A2UI component/);
    });
});
