/**
 * Состояние редактора интерфейса: черновик документа с историей (undo/redo, коалесценция
 * по ``block_id:property``, лимит 80), выделение, активная страница, ширина холста, режим предпросмотра.
 *
 * Документ меняется только командами домена (`interface-editor-domain.js`); slice хранит результат.
 */

import { createSlice } from '@platform/lib/events/index.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import {
    EDITOR_VIEWPORTS,
    commitHistory,
    createHistory,
    redoHistory,
    undoHistory,
} from '../../components/interface-editor/interface-editor-domain.js';
import type { InterfaceEditorUiSlice } from '../editor.types.js';

function requirePayload(event: PlatformEvent): Record<string, unknown> {
    if (!isPlainRecord(event.payload)) {
        throw new Error(`flows/interface_editor: payload must be object for ${event.type}`);
    }
    return event.payload;
}

function requireDocument(payload: Record<string, unknown>, eventType: string): {
    record: Record<string, unknown>;
    pages: unknown[];
    startPageId: string;
} {
    const document = payload.document;
    if (!isPlainRecord(document)) {
        throw new Error(`flows/interface_editor: document required for ${eventType}`);
    }
    const pages = document.pages;
    const startPageId = document.start_page_id;
    if (!Array.isArray(pages) || typeof startPageId !== 'string' || startPageId === '') {
        throw new Error(`flows/interface_editor: document required for ${eventType}`);
    }
    return { record: document, pages, startPageId };
}

function requireHistory(state: any, eventType: any) {
    if (state.history === null) throw new Error(`flows/interface_editor: no document opened for ${eventType}`);
    return state.history;
}

export const interfaceEditorSlice = createSlice({
    name: 'flows/interface_editor',
    extraInitial: {
        /** ``flow_id:branch_id`` открытого документа. */
        documentKey: '',
        history: null,
        pageId: '',
        selectedBlockId: '',
        viewport: 'desktop',
        preview: false,
        sidebarTab: 'add',
        problems: Object.freeze([]),
    },
    extraEvents: {
        DOCUMENT_OPENED: 'document_opened',
        DOCUMENT_COMMITTED: 'document_committed',
        HISTORY_UNDONE: 'history_undone',
        HISTORY_REDONE: 'history_redone',
        PAGE_SELECTED: 'page_selected',
        BLOCK_SELECTED: 'block_selected',
        VIEWPORT_SET: 'viewport_set',
        PREVIEW_SET: 'preview_set',
        SIDEBAR_TAB_SET: 'sidebar_tab_set',
        PROBLEMS_SET: 'problems_set',
    },
    actions: {
        openDocument: 'document_opened',
        commitDocument: 'document_committed',
        undo: 'history_undone',
        redo: 'history_redone',
        selectPage: 'page_selected',
        selectBlock: 'block_selected',
        setViewport: 'viewport_set',
        setPreview: 'preview_set',
        setSidebarTab: 'sidebar_tab_set',
        setProblems: 'problems_set',
    },
    extraReducer: (state: InterfaceEditorUiSlice, event) => {
        const type = event.type;
        if (type === 'flows/interface_editor/document_opened') {
            const payload = requirePayload(event);
            const document = requireDocument(payload, type);
            const documentKey = payload.documentKey;
            if (typeof documentKey !== 'string' || documentKey === '') {
                throw new Error(`flows/interface_editor: documentKey required for ${type}`);
            }
            return {
                ...state,
                documentKey,
                history: createHistory(document.record),
                pageId: document.startPageId,
                selectedBlockId: '',
                preview: false,
                problems: Object.freeze([]),
            };
        }
        if (type === 'flows/interface_editor/document_committed') {
            const payload = requirePayload(event);
            const document = requireDocument(payload, type);
            const coalesceKey = typeof payload.coalesceKey === 'string' ? payload.coalesceKey : null;
            const history = commitHistory(requireHistory(state, type), document.record, coalesceKey);
            const pageId = document.pages.some((page) => isPlainRecord(page) && page.page_id === state.pageId)
                ? state.pageId
                : document.startPageId;
            return { ...state, history, pageId };
        }
        if (type === 'flows/interface_editor/history_undone' || type === 'flows/interface_editor/history_redone') {
            const current = requireHistory(state, type);
            const history = type.endsWith('undone') ? undoHistory(current) : redoHistory(current);
            const document = history.present;
            const pageId = document.pages.some((page: any) => page.page_id === state.pageId) ? state.pageId : document.start_page_id;
            return { ...state, history, pageId, selectedBlockId: '' };
        }
        if (type === 'flows/interface_editor/page_selected') {
            const payload = requirePayload(event);
            const pageId = payload.pageId;
            if (typeof pageId !== 'string' || pageId === '') throw new Error(`flows/interface_editor: pageId required for ${type}`);
            return { ...state, pageId, selectedBlockId: '' };
        }
        if (type === 'flows/interface_editor/block_selected') {
            const payload = requirePayload(event);
            const blockId = payload.blockId;
            if (typeof blockId !== 'string') throw new Error(`flows/interface_editor: blockId must be string for ${type}`);
            return { ...state, selectedBlockId: blockId, sidebarTab: blockId === '' ? state.sidebarTab : 'properties' };
        }
        if (type === 'flows/interface_editor/viewport_set') {
            const payload = requirePayload(event);
            const viewport = payload.viewport;
            if (typeof viewport !== 'string' || !Object.hasOwn(EDITOR_VIEWPORTS, viewport)) throw new Error(`flows/interface_editor: unknown viewport ${String(viewport)}`);
            return { ...state, viewport };
        }
        if (type === 'flows/interface_editor/preview_set') {
            const payload = requirePayload(event);
            const preview = payload.preview;
            if (typeof preview !== 'boolean') throw new Error(`flows/interface_editor: preview must be boolean for ${type}`);
            return { ...state, preview };
        }
        if (type === 'flows/interface_editor/sidebar_tab_set') {
            const payload = requirePayload(event);
            const tab = payload.tab;
            if (tab !== 'add' && tab !== 'properties') throw new Error(`flows/interface_editor: unknown sidebar tab ${String(tab)}`);
            return { ...state, sidebarTab: tab };
        }
        if (type === 'flows/interface_editor/problems_set') {
            const payload = requirePayload(event);
            const problems = payload.problems;
            if (!Array.isArray(problems)) {
                throw new Error(`flows/interface_editor: problems array required for ${type}`);
            }
            return { ...state, problems: Object.freeze(problems.slice()) };
        }
        return state;
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/interface_editor': typeof interfaceEditorSlice;
    }
}
