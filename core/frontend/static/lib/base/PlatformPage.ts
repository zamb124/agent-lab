/**
 * PlatformPage — базовый класс для страниц-маршрутов в event-driven канон.
 *
 * Удобные хелперы поверх PlatformElement: знание текущего маршрута,
 * `navigate(routeKey, params?, navigationOptions?)` через events (как у PlatformElement).
 */

import { PlatformElement } from '../platform-element/index.js';
import type { SelectController } from '../events/select-controller.js';

interface RouteSelection {
    routeKey: string | null;
    params: Record<string, string>;
}

export class PlatformPage extends PlatformElement {
    _routeSelect: SelectController<RouteSelection>;

    constructor() {
        super();
        this._routeSelect = this.select((s) => {
            const router = s.router as { routeKey: string | null; params: Record<string, string> };
            return { routeKey: router.routeKey, params: router.params };
        });
    }

    get routeKey(): string | null {
        const value = this._routeSelect.value;
        return value ? value.routeKey : null;
    }

    get routeParams(): Record<string, string> {
        const value = this._routeSelect.value;
        return value ? (value.params || {}) : {};
    }

    override navigate(routeKey: string, params?: Record<string, string>, navigationOptions?: { search?: string; replace?: boolean }): void {
        super.navigate(routeKey, params, navigationOptions);
    }
}
