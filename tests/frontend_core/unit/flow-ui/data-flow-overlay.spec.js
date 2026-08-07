import { describe, expect, it } from 'vitest';
import {
    buildFlowUIDataFlowMarks,
    flowUIBindingScope,
} from '../../../../core/frontend/static/lib/flow-ui/editor/data-flow-marks.js';

describe('flow-ui data-flow overlay', () => {
    it('classifies JSON Pointer scopes', () => {
        expect(flowUIBindingScope('/values/message')).toBe('input');
        expect(flowUIBindingScope('/content/title')).toBe('content');
        expect(flowUIBindingScope('/system/tasks')).toBe('system');
        expect(flowUIBindingScope('/other')).toBeNull();
    });

    it('builds marks for values, content, system and submit', () => {
        const surface = {
            components: {
                name: {
                    component_id: 'name',
                    type: 'TextField',
                    bindings: { value: '/values/name' },
                    properties: { fieldName: 'full_name' },
                    actions: {},
                },
                title: {
                    component_id: 'title',
                    type: 'Heading',
                    bindings: { text: '/content/title' },
                    properties: {},
                    actions: {},
                },
                feed: {
                    component_id: 'feed',
                    type: 'ConversationFeed',
                    bindings: { tasks: '/system/tasks' },
                    properties: {},
                    actions: {},
                },
                send: {
                    component_id: 'send',
                    type: 'Button',
                    bindings: {},
                    properties: {},
                    actions: {
                        press: { kind: 'event', name: 'platform.ui.submit', context: {} },
                    },
                },
            },
        };
        const rects = [
            { componentId: 'name', rect: { x: 1, y: 2, width: 10, height: 20 } },
            { componentId: 'title', rect: { x: 3, y: 4, width: 11, height: 21 } },
            { componentId: 'feed', rect: { x: 5, y: 6, width: 12, height: 22 } },
            { componentId: 'send', rect: { x: 7, y: 8, width: 13, height: 23 } },
        ];
        const marks = buildFlowUIDataFlowMarks(surface, rects);
        expect(marks).toEqual([
            {
                componentId: 'name',
                scope: 'input',
                tag: '@state:ui_values.full_name',
                pointer: '/values/name',
                rect: { x: 1, y: 2, width: 10, height: 20 },
            },
            {
                componentId: 'title',
                scope: 'content',
                tag: '/content/title',
                pointer: '/content/title',
                rect: { x: 3, y: 4, width: 11, height: 21 },
            },
            {
                componentId: 'feed',
                scope: 'system',
                tag: '/system/tasks',
                pointer: '/system/tasks',
                rect: { x: 5, y: 6, width: 12, height: 22 },
            },
            {
                componentId: 'send',
                scope: 'submit',
                tag: 'submit → flow',
                rect: { x: 7, y: 8, width: 13, height: 23 },
            },
        ]);
    });

    it('skips components without measured rects', () => {
        const surface = {
            components: {
                orphan: {
                    component_id: 'orphan',
                    type: 'TextField',
                    bindings: { value: '/values/orphan' },
                    properties: {},
                    actions: {},
                },
            },
        };
        expect(buildFlowUIDataFlowMarks(surface, [])).toEqual([]);
    });
});
