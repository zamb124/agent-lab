import { describe, expect, it } from 'vitest';
import {
    FLOW_UI_QUICK_REQUIRED_NAME,
    flowUIComponentQuickProps,
} from '../../../../core/frontend/static/lib/flow-ui/editor/component-quick-props.js';

describe('flowUIComponentQuickProps', () => {
    it('exposes Button variant + disabled from schema', () => {
        const props = flowUIComponentQuickProps('Button');
        expect(props.map((prop) => prop.name)).toEqual(['variant', 'disabled']);
        expect(props[0].kind).toBe('enum');
        expect(props[1].kind).toBe('boolean');
        expect(props[0].options?.map((option) => option.value)).toEqual(['primary', 'secondary']);
    });

    it('returns empty list for layout types without boolean/enum schema', () => {
        expect(flowUIComponentQuickProps('Grid')).toEqual([]);
        expect(flowUIComponentQuickProps('Stack')).toEqual([]);
        expect(flowUIComponentQuickProps('Card')).toEqual([]);
    });

    it('adds markdownMode and synthetic required for TextField', () => {
        const props = flowUIComponentQuickProps('TextField');
        expect(props.map((prop) => prop.name)).toEqual([
            'markdownMode',
            FLOW_UI_QUICK_REQUIRED_NAME,
        ]);
        expect(props[1].kind).toBe('boolean');
        expect(props[1].labelKey).toBe('interface_editor.inspector_required');
    });

    it('exposes FileUpload multiple + markdownMode + required', () => {
        expect(flowUIComponentQuickProps('FileUpload').map((prop) => prop.name)).toEqual([
            'multiple',
            'markdownMode',
            FLOW_UI_QUICK_REQUIRED_NAME,
        ]);
    });

    it('exposes PageShell contentMode and Modal open', () => {
        expect(flowUIComponentQuickProps('PageShell').map((prop) => prop.name)).toEqual([
            'contentMode',
        ]);
        expect(flowUIComponentQuickProps('Modal').map((prop) => prop.name)).toEqual(['open']);
    });

    it('exposes Heading level + markdownMode without invented fields', () => {
        expect(flowUIComponentQuickProps('Heading').map((prop) => prop.name)).toEqual([
            'level',
            'markdownMode',
        ]);
    });
});
