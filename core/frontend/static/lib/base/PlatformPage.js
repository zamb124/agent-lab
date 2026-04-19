/**
 * PlatformPage — базовый класс для страниц-маршрутов в event-driven канон.
 *
 * Удобные хелперы поверх PlatformElement: знание текущего маршрута,
 * `navigate(routeKey, params)` через events.
 */

import { PlatformElement } from '../platform-element/index.js';
import { CoreEvents } from '../events/contract.js';

export class PlatformPage extends PlatformElement {
    constructor() {
        super();
        this._routeSelect = this.select((s) => ({ routeKey: s.router.routeKey, params: s.router.params }));
    }

    get routeKey() {
        return this._routeSelect && this._routeSelect.value ? this._routeSelect.value.routeKey : null;
    }

    get routeParams() {
        return this._routeSelect && this._routeSelect.value ? (this._routeSelect.value.params || {}) : {};
    }

    navigate(routeKey, params) {
        if (typeof routeKey !== 'string' || routeKey.length === 0) {
            throw new Error('PlatformPage.navigate: routeKey required');
        }
        this.dispatch(CoreEvents.ROUTER_NAVIGATE_REQUESTED, { routeKey, params: params || {} });
    }
}
