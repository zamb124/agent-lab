/**
 * Slice локального UI-состояния панели «Запуск агента».
 *
 * Хранит флаг «сохранять контекст между запусками» и mock-ответы.
 * Сам чат (ввод, файлы, стриминг A2A) живёт внутри `<platform-flow-ui>`;
 * `persistContext` панель транслирует в атрибут `fresh-context-per-turn`.
 *
 * Транспорта нет: createSlice без HTTP/WS.
 */

import { createSlice } from '@platform/lib/events/index.js';
import type { ExecutionUiSlice } from '../editor.types.js';

function normalizeMockResponses(value: unknown) {
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
    extraReducer: (state: ExecutionUiSlice, event) => {
        const t = event.type;
        const p = event.payload;

        if (t === 'flows/execution_ui/persist_context_toggled') {
            if (p && typeof (p as Record<string, any>).value === 'boolean') {
                return { ...state, persistContext: (p as Record<string, any>).value };
            }
            return { ...state, persistContext: !state.persistContext };
        }

        if (t === 'flows/execution_ui/mocks_set') {
            return { ...state, mockResponses: normalizeMockResponses(p && (p as Record<string, any>).mocks) };
        }

        return state;
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/execution_ui': typeof executionUiSlice;
    }
}
