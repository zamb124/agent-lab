/**
 * Access Explorer — by-user / by-object / why / objects / revoke (команды `frontend/authz_explorer/*`,
 * REST-зеркало `apps/frontend/api/authz_explorer.py`) + UI slice.
 */
import { createAsyncOp, createSlice } from '@platform/lib/events/index.js';

const WS_TIMEOUT_MS = 15_000;

export const authzExplorerByUserOp = createAsyncOp({
    name: 'frontend/authz_explorer_by_user',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/authz_explorer/by_user_requested',
    restMirror: { method: 'GET', path: '/frontend/api/authz/explorer/by-user' },
});

export const authzExplorerByObjectOp = createAsyncOp({
    name: 'frontend/authz_explorer_by_object',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/authz_explorer/by_object_requested',
    restMirror: { method: 'GET', path: '/frontend/api/authz/explorer/by-object' },
});

export const authzExplorerWhyOp = createAsyncOp({
    name: 'frontend/authz_explorer_why',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/authz_explorer/why_requested',
    restMirror: { method: 'GET', path: '/frontend/api/authz/explorer/why' },
});

export const authzExplorerObjectsOp = createAsyncOp({
    name: 'frontend/authz_explorer_objects',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/authz_explorer/objects_requested',
    restMirror: { method: 'GET', path: '/frontend/api/authz/explorer/objects' },
});

export const authzExplorerRevokeOp = createAsyncOp({
    name: 'frontend/authz_explorer_revoke',
    successToastKey: 'frontend:access_page.toast_revoked',
    errorToastKey: 'frontend:access_page.err_revoke',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/authz_explorer/revoke_requested',
    restMirror: { method: 'POST', path: '/frontend/api/authz/explorer/revoke' },
});

export const authzExplorerUiSlice = createSlice({
    name: 'frontend/authz_explorer_ui',
    extraInitial: {
        mode: 'people',
        userId: '',
        objectType: '',
        objectKey: '',
        pickerTypeFilter: '',
        grantTypeFilter: '',
        relationFilter: '',
        sourceFilter: '',
        peopleQuery: '',
        objectsQuery: '',
        whyOpen: false,
        whyUserId: '',
        whyObjectType: '',
        whyObjectKey: '',
        mobilePane: 'picker',
    },
    actions: {
        setMode: 'set_mode',
        selectUser: 'select_user',
        selectObject: 'select_object',
        setPickerTypeFilter: 'set_picker_type_filter',
        setGrantTypeFilter: 'set_grant_type_filter',
        setRelationFilter: 'set_relation_filter',
        setSourceFilter: 'set_source_filter',
        setPeopleQuery: 'set_people_query',
        setObjectsQuery: 'set_objects_query',
        openWhy: 'open_why',
        closeWhy: 'close_why',
        setMobilePane: 'set_mobile_pane',
        resetGrantFilters: 'reset_grant_filters',
        resetPickerSearch: 'reset_picker_search',
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.SET_MODE) {
            const mode = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).mode;
            if (mode !== 'people' && mode !== 'objects') {
                throw new Error('authzExplorerUiSlice.setMode: mode must be people|objects');
            }
            return { ...state, mode, whyOpen: false, mobilePane: 'picker' };
        }
        if (event.type === events.SELECT_USER) {
            const userId = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).userId;
            if (typeof userId !== 'string' || userId.length === 0) {
                throw new Error('authzExplorerUiSlice.selectUser: userId required');
            }
            return {
                ...state,
                mode: 'people',
                userId,
                objectType: '',
                objectKey: '',
                whyOpen: false,
                mobilePane: 'detail',
            };
        }
        if (event.type === events.SELECT_OBJECT) {
            const objectType = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).objectType;
            const objectKey = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).objectKey;
            if (typeof objectType !== 'string' || objectType.length === 0) {
                throw new Error('authzExplorerUiSlice.selectObject: objectType required');
            }
            if (typeof objectKey !== 'string' || objectKey.length === 0) {
                throw new Error('authzExplorerUiSlice.selectObject: objectKey required');
            }
            return {
                ...state,
                mode: 'objects',
                objectType,
                objectKey,
                whyOpen: false,
                mobilePane: 'detail',
            };
        }
        if (event.type === events.SET_PICKER_TYPE_FILTER) {
            const pickerTypeFilter = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).pickerTypeFilter;
            if (typeof pickerTypeFilter !== 'string') {
                throw new Error('authzExplorerUiSlice.setPickerTypeFilter: pickerTypeFilter string required');
            }
            return { ...state, pickerTypeFilter };
        }
        if (event.type === events.SET_GRANT_TYPE_FILTER) {
            const grantTypeFilter = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).grantTypeFilter;
            if (typeof grantTypeFilter !== 'string') {
                throw new Error('authzExplorerUiSlice.setGrantTypeFilter: grantTypeFilter string required');
            }
            return { ...state, grantTypeFilter };
        }
        if (event.type === events.SET_RELATION_FILTER) {
            const relationFilter = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).relationFilter;
            if (typeof relationFilter !== 'string') {
                throw new Error('authzExplorerUiSlice.setRelationFilter: relationFilter string required');
            }
            return { ...state, relationFilter };
        }
        if (event.type === events.SET_SOURCE_FILTER) {
            const sourceFilter = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).sourceFilter;
            if (typeof sourceFilter !== 'string') {
                throw new Error('authzExplorerUiSlice.setSourceFilter: sourceFilter string required');
            }
            return { ...state, sourceFilter };
        }
        if (event.type === events.SET_PEOPLE_QUERY) {
            const peopleQuery = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).peopleQuery;
            if (typeof peopleQuery !== 'string') {
                throw new Error('authzExplorerUiSlice.setPeopleQuery: peopleQuery string required');
            }
            return { ...state, peopleQuery };
        }
        if (event.type === events.SET_OBJECTS_QUERY) {
            const objectsQuery = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).objectsQuery;
            if (typeof objectsQuery !== 'string') {
                throw new Error('authzExplorerUiSlice.setObjectsQuery: objectsQuery string required');
            }
            return { ...state, objectsQuery };
        }
        if (event.type === events.OPEN_WHY) {
            const userId = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).userId;
            const objectType = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).objectType;
            const objectKey = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).objectKey;
            if (typeof userId !== 'string' || userId.length === 0) {
                throw new Error('authzExplorerUiSlice.openWhy: userId required');
            }
            if (typeof objectType !== 'string' || objectType.length === 0) {
                throw new Error('authzExplorerUiSlice.openWhy: objectType required');
            }
            if (typeof objectKey !== 'string' || objectKey.length === 0) {
                throw new Error('authzExplorerUiSlice.openWhy: objectKey required');
            }
            return {
                ...state,
                whyOpen: true,
                whyUserId: userId,
                whyObjectType: objectType,
                whyObjectKey: objectKey,
            };
        }
        if (event.type === events.CLOSE_WHY) {
            return {
                ...state,
                whyOpen: false,
                whyUserId: '',
                whyObjectType: '',
                whyObjectKey: '',
            };
        }
        if (event.type === events.SET_MOBILE_PANE) {
            const mobilePane = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).mobilePane;
            if (mobilePane !== 'picker' && mobilePane !== 'detail') {
                throw new Error('authzExplorerUiSlice.setMobilePane: picker|detail');
            }
            return { ...state, mobilePane };
        }
        if (event.type === events.RESET_GRANT_FILTERS) {
            return {
                ...state,
                grantTypeFilter: '',
                relationFilter: '',
                sourceFilter: '',
            };
        }
        if (event.type === events.RESET_PICKER_SEARCH) {
            return {
                ...state,
                pickerTypeFilter: '',
                peopleQuery: '',
                objectsQuery: '',
            };
        }
        return state;
    },
});
