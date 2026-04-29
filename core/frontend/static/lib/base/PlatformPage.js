/**
 * PlatformPage — базовый класс для страниц-маршрутов в event-driven канон.
 *
 * Удобные хелперы поверх PlatformElement: знание текущего маршрута,
 * `navigate(routeKey, params?, navigationOptions?)` через events (как у PlatformElement).
 */

import { PlatformElement } from '../platform-element/index.js';

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

    navigate(routeKey, params, navigationOptions) {
        super.navigate(routeKey, params, navigationOptions);
    }
}
