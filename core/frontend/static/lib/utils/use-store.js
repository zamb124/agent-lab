/**
 * Reactive Controller для интеграции Zustand Store с Lit компонентами
 * 
 * Store регистрируется глобально через window.__PLATFORM_STORE__
 * в PlatformApp.initServices()
 */

class StoreController {
    constructor(host, selector) {
        this.host = host;
        this.selector = selector;
        this.unsubscribe = null;
        this.previousValue = undefined;
        host.addController(this);
    }

    hostConnected() {
        const Store = window.__PLATFORM_STORE__;
        
        if (!Store) {
            console.error('[StoreController] Store not registered');
            return;
        }
        
        this.unsubscribe = Store.subscribe(() => {
            const newValue = this.selector(Store.state);
            
            if (!this._shallowEqual(this.previousValue, newValue)) {
                this.previousValue = newValue;
                this.host.requestUpdate();
            }
        });
        
        this.previousValue = this.selector(Store.state);
    }

    hostDisconnected() {
        this.unsubscribe?.();
        this.unsubscribe = null;
    }

    get value() {
        const Store = window.__PLATFORM_STORE__;
        if (!Store) return undefined;
        return this.selector(Store.state);
    }

    _shallowEqual(a, b) {
        if (a === b) return true;
        if (!a || !b) return false;
        if (typeof a !== 'object' || typeof b !== 'object') return a === b;
        
        const keysA = Object.keys(a);
        const keysB = Object.keys(b);
        
        if (keysA.length !== keysB.length) return false;
        
        return keysA.every(key => a[key] === b[key]);
    }
}

/**
 * Хелпер для подписки на Store в компонентах
 * 
 * Использование:
 * this.state = this.use(s => ({
 *     items: s.entities.list,
 *     loading: s.entities.loading,
 * }));
 * 
 * const { items, loading } = this.state.value;
 */
export function use(host, selector) {
    return new StoreController(host, selector);
}
