/**
 * Slice локального UI-состояния панели «Запуск агента».
 *
 * Хранит флаг «сохранять контекст между запусками» и список mock-ответов LLM,
 * которые редактируются через модалку `flows.mocks` и кладутся в
 * `params.metadata.mock` при `flows/chat_send`.
 * Ввод текста и файлы принадлежат общему `chat-input`, как и в основном чате.
 *
 * Транспорта нет: createSlice без HTTP/WS. Сетевая часть запуска
 * живёт в `flows/chat_send` (см. `chat.resource.js`).
 */

import { createSlice } from '@platform/lib/events/index.js';

const EMPTY_MOCKS = Object.freeze([]);

function _normalizeMock(raw) {
    if (!raw || typeof raw !== 'object') return null;
    const match = typeof raw.match === 'string' ? raw.match : '';
    const response = typeof raw.response === 'string' ? raw.response : '';
    return Object.freeze({ match, response });
}

export const executionUiSlice = createSlice({
    name: 'flows/execution_ui',
    extraInitial: {
        persistContext: true,
        mockResponses: EMPTY_MOCKS,
    },
    actions: {
        togglePersistContext: 'persist_context_toggled',
        setMocks: 'mocks_set',
    },
    extraReducer: (state, event) => {
        const t = event.type;
        const p = event.payload;

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

        return state;
    },
});
