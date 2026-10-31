/**
 * Pure cluster geometry for `<flow-ui-drawer>`.
 * Launcher + panel are one unit. No DOM.
 */

import { isPlainRecord } from '../../events/payload.js';

export interface DrawerViewport {
    width: number;
    height: number;
    margin: number;
    bottomInset?: number;
}

export interface StoredDrawerGeometry {
    launcherLeft: number;
    launcherTop: number;
    panelWidth: number;
    panelHeight: number;
}

export type PanelAlign = 'left' | 'right';
export type PanelPlacement = 'above' | 'below';

export interface PlacedDrawerGeometry extends StoredDrawerGeometry {
    panelLeft: number;
    panelTop: number;
    panelAlign: PanelAlign;
    panelPlacement: PanelPlacement;
}

export type LauncherPosition = 'bottom-left' | 'bottom-right';

export const LAUNCHER_SIZE_PX = 58;
export const PANEL_GAP_PX = 12;
export const DEFAULT_PANEL_WIDTH_PX = 430;
export const DEFAULT_PANEL_HEIGHT_PX = 720;
export const MIN_PANEL_WIDTH_PX = 280;
export const MIN_PANEL_HEIGHT_PX = 320;
export const DRAG_THRESHOLD_PX = 6;
export const MOBILE_MAX_WIDTH_PX = 520;
export const VIEWPORT_MARGIN_DESKTOP_PX = 22;
export const VIEWPORT_MARGIN_MOBILE_PX = 10;
export const LAUNCHER_NAV_GAP_PX = 8;

const STORED_KEYS = Object.freeze([
    'launcherLeft',
    'launcherTop',
    'panelWidth',
    'panelHeight',
]);

function requireFiniteNumber(value: unknown, label: string): number {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        throw new Error(`flow-ui-drawer geometry: ${label} must be a finite number`);
    }
    return value;
}

function clampNumber(value: number, min: number, max: number): number {
    requireFiniteNumber(value, 'clamp value');
    requireFiniteNumber(min, 'clamp min');
    requireFiniteNumber(max, 'clamp max');
    if (min > max) {
        throw new Error('flow-ui-drawer geometry: clamp min must be <= max');
    }
    if (value < min) return min;
    if (value > max) return max;
    return value;
}

function isDrawerViewport(value: unknown): value is DrawerViewport {
    if (!isPlainRecord(value)) return false;
    const width = value.width;
    const height = value.height;
    const margin = value.margin;
    return typeof width === 'number' && Number.isFinite(width) && width > 0
        && typeof height === 'number' && Number.isFinite(height) && height > 0
        && typeof margin === 'number' && Number.isFinite(margin) && margin >= 0;
}

export function assertViewport(viewport: unknown): asserts viewport is DrawerViewport {
    if (!isPlainRecord(viewport)) {
        throw new Error('flow-ui-drawer geometry: viewport is required');
    }
    const width = requireFiniteNumber(viewport.width, 'viewport.width');
    const height = requireFiniteNumber(viewport.height, 'viewport.height');
    const margin = requireFiniteNumber(viewport.margin, 'viewport.margin');
    if (width <= 0) {
        throw new Error('flow-ui-drawer geometry: viewport.width must be > 0');
    }
    if (height <= 0) {
        throw new Error('flow-ui-drawer geometry: viewport.height must be > 0');
    }
    if (margin < 0) {
        throw new Error('flow-ui-drawer geometry: viewport.margin must be >= 0');
    }
    if (!isDrawerViewport(viewport)) {
        throw new Error('flow-ui-drawer geometry: viewport is required');
    }
}

export function gesturesAllowed(viewport: DrawerViewport): boolean {
    assertViewport(viewport);
    return viewport.width > MOBILE_MAX_WIDTH_PX;
}

export function parseStoredGeometry(raw: unknown): StoredDrawerGeometry | null {
    if (raw === null || raw === undefined) {
        return null;
    }
    if (!isPlainRecord(raw)) {
        throw new Error('flow-ui-drawer geometry: stored value must be an object');
    }
    const present = STORED_KEYS.filter((key) => Object.prototype.hasOwnProperty.call(raw, key));
    if (present.length === 0) {
        return null;
    }
    if (present.length !== STORED_KEYS.length) {
        throw new Error(
            `flow-ui-drawer geometry: expected ${STORED_KEYS.join(', ')}`,
        );
    }
    return Object.freeze({
        launcherLeft: requireFiniteNumber(raw.launcherLeft, 'launcherLeft'),
        launcherTop: requireFiniteNumber(raw.launcherTop, 'launcherTop'),
        panelWidth: requireFiniteNumber(raw.panelWidth, 'panelWidth'),
        panelHeight: requireFiniteNumber(raw.panelHeight, 'panelHeight'),
    });
}

export function toStoredGeometry(cluster: unknown): StoredDrawerGeometry {
    if (!isPlainRecord(cluster)) {
        throw new Error('flow-ui-drawer geometry: cluster is required');
    }
    const stored = parseStoredGeometry({
        launcherLeft: cluster.launcherLeft,
        launcherTop: cluster.launcherTop,
        panelWidth: cluster.panelWidth,
        panelHeight: cluster.panelHeight,
    });
    if (stored === null) {
        throw new Error('flow-ui-drawer geometry: cluster is missing stored fields');
    }
    return stored;
}

function panelSizeLimits(viewport: DrawerViewport): { minWidth: number; maxWidth: number; minHeight: number; maxHeight: number } {
    const maxWidth = Math.max(1, viewport.width - viewport.margin * 2);
    const maxHeight = Math.max(
        1,
        viewport.height - viewport.margin * 2 - LAUNCHER_SIZE_PX - PANEL_GAP_PX,
    );
    return {
        minWidth: Math.min(MIN_PANEL_WIDTH_PX, maxWidth),
        maxWidth,
        minHeight: Math.min(MIN_PANEL_HEIGHT_PX, maxHeight),
        maxHeight,
    };
}

export function createDefaultGeometry(position: LauncherPosition, viewport: DrawerViewport): StoredDrawerGeometry {
    if (position !== 'bottom-left' && position !== 'bottom-right') {
        throw new Error(
            `flow-ui-drawer geometry: invalid position ${JSON.stringify(position)}`,
        );
    }
    assertViewport(viewport);
    const limits = panelSizeLimits(viewport);
    const panelWidth = Math.min(DEFAULT_PANEL_WIDTH_PX, limits.maxWidth);
    const panelHeight = Math.min(DEFAULT_PANEL_HEIGHT_PX, limits.maxHeight);
    const bottomInset = viewport.bottomInset ?? 0;
    const launcherTop = viewport.height - viewport.margin - bottomInset - LAUNCHER_SIZE_PX;
    const launcherLeft = position === 'bottom-left'
        ? viewport.margin
        : viewport.width - viewport.margin - LAUNCHER_SIZE_PX;
    return Object.freeze({
        launcherLeft,
        launcherTop,
        panelWidth,
        panelHeight,
    });
}

function panelAlignFor(geometry: StoredDrawerGeometry, viewport: DrawerViewport): PanelAlign {
    const launcherCenter = geometry.launcherLeft + LAUNCHER_SIZE_PX / 2;
    return launcherCenter >= viewport.width / 2 ? 'right' : 'left';
}

function panelLeftFor(geometry: StoredDrawerGeometry, align: PanelAlign): number {
    if (align === 'right') {
        return geometry.launcherLeft + LAUNCHER_SIZE_PX - geometry.panelWidth;
    }
    return geometry.launcherLeft;
}

export function placePanel(geometry: StoredDrawerGeometry, viewport: DrawerViewport): PlacedDrawerGeometry {
    assertViewport(viewport);
    const stored = toStoredGeometry(geometry);
    let panelAlign = panelAlignFor(stored, viewport);
    let panelLeft = panelLeftFor(stored, panelAlign);
    if (panelAlign === 'right' && panelLeft < viewport.margin) {
        const flippedLeft = panelLeftFor(stored, 'left');
        if (flippedLeft + stored.panelWidth <= viewport.width - viewport.margin) {
            panelAlign = 'left';
            panelLeft = flippedLeft;
        }
    } else if (
        panelAlign === 'left'
        && panelLeft + stored.panelWidth > viewport.width - viewport.margin
    ) {
        const flippedLeft = panelLeftFor(stored, 'right');
        if (flippedLeft >= viewport.margin) {
            panelAlign = 'right';
            panelLeft = flippedLeft;
        }
    }

    let panelTop = stored.launcherTop - PANEL_GAP_PX - stored.panelHeight;
    let panelPlacement: PanelPlacement = 'above';
    if (panelTop < viewport.margin) {
        const belowTop = stored.launcherTop + LAUNCHER_SIZE_PX + PANEL_GAP_PX;
        if (belowTop + stored.panelHeight <= viewport.height - viewport.margin - (viewport.bottomInset ?? 0)) {
            panelTop = belowTop;
            panelPlacement = 'below';
        }
    }

    return Object.freeze({
        launcherLeft: stored.launcherLeft,
        launcherTop: stored.launcherTop,
        panelWidth: stored.panelWidth,
        panelHeight: stored.panelHeight,
        panelLeft,
        panelTop,
        panelAlign,
        panelPlacement,
    });
}

export function clampCluster(geometry: StoredDrawerGeometry, viewport: DrawerViewport): PlacedDrawerGeometry {
    assertViewport(viewport);
    const stored = toStoredGeometry(geometry);
    const limits = panelSizeLimits(viewport);
    const panelWidth = clampNumber(stored.panelWidth, limits.minWidth, limits.maxWidth);
    const panelHeight = clampNumber(stored.panelHeight, limits.minHeight, limits.maxHeight);
    const bottomInset = viewport.bottomInset ?? 0;
    const maxLauncherLeft = viewport.width - viewport.margin - LAUNCHER_SIZE_PX;
    const maxLauncherTop = viewport.height - viewport.margin - bottomInset - LAUNCHER_SIZE_PX;
    const launcherLeft = clampNumber(
        stored.launcherLeft,
        viewport.margin,
        Math.max(viewport.margin, maxLauncherLeft),
    );
    const launcherTop = clampNumber(
        stored.launcherTop,
        viewport.margin,
        Math.max(viewport.margin, maxLauncherTop),
    );
    const placed = placePanel(
        {
            launcherLeft,
            launcherTop,
            panelWidth,
            panelHeight,
        },
        viewport,
    );
    const left = Math.min(placed.panelLeft, placed.launcherLeft);
    const top = Math.min(placed.panelTop, placed.launcherTop);
    const right = Math.max(
        placed.panelLeft + placed.panelWidth,
        placed.launcherLeft + LAUNCHER_SIZE_PX,
    );
    const bottom = Math.max(
        placed.panelTop + placed.panelHeight,
        placed.launcherTop + LAUNCHER_SIZE_PX,
    );
    let dx = 0;
    let dy = 0;
    if (left < viewport.margin) {
        dx = viewport.margin - left;
    }
    if (right + dx > viewport.width - viewport.margin) {
        dx = viewport.width - viewport.margin - right;
    }
    if (top < viewport.margin) {
        dy = viewport.margin - top;
    }
    if (bottom + dy > viewport.height - viewport.margin - bottomInset) {
        dy = viewport.height - viewport.margin - bottomInset - bottom;
    }
    return Object.freeze({
        launcherLeft: placed.launcherLeft + dx,
        launcherTop: placed.launcherTop + dy,
        panelWidth: placed.panelWidth,
        panelHeight: placed.panelHeight,
        panelLeft: placed.panelLeft + dx,
        panelTop: placed.panelTop + dy,
        panelAlign: placed.panelAlign,
        panelPlacement: placed.panelPlacement,
    });
}

export function moveCluster(geometry: StoredDrawerGeometry, dx: number, dy: number, viewport: DrawerViewport): PlacedDrawerGeometry {
    requireFiniteNumber(dx, 'dx');
    requireFiniteNumber(dy, 'dy');
    const stored = toStoredGeometry(geometry);
    return clampCluster(
        {
            launcherLeft: stored.launcherLeft + dx,
            launcherTop: stored.launcherTop + dy,
            panelWidth: stored.panelWidth,
            panelHeight: stored.panelHeight,
        },
        viewport,
    );
}

function attachLauncherToPanel(panelLeft: number, panelTop: number, panelWidth: number, panelHeight: number, panelAlign: PanelAlign): { launcherLeft: number; launcherTop: number } {
    const launcherLeft = panelAlign === 'right'
        ? panelLeft + panelWidth - LAUNCHER_SIZE_PX
        : panelLeft;
    const launcherTop = panelTop + panelHeight + PANEL_GAP_PX;
    return { launcherLeft, launcherTop };
}

export function resizeFromSouthEast(geometry: StoredDrawerGeometry, seX: number, seY: number, viewport: DrawerViewport): PlacedDrawerGeometry {
    requireFiniteNumber(seX, 'seX');
    requireFiniteNumber(seY, 'seY');
    assertViewport(viewport);
    const placed = placePanel(toStoredGeometry(geometry), viewport);
    const limits = panelSizeLimits(viewport);
    const maxRight = viewport.width - viewport.margin;
    const maxBottom = viewport.height - viewport.margin - (viewport.bottomInset ?? 0);
    let panelLeft = placed.panelLeft;
    let panelTop = placed.panelTop;
    let targetSeX = seX;
    let targetSeY = seY;
    if (targetSeX > maxRight) {
        panelLeft -= targetSeX - maxRight;
        targetSeX = maxRight;
    }
    if (targetSeY > maxBottom) {
        panelTop -= targetSeY - maxBottom;
        targetSeY = maxBottom;
    }
    let width = targetSeX - panelLeft;
    let height = targetSeY - panelTop;
    if (width < limits.minWidth) {
        width = limits.minWidth;
        targetSeX = panelLeft + width;
        if (targetSeX > maxRight) {
            targetSeX = maxRight;
            panelLeft = targetSeX - width;
        }
    }
    if (height < limits.minHeight) {
        height = limits.minHeight;
        targetSeY = panelTop + height;
        if (targetSeY > maxBottom) {
            targetSeY = maxBottom;
            panelTop = targetSeY - height;
        }
    }
    if (panelLeft < viewport.margin) {
        width = Math.max(limits.minWidth, width - (viewport.margin - panelLeft));
        panelLeft = viewport.margin;
    }
    if (panelTop < viewport.margin) {
        height = Math.max(limits.minHeight, height - (viewport.margin - panelTop));
        panelTop = viewport.margin;
    }
    width = Math.min(width, maxRight - panelLeft);
    height = Math.min(height, maxBottom - panelTop);
    width = clampNumber(width, limits.minWidth, limits.maxWidth);
    height = clampNumber(height, limits.minHeight, limits.maxHeight);
    const attached = attachLauncherToPanel(
        panelLeft,
        panelTop,
        width,
        height,
        placed.panelAlign,
    );
    return clampCluster(
        {
            launcherLeft: attached.launcherLeft,
            launcherTop: attached.launcherTop,
            panelWidth: width,
            panelHeight: height,
        },
        viewport,
    );
}
