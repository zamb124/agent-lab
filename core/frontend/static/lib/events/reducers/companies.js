/**
 * Companies slice.
 *
 * state.companies:
 *   list:        Array - my companies
 *   loading:     boolean
 *   error:       string|null
 *   slugChecks:  { [slug]: { available: boolean } }
 */

export const COMPANIES_EVENTS = Object.freeze({
    LOAD_REQUESTED:   'companies/list/load_requested',
    LOADED:           'companies/list/loaded',
    LOAD_FAILED:      'companies/list/load_failed',
    SLUG_CHECK_REQUESTED: 'companies/slug/check_requested',
    SLUG_CHECKED:         'companies/slug/checked',
    SLUG_CHECK_FAILED:    'companies/slug/check_failed',
    CREATE_REQUESTED: 'companies/company/create_requested',
    CREATED:          'companies/company/created',
    CREATE_FAILED:    'companies/company/create_failed',
});

export const initialCompaniesState = Object.freeze({
    list: [],
    loading: false,
    error: null,
    slugChecks: {},
});

export function companiesReducer(state = initialCompaniesState, event) {
    switch (event.type) {
        case COMPANIES_EVENTS.LOAD_REQUESTED:
            return { ...state, loading: true, error: null };
        case COMPANIES_EVENTS.LOADED: {
            if (!event.payload || !Array.isArray(event.payload.items)) {
                throw new Error(`${event.type}: payload.items must be an array`);
            }
            return { ...state, loading: false, list: event.payload.items };
        }
        case COMPANIES_EVENTS.LOAD_FAILED:
            return { ...state, loading: false, error: event.payload && event.payload.message };
        case COMPANIES_EVENTS.SLUG_CHECKED: {
            const slug = event.payload && event.payload.slug;
            const available = event.payload && event.payload.available;
            if (!slug) return state;
            return { ...state, slugChecks: { ...state.slugChecks, [slug]: { available: !!available } } };
        }
        case COMPANIES_EVENTS.CREATED: {
            const company = event.payload && event.payload.company;
            if (!company) return state;
            return { ...state, list: [...state.list, company] };
        }
        default:
            return state;
    }
}

export const companiesSlice = { reducer: companiesReducer, initial: initialCompaniesState };
