import { EDITOR_VIEWPORTS } from './interface-editor-domain.js';

export const HOST_EDITOR_EVENTS = ['editor-undo', 'editor-redo', 'editor-viewport', 'editor-preview', 'editor-templates', 'editor-assist'];

export interface EditorFrame {
    top: number;
    left: number;
    width: number;
    height: number;
}

export interface InlineEdit {
    blockId: string;
    property: string;
    value: unknown;
    frame: EditorFrame;
    multiline: boolean;
}

export function editorFrameWidth(viewport: unknown): number {
    switch (viewport) {
        case 'desktop':
            return EDITOR_VIEWPORTS.desktop;
        case 'tablet':
            return EDITOR_VIEWPORTS.tablet;
        case 'mobile':
            return EDITOR_VIEWPORTS.mobile;
        default:
            throw new Error(`flows-interface-editor: unknown viewport ${String(viewport)}`);
    }
}

export function inlineTextControl(root: ParentNode): HTMLInputElement | HTMLTextAreaElement | null {
    const field = root.querySelector('.inline-edit');
    if (field === null) return null;
    if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) return field;
    throw new Error('flows-interface-editor: inline edit control must be an input or textarea');
}
