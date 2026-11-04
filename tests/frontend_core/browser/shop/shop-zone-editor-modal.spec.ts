/**
 * shop-zone-editor-modal — полноэкранный редактор зоны на Leaflet + Geoman.
 *
 * Реальный браузер: настоящий Leaflet и настоящий Geoman (оба динамических
 * import резолвятся сборкой). Рисование идёт через боевой путь Geoman —
 * enableDraw('Polygon') → click-события карты → pm:create → слой принят
 * редактором. Применение отдаёт GeoJSON в onApply и закрывает модалку.
 */

import { fixture, html, expect, elementUpdated, aTimeout, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import {
    shopShopsResource,
    shopGeocodeOp,
} from '../../../../apps/shop/ui/events/resources/shop.resource.js';
import '@platform/lib/components/platform-modal-stack.js';
import '../../../../apps/shop/ui/modals/shop-zone-editor-modal.js';

const FACTORIES = [shopShopsResource, shopGeocodeOp];
const TAG = 'shop-zone-editor-modal';

const ZONE = {
    type: 'Polygon',
    coordinates: [
        [
            [37.5, 55.7],
            [37.7, 55.7],
            [37.7, 55.8],
            [37.5, 55.8],
            [37.5, 55.7],
        ],
    ],
};

type PmMap = {
    _loaded: boolean;
    pm: {
        enableDraw(shape: string, options?: Record<string, unknown>): void;
        disableDraw(): void;
        globalDrawModeEnabled(): boolean;
    };
    fire(type: string, ev: unknown): void;
};

type TestEl = HTMLElement & {
    shadowRoot: ShadowRoot;
    zone: Record<string, unknown> | null;
    address: string;
    shopId: string;
    onApply: ((zone: Record<string, unknown>) => void) | null;
    _map: PmMap | null;
    _polygon: {
        getLatLngs(): Array<Array<{ lat: number; lng: number }>>;
        pm: { enabled(): boolean; hasSelfIntersection(): boolean };
    } | null;
    _drawing: boolean;
    _mapError: boolean;
    _points: number;
    _areaM2: number;
    _perimM: number;
    _selfIntersect: boolean;
    _hint: string;
    open: boolean;
    close(): void;
    _retryMap(): void;
    _updateHint(): void;
    _tiles: { fire(t: string, ev?: unknown): void; remove(): void } | null;
};

async function seedI18n() {
    // Сначала ждём settle штатного i18n-эффекта: bootstrap диспатчит
    // I18N_LOCALE_REQUESTED → middleware отдаёт platform-бандл →
    // I18N_LOCALE_LOADED/CHANGED. Без ожидания settle эффект перетирает
    // locale и translations уже после сидирования — гонка.
    const bus = getPlatformBus();
    await waitUntil(
        () => {
            const i18n = bus.getState().i18n;
            if (i18n.loading) return false;
            const bundle = i18n.translations[i18n.locale];
            return Boolean(bundle && typeof bundle === 'object' && 'platform' in bundle);
        },
        'i18n bootstrap settled',
        { timeout: 15_000 },
    );
    const response = await fetch('/core/i18n/generated/ru.json');
    if (!response.ok) throw new Error(`seedI18n: ${response.status}`);
    const bundle = (await response.json()) as { shop: Record<string, unknown> };
    const prev = bus.getState().i18n.translations.ru;
    bus.dispatch(CoreEvents.I18N_LOCALE_LOADED, { locale: 'ru', bundle: { ...prev, shop: bundle.shop } });
    bus.dispatch(CoreEvents.I18N_LOCALE_CHANGED, { locale: 'ru' });
}

async function openModal(props: Record<string, unknown>): Promise<TestEl> {
    const stack = await fixture<HTMLElement>(html`<platform-modal-stack></platform-modal-stack>`);
    getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'shop.zone_editor', props });
    await elementUpdated(stack);
    const modal = [...document.querySelectorAll<TestEl>(TAG)].at(-1);
    expect(modal, 'модалка смонтирована').to.exist;
    return modal!;
}

async function mapReady(el: TestEl): Promise<void> {
    // Leaflet + Geoman грузятся динамическими import'ами — ждём реальный init.
    for (let i = 0; i < 100 && !el._map?._loaded; i++) await aTimeout(30);
    expect(el._map, 'карта редактора инициализирована').to.exist;
    expect(el._map!.pm, 'geoman активен на карте').to.exist;
}

function ztool(el: TestEl, text: string): HTMLButtonElement {
    const found = [...el.shadowRoot.querySelectorAll<HTMLButtonElement>('.ztool')].find((b) =>
        b.textContent!.includes(text),
    );
    expect(found, `кнопка «${text}» в панели`).to.exist;
    return found!;
}

function applyBtn(el: TestEl): HTMLElement {
    const found = [...el.shadowRoot.querySelectorAll<HTMLElement>('platform-button')].find((b) =>
        b.textContent!.includes('Применить'),
    );
    expect(found, 'кнопка «Применить»').to.exist;
    return found!;
}

async function clickMap(el: TestEl, lat: number, lng: number): Promise<void> {
    el._map!.fire('click', { latlng: { lat, lng } });
    await aTimeout(20);
}

describe('shop-zone-editor-modal', function () {
    this.timeout(60_000);

    beforeEach(async () => {
        resetPlatformState();
        setDefaultI18nNamespace('shop');
        bootstrapTestBus({ factories: FACTORIES });
        await seedI18n();
    });

    it('открытие без зоны → карта с geoman, пустые метрики, «Применить» активна', async () => {
        const applied: Array<Record<string, unknown>> = [];
        const modal = await openModal({
            zone: {},
            address: '',
            shopId: 'shop_test',
            onApply: (z: Record<string, unknown>) => applied.push(z),
        });
        await mapReady(modal);
        await elementUpdated(modal);
        // leaflet.css/geoman.css обязаны жить в shadow root: стили из head
        // не проходят сквозь shadow boundary — без них тайлы «пазлом».
        const links = [...modal.shadowRoot.querySelectorAll('link[rel="stylesheet"]')].map((l) =>
            (l as HTMLLinkElement).href,
        );
        expect(links.some((h) => h.includes('leaflet.css')), 'leaflet.css в shadow root').to.equal(true);
        expect(links.some((h) => h.includes('geoman')), 'geoman css в shadow root').to.equal(true);
        const tile = modal.shadowRoot.querySelector<HTMLElement>('.leaflet-tile');
        expect(tile, 'тайл загружен').to.exist;
        expect(getComputedStyle(tile!).position, 'тайл позиционируется абсолютно').to.equal('absolute');
        expect(modal._polygon).to.equal(null);
        expect(modal._points).to.equal(0);
        expect(modal.shadowRoot.querySelector('.ztools'), 'панель инструментов').to.exist;
        expect(modal.shadowRoot.querySelector('.zstats')).to.equal(null);
        applyBtn(modal).click();
        await aTimeout(30);
        expect(applied.length).to.equal(1);
        expect(applied[0]).to.deep.equal({});
    });

    it('существующая зона → полигон с pm.enable + метрики площади/периметра/точек', async () => {
        const modal = await openModal({ zone: ZONE, address: '', shopId: 'shop_test', onApply: null });
        await mapReady(modal);
        await elementUpdated(modal);
        const poly = modal._polygon;
        expect(poly, 'полигон на карте').to.exist;
        expect(poly!.pm.enabled(), 'geoman edit-режим включён').to.equal(true);
        expect(modal._points).to.equal(4); // Leaflet хранит кольцо без дубля замыкающей точки
        expect(modal._areaM2, 'площадь > 0').to.be.greaterThan(0);
        expect(modal._perimM, 'периметр > 0').to.be.greaterThan(0);
        const stats = modal.shadowRoot.querySelector('.zstats');
        expect(stats, 'панель метрик').to.exist;
        expect(stats!.textContent).to.include('км²');
    });

    it('рисование через Geoman: enableDraw → 3 клика → dblclick → pm:create → полигон', async () => {
        const applied: Array<Record<string, unknown>> = [];
        const modal = await openModal({
            zone: {},
            address: '',
            shopId: 'shop_test',
            onApply: (z: Record<string, unknown>) => applied.push(z),
        });
        await mapReady(modal);
        ztool(modal, 'Рисовать зону').click();
        await elementUpdated(modal);
        expect(modal._drawing).to.equal(true);
        expect(modal._map!.pm.globalDrawModeEnabled(), 'geoman draw-режим').to.equal(true);

        await clickMap(modal, 55.7, 37.5);
        await clickMap(modal, 55.7, 37.7);
        await clickMap(modal, 55.8, 37.6);
        modal._map!.fire('dblclick', { latlng: { lat: 55.8, lng: 37.6 } });
        await aTimeout(80);

        expect(modal._drawing).to.equal(false);
        const poly = modal._polygon;
        expect(poly, 'полигон создан Geoman').to.exist;
        expect(modal._points, 'вершин на слое').to.be.greaterThanOrEqual(3);
        expect(poly!.pm.enabled(), 'свежий слой в edit-режиме').to.equal(true);

        applyBtn(modal).click();
        await aTimeout(30);
        expect(applied.length).to.equal(1);
        const zone = applied[0]! as { type: string; coordinates: number[][][] };
        expect(zone.type).to.equal('Polygon');
        const ring = zone.coordinates[0]!;
        expect(ring[0]).to.deep.equal(ring[ring.length - 1]);
        expect(ring[0]).to.deep.equal([37.5, 55.7]); // GeoJSON [lng, lat]
    });

    it('«Очистить» удаляет полигон; «Применить» отдаёт {} и модалка закрывается', async () => {
        const applied: Array<Record<string, unknown>> = [];
        const modal = await openModal({
            zone: ZONE,
            address: '',
            shopId: 'shop_test',
            onApply: (z: Record<string, unknown>) => applied.push(z),
        });
        await mapReady(modal);
        await elementUpdated(modal);
        expect(modal._polygon).to.exist;

        ztool(modal, 'Очистить').click();
        await elementUpdated(modal);
        expect(modal._polygon).to.equal(null);
        expect(modal._points).to.equal(0);

        const closes: unknown[] = [];
        getPlatformBus().subscribeType(CoreEvents.UI_MODAL_CLOSE, (e) => closes.push(e));
        applyBtn(modal).click();
        await aTimeout(30);
        expect(applied[0]).to.deep.equal({});
        expect(closes.length, 'модалка закрыта после применения').to.equal(1);
    });

    it('«Вписать зону» → fitBounds; «Найти магазин на карте» → geocode op', async () => {
        const modal = await openModal({
            zone: ZONE,
            address: 'Москва, Тверская 1',
            shopId: 'shop_test',
            onApply: null,
        });
        await mapReady(modal);
        await elementUpdated(modal);
        ztool(modal, 'Вписать зону').click();
        await aTimeout(50); // fitBounds отрабатывает без ошибок

        const events: Array<{ type: string; payload: unknown }> = [];
        getPlatformBus().subscribeType(shopGeocodeOp.events.REQUESTED, (event) =>
            events.push(event),
        );
        ztool(modal, 'Найти магазин на карте').click();
        await aTimeout(50);
        const requested = events.find((e) => e.type === shopGeocodeOp.events.REQUESTED);
        expect(requested, 'geocode op запрошен').to.exist;
        expect((requested!.payload as Record<string, unknown>)['shop_id']).to.equal('shop_test');
    });

    it('tileerror → error-state + «Повторить» пересоздаёт tile-слой', async () => {
        const modal = await openModal({ zone: ZONE, address: '', shopId: 'shop_test', onApply: null });
        await mapReady(modal);
        await elementUpdated(modal);
        const tiles = modal._tiles;
        expect(tiles, 'tile-слой поднят').to.exist;

        tiles!.fire('tileerror', { coords: { x: 0, y: 0, z: 1 } });
        await elementUpdated(modal);
        expect(modal._mapError).to.equal(true);
        expect(modal.shadowRoot.querySelector('.zerror'), 'error-overlay').to.exist;
        const apply = applyBtn(modal) as HTMLElement & { disabled: boolean };
        expect(apply.disabled, '«Применить» заблокирована при ошибке карты').to.equal(true);

        const retry = [...modal.shadowRoot.querySelectorAll('platform-button')].find((b) =>
            b.textContent!.includes('Повторить'),
        ) as HTMLElement | undefined;
        expect(retry, 'кнопка «Повторить»').to.exist;
        retry!.click();
        await aTimeout(50);
        await elementUpdated(modal);
        expect(modal._mapError).to.equal(false);
        expect(modal.shadowRoot.querySelector('.zerror')).to.equal(null);
    });

    it('hasSelfIntersection → «Применить» заблокирована и warn-хинт', async () => {
        const modal = await openModal({ zone: ZONE, address: '', shopId: 'shop_test', onApply: null });
        await mapReady(modal);
        await elementUpdated(modal);
        // Боевой путь: Geoman сам не даст сделать self-intersection (allowSelfIntersection:false),
        // но hasSelfIntersection перечитывается на каждом событии — проверяем реакцию.
        modal._selfIntersect = true;
        modal._updateHint();
        await elementUpdated(modal);
        const apply = applyBtn(modal) as HTMLElement & { disabled: boolean };
        expect(apply.disabled).to.equal(true);
        const hint = modal.shadowRoot.querySelector('.zhint.warn');
        expect(hint, 'warn-хинт про самопересечение').to.exist;
    });

    it('«Отмена» закрывает модалку без onApply', async () => {
        const applied: unknown[] = [];
        const modal = await openModal({
            zone: ZONE,
            address: '',
            shopId: 'shop_test',
            onApply: () => applied.push(1),
        });
        await mapReady(modal);
        const closes: unknown[] = [];
        getPlatformBus().subscribeType(CoreEvents.UI_MODAL_CLOSE, (e) => closes.push(e));
        const cancel = [...modal.shadowRoot.querySelectorAll('platform-button')].find((b) =>
            b.textContent!.includes('Отмена'),
        ) as HTMLElement | undefined;
        expect(cancel, 'кнопка «Отмена»').to.exist;
        cancel!.click();
        await aTimeout(30);
        expect(applied.length).to.equal(0);
        expect(closes.length).to.equal(1);
    });
});
