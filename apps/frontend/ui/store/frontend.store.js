/**
 * Frontend Store - Состояние фронтенд приложения
 * Доменная структура: entities, ui, user
 */
import { BaseStore } from '@platform/lib/store/BaseStore.js';

const baseStore = new BaseStore('frontend', {
    entities: {
        companies: [],
        currentCompanyId: null,
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

    setCurrentView(view) {
        baseStore.setState((s) => ({
            ui: { ...s.ui, currentView: view },
        }));
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

    setCurrentCompanyId(companyId) {
        baseStore.setState((s) => ({
            entities: { ...s.entities, currentCompanyId: companyId },
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
