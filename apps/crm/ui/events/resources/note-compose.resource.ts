/**
 * Черновик новой заметки: распознанный текст диктовки до открытия note-page.
 */

import { createSlice } from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { CrmNoteComposeSlice } from '../crm.types.js';

export const noteComposeSlice = createSlice({
    name: 'crm/note_compose',
    extraInitial: {
        description: '',
    },
    extraEvents: {
        DESCRIPTION_SET: 'description_set',
    },
    actions: {
        setDescription: 'description_set',
    },
    extraReducer: (state: CrmNoteComposeSlice, event) => {
        switch (event.type) {
            case 'crm/note_compose/description_set': {
                const payload = event.payload;
                if (!isPlainRecord(payload)) {
                    return state;
                }
                const description = payload.description;
                if (typeof description !== 'string') {
                    return state;
                }
                return { ...state, description };
            }
            default:
                return state;
        }
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/note_compose': typeof noteComposeSlice;
    }
}
