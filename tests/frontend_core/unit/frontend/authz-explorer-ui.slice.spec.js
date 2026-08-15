/**
 * frontend/authz_explorer_ui — picker vs grant filters, URL-независимые actions.
 */
import { describe, it, expect } from 'vitest';
import { authzExplorerUiSlice } from '../../../../apps/frontend/ui/events/resources/authz-explorer.resource.js';

function reduce(eventType, payload, state = authzExplorerUiSlice.slice.initial) {
    return authzExplorerUiSlice.reducer(state, { type: eventType, payload });
}

describe('authzExplorerUiSlice reducer', () => {
    it('pickerTypeFilter не меняет grantTypeFilter', () => {
        const next = reduce(authzExplorerUiSlice.events.SET_PICKER_TYPE_FILTER, {
            pickerTypeFilter: 'wiki_page',
        });
        expect(next.pickerTypeFilter).toBe('wiki_page');
        expect(next.grantTypeFilter).toBe('');
    });

    it('grantTypeFilter не меняет pickerTypeFilter', () => {
        const withPicker = reduce(authzExplorerUiSlice.events.SET_PICKER_TYPE_FILTER, {
            pickerTypeFilter: 'crm_entity',
        });
        const next = reduce(
            authzExplorerUiSlice.events.SET_GRANT_TYPE_FILTER,
            { grantTypeFilter: 'wiki_page' },
            withPicker,
        );
        expect(next.pickerTypeFilter).toBe('crm_entity');
        expect(next.grantTypeFilter).toBe('wiki_page');
    });

    it('resetGrantFilters чистит только гранты', () => {
        const primed = reduce(
            authzExplorerUiSlice.events.SET_GRANT_TYPE_FILTER,
            { grantTypeFilter: 'flow' },
            reduce(authzExplorerUiSlice.events.SET_PICKER_TYPE_FILTER, {
                pickerTypeFilter: 'wiki_page',
            }),
        );
        const next = reduce(authzExplorerUiSlice.events.RESET_GRANT_FILTERS, {}, primed);
        expect(next.grantTypeFilter).toBe('');
        expect(next.relationFilter).toBe('');
        expect(next.sourceFilter).toBe('');
        expect(next.pickerTypeFilter).toBe('wiki_page');
    });

    it('resetPickerSearch чистит только пикер', () => {
        const primed = reduce(
            authzExplorerUiSlice.events.SET_OBJECTS_QUERY,
            { objectsQuery: 'wiki' },
            reduce(
                authzExplorerUiSlice.events.SET_GRANT_TYPE_FILTER,
                { grantTypeFilter: 'flow' },
                reduce(authzExplorerUiSlice.events.SET_PICKER_TYPE_FILTER, {
                    pickerTypeFilter: 'wiki_page',
                }),
            ),
        );
        const next = reduce(authzExplorerUiSlice.events.RESET_PICKER_SEARCH, {}, primed);
        expect(next.pickerTypeFilter).toBe('');
        expect(next.objectsQuery).toBe('');
        expect(next.peopleQuery).toBe('');
        expect(next.grantTypeFilter).toBe('flow');
    });

    it('selectUser и selectObject не зависят от URL', () => {
        const userState = reduce(authzExplorerUiSlice.events.SELECT_USER, {
            userId: 'u1',
        });
        expect(userState.mode).toBe('people');
        expect(userState.userId).toBe('u1');
        expect(userState.objectKey).toBe('');
        const objectState = reduce(authzExplorerUiSlice.events.SELECT_OBJECT, {
            objectType: 'wiki_page',
            objectKey: 'p1',
        });
        expect(objectState.mode).toBe('objects');
        expect(objectState.objectType).toBe('wiki_page');
        expect(objectState.objectKey).toBe('p1');
    });
});
