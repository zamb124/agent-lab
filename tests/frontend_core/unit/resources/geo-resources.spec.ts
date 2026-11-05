/**
 * Geo-ресурсы в core: адресный справочник, маршруты, слои карты и реестр
 * покрытия — контракт WS-команд и REST-зеркал владельца geo, плюс reducer
 * видимости слоёв geoMapSlice.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    geoAddressSuggestOp,
    geoAddressNearestOp,
    geoAddressesInZoneOp,
} from '@platform/lib/events/resources/geo-addresses.resource.js';
import { geoRouteOp, geoIsochroneOp } from '@platform/lib/events/resources/geo-route.resource.js';
import {
    geoLayersOp,
    geoLayerFeaturesOp,
    geoMapSlice,
} from '@platform/lib/events/resources/geo-layers.resource.js';
import {
    geoRegionsResource,
    geoSourcesOp,
    geoStatsOp,
    geoCursorsOp,
    geoImportStatusOp,
    geoImportRunOp,
} from '@platform/lib/events/resources/geo-coverage.resource.js';
import { testEvent } from '../../helpers/bus-fixtures.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

type AnyAsyncOp = import('@platform/lib/events/factories/async-op.js').AsyncOpFactory;

beforeEach(() => resetFactories());
afterEach(() => resetFactories());

describe('geo addresses resource', () => {
    it('suggest/nearest/in_zone — silent WS-команды с REST-зеркалом', () => {
        const ops: Array<[typeof geoAddressSuggestOp, string, string, string]> = [
            [geoAddressSuggestOp, 'geo/addresses_suggest', 'geo/addresses/suggest_requested', '/geo/api/v1/addresses/suggest'],
            [geoAddressNearestOp, 'geo/addresses_nearest', 'geo/addresses/nearest_requested', '/geo/api/v1/addresses/nearest'],
            [geoAddressesInZoneOp, 'geo/addresses_in_zone', 'geo/addresses/in_zone_requested', '/geo/api/v1/addresses/in-zone'],
        ];
        for (const [op, name, commandType, path] of ops) {
            expect(op.name).toBe(name);
            expect(op.transport).toBe('ws');
            expect(op.commandType).toBe(commandType);
            expect(op.restMirror).toEqual({ method: 'POST', path });
        }
    });
});

describe('geo route resource', () => {
    it('route/isochrone — silent WS-команды с REST-зеркалом', () => {
        const ops: Array<[AnyAsyncOp, string, string]> = [
            [geoRouteOp, 'geo/route/calculate_requested', '/geo/api/v1/route/calculate'],
            [geoIsochroneOp, 'geo/route/isochrone_requested', '/geo/api/v1/route/isochrone'],
        ];
        for (const [op, commandType, path] of ops) {
            expect(op.transport).toBe('ws');
            expect(op.commandType).toBe(commandType);
            expect(op.restMirror).toEqual({ method: 'POST', path });
        }
    });
});

describe('geo layers resource', () => {
    it('реестр слоёв и фичи в рамке — silent WS-команды', () => {
        expect(geoLayersOp.commandType).toBe('geo/layers/list_requested');
        expect(geoLayersOp.restMirror).toEqual({ method: 'GET', path: '/geo/api/v1/layers' });
        expect(geoLayerFeaturesOp.commandType).toBe('geo/layers/features_requested');
        expect(geoLayerFeaturesOp.restMirror).toEqual({ method: 'POST', path: '/geo/api/v1/layers/features' });
    });

    it('geoMapSlice.toggle прячет и возвращает слой по имени', () => {
        const toggled = geoMapSlice.slice.reducer(geoMapSlice.slice.initial, testEvent('geo/map/toggle', { name: 'roads' }));
        expect(toggled.hidden).toEqual({ roads: true });
        const restored = geoMapSlice.slice.reducer(toggled, testEvent('geo/map/toggle', { name: 'roads' }));
        expect(restored.hidden).toEqual({});
    });

    it('geoMapSlice: чужое событие и пустое имя не меняют состояние / бросают', () => {
        const untouched = geoMapSlice.slice.reducer(geoMapSlice.slice.initial, testEvent('geo/other/event', { name: 'x' }));
        expect(untouched).toBe(geoMapSlice.slice.initial);
        expect(() => geoMapSlice.slice.reducer(geoMapSlice.slice.initial, testEvent('geo/map/toggle', { name: '' }))).toThrow(/payload\.name/);
    });
});

describe('geo coverage resource', () => {
    it('geo/regions — CRUD-коллекция по имени региона с REST-зеркалом', () => {
        expect(geoRegionsResource.name).toBe('geo/regions');
        expect(geoRegionsResource.transport).toBe('ws');
        expect(geoRegionsResource.baseUrl).toBe('/geo/api/v1/regions');
        expect(geoRegionsResource.idField).toBe('name');
    });

    it('одиночные опросы страницы «Источники» — silent WS-команды', () => {
        const ops: Array<[AnyAsyncOp, string, string, string]> = [
            [geoSourcesOp, 'geo/sources/list_requested', 'GET', '/geo/api/v1/sources'],
            [geoStatsOp, 'geo/stats/overview_requested', 'GET', '/geo/api/v1/stats/overview'],
            [geoCursorsOp, 'geo/cursors/list_requested', 'GET', '/geo/api/v1/cursors'],
            [geoImportStatusOp, 'geo/import/status_requested', 'GET', '/geo/api/v1/import/status'],
            [geoImportRunOp, 'geo/import/run_requested', 'POST', '/geo/api/v1/import/run'],
        ];
        for (const [op, commandType, method, path] of ops) {
            expect(op.transport).toBe('ws');
            expect(op.commandType).toBe(commandType);
            expect(op.restMirror).toEqual({ method, path });
        }
    });
});
