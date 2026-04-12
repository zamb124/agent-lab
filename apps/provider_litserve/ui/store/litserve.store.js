import { BaseStore } from '@platform/lib/store/BaseStore.js';

const baseStore = new BaseStore(
    'litserve',
    {
        ui: {
            currentView: 'models',
        },
    },
    {
        persist: true,
        devtools: true,
        partialize: (state) => ({
            ui: {
                currentView: state.ui.currentView,
            },
        }),
    },
);

export const LitserveStore = {
    get state() {
        return baseStore.state;
    },

    subscribe(callback) {
        return baseStore.subscribe(callback);
    },

    setCurrentView(view) {
        baseStore.setState((state) => ({
            ui: {
                ...state.ui,
                currentView: view,
            },
        }));
    },
};
