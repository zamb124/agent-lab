/**
 * Состояние редактора интерфейса: черновик документа с историей (undo/redo, коалесценция
 * по ``block_id:property``, лимит 80), выделение, активная страница, ширина холста, режим предпросмотра.
 *
 * Документ меняется только командами домена (`interface-editor-domain.js`); slice хранит результат.
 */

import { createSlice } from '@platform/lib/events/index.js';
import {
    EDITOR_VIEWPORTS,
    commitHistory,
    createHistory,
    redoHistory,
    undoHistory,
} from '../../components/interface-editor/interface-editor-domain.js';

function requirePayload(event) {
    const payload = event.payload;
    if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
        throw new Error(`flows/interface_editor: payload must be object for ${event.type}`);
    }
    return payload;
}

function requireDocument(payload, eventType) {
    const document = payload.document;
    if (document === null || typeof document !== 'object' || !Array.isArray(document.pages)) {
        throw new Error(`flows/interface_editor: document required for ${eventType}`);
    }
    return document;
}

function requireHistory(state, eventType) {
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
    extraReducer: (state, event) => {
        const type = event.type;
        if (type === 'flows/interface_editor/document_opened') {
            const payload = requirePayload(event);
            const document = requireDocument(payload, type);
            if (typeof payload.documentKey !== 'string' || payload.documentKey === '') {
                throw new Error(`flows/interface_editor: documentKey required for ${type}`);
            }
            return {
                ...state,
                documentKey: payload.documentKey,
                history: createHistory(document),
                pageId: document.start_page_id,
                selectedBlockId: '',
                preview: false,
                problems: Object.freeze([]),
            };
        }
        if (type === 'flows/interface_editor/document_committed') {
            const payload = requirePayload(event);
            const document = requireDocument(payload, type);
            const coalesceKey = typeof payload.coalesceKey === 'string' ? payload.coalesceKey : null;
            const history = commitHistory(requireHistory(state, type), document, coalesceKey);
            const pageId = document.pages.some((page) => page.page_id === state.pageId) ? state.pageId : document.start_page_id;
            return { ...state, history, pageId };
        }
        if (type === 'flows/interface_editor/history_undone' || type === 'flows/interface_editor/history_redone') {
            const current = requireHistory(state, type);
            const history = type.endsWith('undone') ? undoHistory(current) : redoHistory(current);
            const document = history.present;
            const pageId = document.pages.some((page) => page.page_id === state.pageId) ? state.pageId : document.start_page_id;
            return { ...state, history, pageId, selectedBlockId: '' };
        }
        if (type === 'flows/interface_editor/page_selected') {
            const payload = requirePayload(event);
            if (typeof payload.pageId !== 'string' || payload.pageId === '') throw new Error(`flows/interface_editor: pageId required for ${type}`);
            return { ...state, pageId: payload.pageId, selectedBlockId: '' };
        }
        if (type === 'flows/interface_editor/block_selected') {
            const payload = requirePayload(event);
            if (typeof payload.blockId !== 'string') throw new Error(`flows/interface_editor: blockId must be string for ${type}`);
            return { ...state, selectedBlockId: payload.blockId, sidebarTab: payload.blockId === '' ? state.sidebarTab : 'properties' };
        }
        if (type === 'flows/interface_editor/viewport_set') {
            const payload = requirePayload(event);
            if (!Object.hasOwn(EDITOR_VIEWPORTS, payload.viewport)) throw new Error(`flows/interface_editor: unknown viewport ${String(payload.viewport)}`);
            return { ...state, viewport: payload.viewport };
        }
        if (type === 'flows/interface_editor/preview_set') {
            const payload = requirePayload(event);
            if (typeof payload.preview !== 'boolean') throw new Error(`flows/interface_editor: preview must be boolean for ${type}`);
            return { ...state, preview: payload.preview };
        }
        if (type === 'flows/interface_editor/sidebar_tab_set') {
            const payload = requirePayload(event);
            if (payload.tab !== 'add' && payload.tab !== 'properties') throw new Error(`flows/interface_editor: unknown sidebar tab ${String(payload.tab)}`);
            return { ...state, sidebarTab: payload.tab };
        }
        if (type === 'flows/interface_editor/problems_set') {
            const payload = requirePayload(event);
            if (!Array.isArray(payload.problems)) {
                throw new Error(`flows/interface_editor: problems array required for ${type}`);
            }
            return { ...state, problems: Object.freeze(payload.problems.slice()) };
        }
        return state;
    },
});
