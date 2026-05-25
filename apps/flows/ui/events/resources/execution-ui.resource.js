/**
 * Slice локального UI-состояния панели «Запуск агента».
 *
 * Хранит флаг «сохранять контекст между запусками».
 * Ввод текста и файлы принадлежат общему `chat-input`, как и в основном чате.
 *
 * Транспорта нет: createSlice без HTTP/WS. Сетевая часть запуска
 * живёт в `flows/chat_send` (см. `chat.resource.js`).
 */

import { createSlice } from '@platform/lib/events/index.js';

export const executionUiSlice = createSlice({
    name: 'flows/execution_ui',
    extraInitial: {
        persistContext: true,
    },
    actions: {
        togglePersistContext: 'persist_context_toggled',
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

        return state;
    },
});
