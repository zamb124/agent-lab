/**
 * Slice локального UI-состояния панели «Запуск агента».
 *
 * Хранит флаг «сохранять контекст между запусками» и mock-ответы.
 * Ввод текста и файлы принадлежат общему `chat-input`, как и в основном чате.
 *
 * Транспорта нет: createSlice без HTTP/WS. Сетевая часть запуска
 * живёт в `flows/chat_send` (см. `chat.resource.js`).
 */

import { createSlice } from '@platform/lib/events/index.js';

function normalizeMockResponses(value) {
    if (!Array.isArray(value)) {
        return [];
    }
    return value.map((item) => {
        const record = item !== null && typeof item === 'object' && !Array.isArray(item)
            ? item
            : {};
        return {
            match: typeof record.match === 'string' ? record.match : '',
            response: typeof record.response === 'string' ? record.response : '',
        };
    });
}

export const executionUiSlice = createSlice({
    name: 'flows/execution_ui',
    extraInitial: {
        persistContext: true,
        mockResponses: [],
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
            return { ...state, mockResponses: normalizeMockResponses(p && p.mocks) };
        }

        return state;
    },
});
