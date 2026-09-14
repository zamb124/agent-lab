/**
 * Slice ``flows/interface_editor``: документ живёт в истории (undo/redo с коалесценцией),
 * выделение и страница сбрасываются вместе с документом, payload'ы валидируются fail-closed.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';

import { interfaceEditorSlice } from '../../../../apps/flows/ui/events/resources/interface-editor.resource.js';
import { EMPTY_DOCUMENT, HISTORY_LIMIT } from '../../../../apps/flows/ui/components/interface-editor/interface-editor-domain.js';
import { buildBus } from '../../helpers/bus-fixtures.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

beforeEach(() => resetFactories());
afterEach(() => resetFactories());

function build() {
    registerFactory(interfaceEditorSlice);
    const collected = collectFactories([interfaceEditorSlice]);
    const { bus, getState } = buildBus({ slices: collected.slices });
    return { getState, dispatch: (type, payload) => bus.dispatch(type, payload) };
}

function withHeading(text) {
    return {
        start_page_id: 'main',
        pages: [{ page_id: 'main', title: '', blocks: [{ block_id: 'h', type: 'heading', text, level: 2 }] }],
    };
}

function editorState(getState) {
    return getState().flowsInterfaceEditor;
}

describe('flows/interface_editor slice', () => {
        it('starts closed, on the add tab and desktop viewport', () => {
        const { getState } = build();
        expect(editorState(getState)).toMatchObject({
            documentKey: '',
            history: null,
            pageId: '',
            selectedBlockId: '',
            viewport: 'desktop',
            preview: false,
            sidebarTab: 'add',
            problems: [],
        });
    });

    it('stores document problems for the shared header flyout', () => {
        const { dispatch, getState } = build();
        dispatch('flows/interface_editor/document_opened', { documentKey: 'flow-1:default', document: EMPTY_DOCUMENT });
        const problems = [{ code: 'inputs_without_action', severity: 'error', pageId: 'main', blockId: null, property: null, params: {} }];
        dispatch('flows/interface_editor/problems_set', { problems });
        expect(editorState(getState).problems).toEqual(problems);
        expect(() => dispatch('flows/interface_editor/problems_set', { problems: null })).toThrow(/problems array required/);
    });

    it('opens a document on its start page and rejects commits without a document', () => {
        const { dispatch, getState } = build();
        expect(() => dispatch('flows/interface_editor/document_committed', { document: EMPTY_DOCUMENT })).toThrow(/no document opened/);
        expect(() => dispatch('flows/interface_editor/document_opened', { document: EMPTY_DOCUMENT })).toThrow(/documentKey required/);
        dispatch('flows/interface_editor/document_opened', { documentKey: 'flow-1:default', document: EMPTY_DOCUMENT });
        expect(editorState(getState).pageId).toBe('main');
        expect(editorState(getState).history.present).toEqual(EMPTY_DOCUMENT);
    });

    it('coalesces property edits by key and keeps the history bounded', () => {
        const { dispatch, getState } = build();
        dispatch('flows/interface_editor/document_opened', { documentKey: 'flow-1:default', document: withHeading('a') });
        dispatch('flows/interface_editor/document_committed', { document: withHeading('ab'), coalesceKey: 'h:text' });
        dispatch('flows/interface_editor/document_committed', { document: withHeading('abc'), coalesceKey: 'h:text' });
        expect(editorState(getState).history.past).toHaveLength(1);
        dispatch('flows/interface_editor/history_undone', {});
        expect(editorState(getState).history.present).toEqual(withHeading('a'));
        dispatch('flows/interface_editor/history_redone', {});
        expect(editorState(getState).history.present).toEqual(withHeading('abc'));
        for (let index = 0; index < HISTORY_LIMIT + 10; index += 1) {
            dispatch('flows/interface_editor/document_committed', { document: withHeading(`v${index}`) });
        }
        expect(editorState(getState).history.past.length).toBeLessThanOrEqual(HISTORY_LIMIT);
    });

    it('selecting a block switches to properties, selecting a page clears the block', () => {
        const { dispatch, getState } = build();
        dispatch('flows/interface_editor/document_opened', { documentKey: 'flow-1:default', document: withHeading('a') });
        dispatch('flows/interface_editor/block_selected', { blockId: 'h' });
        expect(editorState(getState)).toMatchObject({ selectedBlockId: 'h', sidebarTab: 'properties' });
        dispatch('flows/interface_editor/page_selected', { pageId: 'main' });
        expect(editorState(getState).selectedBlockId).toBe('');
        expect(() => dispatch('flows/interface_editor/viewport_set', { viewport: 'watch' })).toThrow(/unknown viewport/);
        expect(() => dispatch('flows/interface_editor/sidebar_tab_set', { tab: 'layers' })).toThrow(/unknown sidebar tab/);
        expect(() => dispatch('flows/interface_editor/preview_set', { preview: 'yes' })).toThrow(/preview must be boolean/);
    });
});
