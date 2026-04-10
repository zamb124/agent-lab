/**
 * Frontend Store - Состояние фронтенд приложения
 * Доменная структура: entities, ui, user
 */
import { BaseStore } from '@platform/lib/store/BaseStore.js';

const CONSOLE_VIEW_TO_PATH = new Map([
    ['dashboard', '/dashboard'],
    ['team', '/team'],
    ['api-keys', '/api-keys'],
    ['embed-configs', '/embed-configs'],
    ['billing', '/billing'],
    ['settings', '/settings'],
    ['scheduler-tasks', '/scheduler-tasks'],
    ['lead-requests', '/lead-requests'],
    ['platform-tracing', '/platform-tracing'],
    ['platform-billing', '/platform-billing'],
]);

const CONSOLE_PATH_TO_VIEW = new Map(
    [...CONSOLE_VIEW_TO_PATH.entries()].map(([viewName, urlPath]) => [urlPath, viewName]),
);

/**
 * @param {string} path
 * @returns {string | null}
 */
export function getConsoleViewForPath(path) {
    const direct = CONSOLE_PATH_TO_VIEW.get(path);
    if (direct) {
        return direct;
    }
    if (path === '/settings' || path.startsWith('/settings/')) {
        return 'settings';
    }
    return null;
}

/**
 * @param {string} view
 */
function pushConsolePathForView(view) {
    if (typeof window === 'undefined') {
        return;
    }
    const targetPath = CONSOLE_VIEW_TO_PATH.get(view);
    if (!targetPath) {
        return;
    }
    if (view === 'settings' && window.location.pathname.startsWith('/settings')) {
        return;
    }
    if (window.location.pathname === targetPath) {
        return;
    }
    window.history.pushState({ frontendConsoleView: view }, '', targetPath);
}

const baseStore = new BaseStore('frontend', {
    entities: {
        companies: [],
        activeCompanyId: null,
        team: {
            members: [],
            loading: false,
        },
        apiKeys: {
            keys: [],
            loading: false,
        },
        billing: {
            subscription: null,
            usage: null,
            loading: false,
        },
        payments: {
            history: [],
            loading: false,
        },
        services: {
            statuses: {},
            loading: false,
        },
        settings: {
            company: null,
            loading: false,
        },
        embed: {
            configs: [],
            loading: false,
        },
    },
    ui: {
        currentView: 'dashboard',
        globalLoading: false,
        globalError: null,
    },
    user: {
        data: null,
    },
}, {
    persist: true,
    devtools: true,
});

export const FrontendStore = {
    get state() {
        return baseStore.state;
    },

    subscribe(callback) {
        return baseStore.subscribe(callback);
    },

    // === UI ===

    /**
     * @param {string} view
     * @param {{ skipUrlSync?: boolean }} [options]
     */
    setCurrentView(view, options = {}) {
        const { skipUrlSync = false } = options;
        baseStore.setState((s) => ({
            ui: { ...s.ui, currentView: view },
        }));
        if (!skipUrlSync) {
            pushConsolePathForView(view);
        }
    },

    setGlobalLoading(loading) {
        baseStore.setState((s) => ({
            ui: { ...s.ui, globalLoading: loading },
        }));
    },

    setGlobalError(error) {
        baseStore.setState((s) => ({
            ui: { ...s.ui, globalError: error },
        }));
    },

    // === User ===

    setUser(user) {
        baseStore.setState((s) => ({
            user: { ...s.user, data: user },
        }));
    },

    // === Companies ===

    setCompanies(companies) {
        baseStore.setState((s) => ({
            entities: { ...s.entities, companies },
        }));
    },

    setActiveCompanyId(companyId) {
        baseStore.setState((s) => ({
            entities: { ...s.entities, activeCompanyId: companyId },
        }));
    },

    // === Team ===

    setTeamMembers(members) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                team: { ...s.entities.team, members, loading: false },
            },
        }));
    },

    setTeamLoading(loading) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                team: { ...s.entities.team, loading },
            },
        }));
    },

    // === API Keys ===

    setApiKeys(keys) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                apiKeys: { ...s.entities.apiKeys, keys, loading: false },
            },
        }));
    },

    setApiKeysLoading(loading) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                apiKeys: { ...s.entities.apiKeys, loading },
            },
        }));
    },

    // === Billing ===

    setBillingData(subscription, usage) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                billing: { subscription, usage, loading: false },
            },
        }));
    },

    setBillingLoading(loading) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                billing: { ...s.entities.billing, loading },
            },
        }));
    },

    setPaymentHistory(history) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                payments: { history, loading: false },
            },
        }));
    },

    setPaymentsLoading(loading) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                payments: { ...s.entities.payments, loading },
            },
        }));
    },

    // === Services Status ===

    setServicesStatus(statuses) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                services: { statuses, loading: false },
            },
        }));
    },

    setServicesLoading(loading) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                services: { ...s.entities.services, loading },
            },
        }));
    },

    // === Settings ===

    setCompanySettings(company) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                settings: { company, loading: false },
            },
        }));
    },

    setSettingsLoading(loading) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                settings: { ...s.entities.settings, loading },
            },
        }));
    },

    // === Embed ===

    setEmbedConfigs(configs) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                embed: { configs, loading: false },
            },
        }));
    },

    setEmbedLoading(loading) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                embed: { ...s.entities.embed, loading },
            },
        }));
    },
};
