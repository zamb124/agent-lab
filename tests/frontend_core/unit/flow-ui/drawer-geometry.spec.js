import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
    DEFAULT_PANEL_HEIGHT_PX,
    DEFAULT_PANEL_WIDTH_PX,
    LAUNCHER_SIZE_PX,
    MIN_PANEL_HEIGHT_PX,
    MIN_PANEL_WIDTH_PX,
    MOBILE_MAX_WIDTH_PX,
    PANEL_GAP_PX,
    clampCluster,
    createDefaultGeometry,
    gesturesAllowed,
    moveCluster,
    parseStoredGeometry,
    placePanel,
    resizeFromSouthEast,
    toStoredGeometry,
} from '../../../../core/frontend/static/lib/flow-ui/shell/drawer-geometry.js';
import { drawerGeometryStorageKey } from '../../../../core/frontend/static/lib/flow-ui/shell/preferences.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '../../../..');

const DESKTOP = Object.freeze({ width: 1280, height: 800, margin: 22 });
const NARROW = Object.freeze({ width: 400, height: 720, margin: 10 });

function assertClusterInsideViewport(cluster, viewport) {
    const left = Math.min(cluster.panelLeft, cluster.launcherLeft);
    const top = Math.min(cluster.panelTop, cluster.launcherTop);
    const right = Math.max(
        cluster.panelLeft + cluster.panelWidth,
        cluster.launcherLeft + LAUNCHER_SIZE_PX,
    );
    const bottom = Math.max(
        cluster.panelTop + cluster.panelHeight,
        cluster.launcherTop + LAUNCHER_SIZE_PX,
    );
    expect(left).toBeGreaterThanOrEqual(viewport.margin);
    expect(top).toBeGreaterThanOrEqual(viewport.margin);
    expect(right).toBeLessThanOrEqual(viewport.width - viewport.margin);
    expect(bottom).toBeLessThanOrEqual(viewport.height - viewport.margin);
}

describe('drawer-geometry', () => {
    it('places default corners at the bottom of the viewport', () => {
        const right = createDefaultGeometry('bottom-right', DESKTOP);
        expect(right.launcherLeft).toBe(DESKTOP.width - DESKTOP.margin - LAUNCHER_SIZE_PX);
        expect(right.launcherTop).toBe(DESKTOP.height - DESKTOP.margin - LAUNCHER_SIZE_PX);
        expect(right.panelWidth).toBe(DEFAULT_PANEL_WIDTH_PX);
        expect(right.panelHeight).toBeLessThanOrEqual(DEFAULT_PANEL_HEIGHT_PX);

        const left = createDefaultGeometry('bottom-left', DESKTOP);
        expect(left.launcherLeft).toBe(DESKTOP.margin);
        expect(left.launcherTop).toBe(right.launcherTop);
    });

    it('rejects an invalid initial corner', () => {
        expect(() => createDefaultGeometry('top-right', DESKTOP)).toThrow(/invalid position/);
    });

    it('opens the panel above a right-side launcher with matching right edges', () => {
        const stored = createDefaultGeometry('bottom-right', DESKTOP);
        const placed = placePanel(stored, DESKTOP);
        expect(placed.panelAlign).toBe('right');
        expect(placed.panelPlacement).toBe('above');
        expect(placed.panelLeft + placed.panelWidth).toBe(placed.launcherLeft + LAUNCHER_SIZE_PX);
        expect(placed.panelTop + placed.panelHeight + PANEL_GAP_PX).toBe(placed.launcherTop);
        assertClusterInsideViewport(clampCluster(stored, DESKTOP), DESKTOP);
    });

    it('opens the panel above a left-side launcher with matching left edges', () => {
        const stored = createDefaultGeometry('bottom-left', DESKTOP);
        const placed = placePanel(stored, DESKTOP);
        expect(placed.panelAlign).toBe('left');
        expect(placed.panelLeft).toBe(placed.launcherLeft);
        assertClusterInsideViewport(clampCluster(stored, DESKTOP), DESKTOP);
    });

    it('places the panel below the launcher when there is no room above', () => {
        const stored = {
            launcherLeft: 100,
            launcherTop: 40,
            panelWidth: 300,
            panelHeight: 400,
        };
        const placed = placePanel(stored, DESKTOP);
        expect(placed.panelPlacement).toBe('below');
        expect(placed.panelTop).toBe(stored.launcherTop + LAUNCHER_SIZE_PX + PANEL_GAP_PX);
        assertClusterInsideViewport(clampCluster(stored, DESKTOP), DESKTOP);
    });

    it('clamps a wide panel when the preferred side overflows', () => {
        const viewport = { width: 800, height: 700, margin: 16 };
        const stored = {
            launcherLeft: 500,
            launcherTop: 500,
            panelWidth: 700,
            panelHeight: 320,
        };
        const clamped = clampCluster(stored, viewport);
        assertClusterInsideViewport(clamped, viewport);
        expect(clamped.panelWidth).toBeLessThanOrEqual(viewport.width - viewport.margin * 2);
    });

    it('clamps a cluster that starts outside the viewport', () => {
        const clamped = clampCluster(
            {
                launcherLeft: -400,
                launcherTop: 4000,
                panelWidth: 9000,
                panelHeight: 9000,
            },
            DESKTOP,
        );
        expect(clamped.panelWidth).toBeLessThanOrEqual(
            DESKTOP.width - DESKTOP.margin * 2,
        );
        expect(clamped.panelHeight).toBeGreaterThanOrEqual(MIN_PANEL_HEIGHT_PX);
        expect(clamped.panelWidth).toBeGreaterThanOrEqual(
            Math.min(MIN_PANEL_WIDTH_PX, DESKTOP.width - DESKTOP.margin * 2),
        );
        assertClusterInsideViewport(clamped, DESKTOP);
    });

    it('moves the whole cluster by delta and clamps', () => {
        const start = clampCluster(
            {
                launcherLeft: 400,
                launcherTop: 500,
                panelWidth: 300,
                panelHeight: 320,
            },
            DESKTOP,
        );
        const moved = moveCluster(start, -80, -40, DESKTOP);
        expect(moved.launcherLeft).toBe(start.launcherLeft - 80);
        expect(moved.launcherTop).toBe(start.launcherTop - 40);
        expect(moved.panelWidth).toBe(start.panelWidth);
        assertClusterInsideViewport(moved, DESKTOP);

        const blocked = moveCluster(start, 4000, 4000, DESKTOP);
        assertClusterInsideViewport(blocked, DESKTOP);
    });

    it('resizes from the south-east corner and grows the opposite side at the viewport edge', () => {
        const start = clampCluster(
            {
                launcherLeft: 200,
                launcherTop: 500,
                panelWidth: 300,
                panelHeight: 320,
            },
            DESKTOP,
        );
        const seX = start.panelLeft + start.panelWidth;
        const seY = start.panelTop + start.panelHeight;
        const grown = resizeFromSouthEast(start, seX + 80, seY + 40, DESKTOP);
        expect(grown.panelWidth).toBe(start.panelWidth + 80);
        expect(grown.panelHeight).toBe(start.panelHeight + 40);
        expect(grown.launcherTop).toBe(grown.panelTop + grown.panelHeight + PANEL_GAP_PX);
        assertClusterInsideViewport(grown, DESKTOP);

        const pastEdge = resizeFromSouthEast(start, DESKTOP.width + 500, seY, DESKTOP);
        expect(pastEdge.panelWidth).toBeGreaterThan(start.panelWidth);
        expect(pastEdge.panelLeft).toBeLessThan(start.panelLeft);
        expect(pastEdge.panelLeft + pastEdge.panelWidth).toBeLessThanOrEqual(
            DESKTOP.width - DESKTOP.margin,
        );
        assertClusterInsideViewport(pastEdge, DESKTOP);
    });

    it('disables gestures at the mobile breakpoint', () => {
        expect(gesturesAllowed({ width: MOBILE_MAX_WIDTH_PX, height: 800, margin: 10 })).toBe(false);
        expect(gesturesAllowed({ width: MOBILE_MAX_WIDTH_PX + 1, height: 800, margin: 22 })).toBe(true);
        expect(gesturesAllowed(NARROW)).toBe(false);
    });

    it('parses stored geometry fail-closed', () => {
        expect(parseStoredGeometry(null)).toBe(null);
        expect(parseStoredGeometry(undefined)).toBe(null);
        expect(parseStoredGeometry({})).toBe(null);
        expect(() => parseStoredGeometry([])).toThrow(/must be an object/);
        expect(() => parseStoredGeometry('nope')).toThrow(/must be an object/);
        expect(() => parseStoredGeometry({ launcherLeft: 1 })).toThrow(/expected/);
        expect(() => parseStoredGeometry({
            launcherLeft: 1,
            launcherTop: 2,
            panelWidth: 3,
            panelHeight: Number.NaN,
        })).toThrow(/panelHeight/);
        const stored = parseStoredGeometry({
            launcherLeft: 10,
            launcherTop: 20,
            panelWidth: 300,
            panelHeight: 400,
        });
        expect(stored).toEqual({
            launcherLeft: 10,
            launcherTop: 20,
            panelWidth: 300,
            panelHeight: 400,
        });
        expect(Object.isFrozen(stored)).toBe(true);
        expect(toStoredGeometry({
            ...stored,
            panelLeft: 1,
            panelTop: 2,
            panelAlign: 'right',
            panelPlacement: 'above',
        })).toEqual(stored);
    });
});

describe('drawer geometry persist key', () => {
    it('builds the Lara key from a snake_case branchId', () => {
        expect(drawerGeometryStorageKey('sync')).toBe('platform:core:assistant.drawer.sync');
        expect(() => drawerGeometryStorageKey('Sync')).toThrow(/snake_case/);
        expect(() => drawerGeometryStorageKey('geo-1')).toThrow(/snake_case/);
    });
});

describe('drawer geometry stays in the embed host', () => {
    it('service apps do not own cluster geometry or a left FAB', () => {
        const appDirNames = readdirSync(join(root, 'apps'));
        const appFiles = appDirNames.flatMap((svc) => {
            const dir = join(root, 'apps', svc, 'ui', 'app');
            if (!existsSync(dir)) {
                return [];
            }
            return readdirSync(dir)
                .filter((name) => name.endsWith('-app.js') || name.endsWith('-app.ts'))
                .map((name) => join(dir, name));
        });
        expect(appFiles.length).toBeGreaterThan(5);
        for (const file of appFiles) {
            const source = readFileSync(file, 'utf8');
            expect(source).not.toContain('drawer-geometry');
            expect(source).not.toContain('moveCluster');
            expect(source).not.toContain('resizeFromSouthEast');
            expect(source).not.toContain("launcherPosition: 'bottom-left'");
        }
    });

    it('embed autoload keeps launcherPosition as the initial corner only', () => {
        const autoload = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/shell/embed-autoload.ts'),
            'utf8',
        );
        expect(autoload).toContain('launcherPosition');
        expect(autoload).not.toContain('moveCluster');
        expect(autoload).not.toContain('resizeFromSouthEast');
        expect(autoload).not.toContain('drawer-geometry');

        const hostApi = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/shell/embed-host-api.ts'),
            'utf8',
        );
        expect(hostApi).not.toContain('moveCluster');
        expect(hostApi).not.toContain('parseStoredGeometry');
        expect(hostApi).not.toContain('drawer-geometry');
    });
});
