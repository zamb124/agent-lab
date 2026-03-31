/**
 * BaseStore - Обёртка над Zustand для создания Store
 * 
 * Предоставляет:
 * - Redux DevTools интеграцию
 * - Persist в localStorage (опционально)
 * - Deep merge для сохранения структуры при миграциях
 * - Единый API: state, subscribe, setState
 */
import { create, devtools, persist } from '../../assets/js/zustand-bundle.js';

export function deepMerge(target, source) {
    if (!source || typeof source !== 'object') return target;
    if (!target || typeof target !== 'object') return target;
    
    const result = { ...target };
    
    for (const key of Object.keys(target)) {
        if (key in source) {
            const targetVal = target[key];
            const sourceVal = source[key];
            
            // Если initial state имеет объект, а persisted - null, сохраняем структуру initial
            if (targetVal !== null && typeof targetVal === 'object' && sourceVal === null) {
                result[key] = targetVal;
            } else if (
                targetVal !== null &&
                sourceVal !== null &&
                typeof targetVal === 'object' &&
                typeof sourceVal === 'object' &&
                !Array.isArray(targetVal) &&
                !Array.isArray(sourceVal)
            ) {
                result[key] = deepMerge(targetVal, sourceVal);
            } else if (sourceVal !== undefined) {
                result[key] = sourceVal;
            }
        }
    }
    
    return result;
}

export class BaseStore {
    /**
     * @param {string} name - Имя store (для devtools и persist)
     * @param {Object} initialState - Начальное состояние
     * @param {Object} options - { persist, devtools, partialize, persistMerge }
     */
    constructor(name, initialState, options = {}) {
        this.name = name;
        this._initialState = initialState;
        this._options = {
            persist: false,
            devtools: true,
            partialize: null,
            persistMerge: null,
            ...options
        };
        
        let storeCreator = (set, get) => ({
            ...initialState,
            _set: set,
            _get: get,
        });

        if (this._options.persist) {
            const defaultMerge = (persistedState, currentState) => deepMerge(currentState, persistedState);
            const mergeFn = typeof this._options.persistMerge === 'function'
                ? this._options.persistMerge
                : defaultMerge;
            const persistConfig = {
                name: `${name}-store`,
                merge: mergeFn,
            };
            if (this._options.partialize) {
                persistConfig.partialize = this._options.partialize;
            }
            storeCreator = persist(storeCreator, persistConfig);
        }

        if (this._options.devtools) {
            storeCreator = devtools(storeCreator, { name });
        }

        this._store = create(storeCreator);
    }

    get state() {
        return this._store.getState();
    }

    subscribe(callback) {
        return this._store.subscribe(callback);
    }

    setState(updater) {
        const currentState = this._store.getState();
        
        if (typeof updater === 'function') {
            currentState._set(updater);
        } else {
            currentState._set((state) => ({ ...state, ...updater }));
        }
    }

    getStore() {
        return this._store;
    }
}
