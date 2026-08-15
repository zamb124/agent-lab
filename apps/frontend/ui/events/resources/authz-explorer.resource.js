/**
 * Access Explorer — by-user / by-object / why / objects / revoke + UI slice.
 */
import { createAsyncOp, createSlice } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const authzExplorerByUserOp = createAsyncOp({
    name: 'frontend/authz_explorer_by_user',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/authz/explorer/by-user' },
    request: async ({ payload }) => {
        const userId = payload && payload.user_id;
        if (typeof userId !== 'string' || userId.length === 0) {
            throw new Error('authzExplorerByUserOp: user_id required');
        }
        return httpRequest({
            method: 'GET',
            url: '/frontend/api/authz/explorer/by-user',
            query: { user_id: userId },
        });
    },
});

export const authzExplorerByObjectOp = createAsyncOp({
    name: 'frontend/authz_explorer_by_object',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/authz/explorer/by-object' },
    request: async ({ payload }) => {
        const objectType = payload && payload.object_type;
        const objectKey = payload && payload.object_key;
        if (typeof objectType !== 'string' || objectType.length === 0) {
            throw new Error('authzExplorerByObjectOp: object_type required');
        }
        if (typeof objectKey !== 'string' || objectKey.length === 0) {
            throw new Error('authzExplorerByObjectOp: object_key required');
        }
        return httpRequest({
            method: 'GET',
            url: '/frontend/api/authz/explorer/by-object',
            query: { object_type: objectType, object_key: objectKey },
        });
    },
});

export const authzExplorerWhyOp = createAsyncOp({
    name: 'frontend/authz_explorer_why',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/authz/explorer/why' },
    request: async ({ payload }) => {
        const userId = payload && payload.user_id;
        const objectType = payload && payload.object_type;
        const objectKey = payload && payload.object_key;
        if (typeof userId !== 'string' || userId.length === 0) {
            throw new Error('authzExplorerWhyOp: user_id required');
        }
        if (typeof objectType !== 'string' || objectType.length === 0) {
            throw new Error('authzExplorerWhyOp: object_type required');
        }
        if (typeof objectKey !== 'string' || objectKey.length === 0) {
            throw new Error('authzExplorerWhyOp: object_key required');
        }
        return httpRequest({
            method: 'GET',
            url: '/frontend/api/authz/explorer/why',
            query: {
                user_id: userId,
                object_type: objectType,
                object_key: objectKey,
            },
        });
    },
});

export const authzExplorerObjectsOp = createAsyncOp({
    name: 'frontend/authz_explorer_objects',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/authz/explorer/objects' },
    request: async ({ payload }) => {
        const query = payload && typeof payload.q === 'string' ? payload.q : '';
        const objectType = payload && payload.object_type;
        const params = { q: query };
        if (typeof objectType === 'string' && objectType.length > 0) {
            params.object_type = objectType;
        }
        return httpRequest({
            method: 'GET',
            url: '/frontend/api/authz/explorer/objects',
            query: params,
        });
    },
});

export const authzExplorerRevokeOp = createAsyncOp({
    name: 'frontend/authz_explorer_revoke',
    successToastKey: 'frontend:access_page.toast_revoked',
    errorToastKey: 'frontend:access_page.err_revoke',
    restMirror: { method: 'POST', path: '/frontend/api/authz/explorer/revoke' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('authzExplorerRevokeOp: payload required');
        }
        return httpRequest({
            method: 'POST',
            url: '/frontend/api/authz/explorer/revoke',
            body: payload,
        });
    },
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
            const mode = event.payload && event.payload.mode;
            if (mode !== 'people' && mode !== 'objects') {
                throw new Error('authzExplorerUiSlice.setMode: mode must be people|objects');
            }
            return { ...state, mode, whyOpen: false, mobilePane: 'picker' };
        }
        if (event.type === events.SELECT_USER) {
            const userId = event.payload && event.payload.userId;
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
            const objectType = event.payload && event.payload.objectType;
            const objectKey = event.payload && event.payload.objectKey;
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
            const pickerTypeFilter = event.payload && event.payload.pickerTypeFilter;
            if (typeof pickerTypeFilter !== 'string') {
                throw new Error('authzExplorerUiSlice.setPickerTypeFilter: pickerTypeFilter string required');
            }
            return { ...state, pickerTypeFilter };
        }
        if (event.type === events.SET_GRANT_TYPE_FILTER) {
            const grantTypeFilter = event.payload && event.payload.grantTypeFilter;
            if (typeof grantTypeFilter !== 'string') {
                throw new Error('authzExplorerUiSlice.setGrantTypeFilter: grantTypeFilter string required');
            }
            return { ...state, grantTypeFilter };
        }
        if (event.type === events.SET_RELATION_FILTER) {
            const relationFilter = event.payload && event.payload.relationFilter;
            if (typeof relationFilter !== 'string') {
                throw new Error('authzExplorerUiSlice.setRelationFilter: relationFilter string required');
            }
            return { ...state, relationFilter };
        }
        if (event.type === events.SET_SOURCE_FILTER) {
            const sourceFilter = event.payload && event.payload.sourceFilter;
            if (typeof sourceFilter !== 'string') {
                throw new Error('authzExplorerUiSlice.setSourceFilter: sourceFilter string required');
            }
            return { ...state, sourceFilter };
        }
        if (event.type === events.SET_PEOPLE_QUERY) {
            const peopleQuery = event.payload && event.payload.peopleQuery;
            if (typeof peopleQuery !== 'string') {
                throw new Error('authzExplorerUiSlice.setPeopleQuery: peopleQuery string required');
            }
            return { ...state, peopleQuery };
        }
        if (event.type === events.SET_OBJECTS_QUERY) {
            const objectsQuery = event.payload && event.payload.objectsQuery;
            if (typeof objectsQuery !== 'string') {
                throw new Error('authzExplorerUiSlice.setObjectsQuery: objectsQuery string required');
            }
            return { ...state, objectsQuery };
        }
        if (event.type === events.OPEN_WHY) {
            const userId = event.payload && event.payload.userId;
            const objectType = event.payload && event.payload.objectType;
            const objectKey = event.payload && event.payload.objectKey;
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
            const mobilePane = event.payload && event.payload.mobilePane;
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
