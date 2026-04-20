/**
 * Slice локального UI-состояния панели «Запуск агента».
 *
 * Хранит ввод пользователя, прикреплённые файлы (в base64), флаг
 * «сохранять контекст между запусками» и список mock-ответов LLM,
 * которые редактируются через модалку `flows.mocks` и кладутся в
 * `params.metadata.mock` при `flows/chat_send`.
 *
 * Транспорта нет: createSlice без HTTP/WS. Сетевая часть запуска
 * живёт в `flows/chat_send` (см. `chat.resource.js`).
 */

import { createSlice } from '@platform/lib/events/index.js';

const EMPTY_FILES = Object.freeze([]);
const EMPTY_MOCKS = Object.freeze([]);

function _normalizeFile(raw) {
    if (!raw || typeof raw !== 'object') return null;
    if (typeof raw.name !== 'string' || raw.name.length === 0) return null;
    if (typeof raw.bytes !== 'string' || raw.bytes.length === 0) return null;
    const size = typeof raw.size === 'number' ? raw.size : 0;
    const type = typeof raw.type === 'string' ? raw.type : 'application/octet-stream';
    return Object.freeze({ name: raw.name, size, type, bytes: raw.bytes });
}

function _normalizeMock(raw) {
    if (!raw || typeof raw !== 'object') return null;
    const match = typeof raw.match === 'string' ? raw.match : '';
    const response = typeof raw.response === 'string' ? raw.response : '';
    return Object.freeze({ match, response });
}

export const executionUiSlice = createSlice({
    name: 'flows/execution_ui',
    extraInitial: {
        inputText: '',
        attachedFiles: EMPTY_FILES,
        persistContext: true,
        mockResponses: EMPTY_MOCKS,
    },
    actions: {
        setInputText: 'input_text_set',
        addFiles: 'files_added',
        removeFile: 'file_removed',
        togglePersistContext: 'persist_context_toggled',
        setMocks: 'mocks_set',
        clear: 'cleared',
    },
    extraReducer: (state, event) => {
        const t = event.type;
        const p = event.payload;

        if (t === 'flows/execution_ui/input_text_set') {
            if (!p || typeof p.text !== 'string') return state;
            return { ...state, inputText: p.text };
        }

        if (t === 'flows/execution_ui/files_added') {
            if (!p || !Array.isArray(p.files)) return state;
            const incoming = p.files
                .map(_normalizeFile)
                .filter((f) => f !== null);
            if (incoming.length === 0) return state;
            return {
                ...state,
                attachedFiles: Object.freeze([...state.attachedFiles, ...incoming]),
            };
        }

        if (t === 'flows/execution_ui/file_removed') {
            if (!p || typeof p.index !== 'number') return state;
            const idx = p.index;
            if (idx < 0 || idx >= state.attachedFiles.length) return state;
            const next = state.attachedFiles.filter((_, i) => i !== idx);
            return { ...state, attachedFiles: Object.freeze(next) };
        }

        if (t === 'flows/execution_ui/persist_context_toggled') {
            if (p && typeof p.value === 'boolean') {
                return { ...state, persistContext: p.value };
            }
            return { ...state, persistContext: !state.persistContext };
        }

        if (t === 'flows/execution_ui/mocks_set') {
            if (!p || !Array.isArray(p.mocks)) return state;
            const next = p.mocks.map(_normalizeMock).filter((m) => m !== null);
            return { ...state, mockResponses: Object.freeze(next) };
        }

        if (t === 'flows/execution_ui/cleared') {
            return { ...state, inputText: '', attachedFiles: EMPTY_FILES };
        }

        return state;
    },
});
