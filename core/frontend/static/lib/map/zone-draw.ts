/**
 * TerraDraw поверх PlatformMap для <platform-map draw="polygon">.
 *
 * Единая сборка редактора зон платформы: Select + Polygon режимы,
 * ValidateNotSelfIntersecting на draw и select, фирменная стилизация.
 * TerraDraw и адаптер импортируются lazy — бандл вырастает только у
 * потребителей draw-режима.
 */

import type { PlatformMap } from './basemap.js';
import type { Feature } from 'geojson';
import type { HexColor, GeoJSONStoreFeatures } from 'terra-draw';

export type TerraDrawModule = typeof import('terra-draw');
export type TerraDrawInstance = import('terra-draw').TerraDraw;
export type TerraDrawAdapterModule = typeof import('terra-draw-maplibre-gl-adapter');

export interface ZoneDrawOptions {
    accent?: string;
    maxPoints?: number;
}

export interface ZoneDraw {
    draw: TerraDrawInstance;
    validate: (feature: Feature) => boolean;
}

export async function createZoneDraw(
    map: PlatformMap,
    { accent = '#f2542d' }: ZoneDrawOptions = {},
): Promise<ZoneDraw> {
    const [td, adapterMod] = await Promise.all([
        import('terra-draw'),
        import('terra-draw-maplibre-gl-adapter'),
    ]);
    const color = accent as HexColor;
    const draw = new td.TerraDraw({
        adapter: new adapterMod.TerraDrawMapLibreGLAdapter({ map }),
        modes: [
            new td.TerraDrawSelectMode({
                flags: {
                    polygon: {
                        feature: {
                            draggable: true,
                            selfIntersectable: false,
                            validation: td.ValidateNotSelfIntersecting,
                            coordinates: {
                                snappable: true,
                                midpoints: { draggable: true },
                                draggable: true,
                                deletable: true,
                            },
                        },
                    },
                },
            }),
            new td.TerraDrawPolygonMode({
                editable: true,
                validation: td.ValidateNotSelfIntersecting,
                styles: {
                    fillColor: color,
                    fillOpacity: 0.12,
                    outlineColor: color,
                    outlineWidth: 2.5,
                    coordinatePointColor: color,
                    editedPointColor: '#155dfc' as HexColor,
                },
            }),
        ],
    });
    draw.start();
    draw.setMode('select');
    const validate = (feature: Feature): boolean =>
        td.ValidateNotSelfIntersecting(feature as unknown as GeoJSONStoreFeatures).valid;
    return { draw, validate };
}
