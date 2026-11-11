/**
 * Чистые хелперы дерева локаций и группировки остатков для WMS-раздела.
 *
 * Узел дерева склада: корни — склады (`wh:<id>`) и виртуальные локации
 * (`virtual` — `warehouse_id IS NULL`), дети — локации по `parent_id`.
 */

import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { PlatformTreeNode } from '@platform/lib/components/platform-tree.js';
import type { StockLocation, StockQuant, StockWarehouse } from '@platform/lib/events/wire/stock.gen.js';

export interface LocationTreeData {
    nodes: PlatformTreeNode[];
    byId: Map<string, StockLocation>;
    childrenOf: Map<string, StockLocation[]>;
}

const USAGE_ICONS: Record<string, string> = {
    view: 'folder',
    internal: 'folder',
    bin: 'pin',
    container: 'box',
    partner: 'truck',
    customer: 'truck',
    supplier: 'truck',
    transit: 'truck',
    inventory: 'adjustment',
    adjustment: 'adjustment',
    production: 'settings',
    scrap: 'trash',
};

export function usageIcon(usage: string): string {
    return USAGE_ICONS[usage] ?? 'pin';
}

export function isVirtualUsage(usage: string): boolean {
    return usage === 'partner' || usage === 'customer' || usage === 'supplier'
        || usage === 'transit' || usage === 'inventory' || usage === 'adjustment'
        || usage === 'production' || usage === 'scrap';
}

export function childrenIndex(locations: readonly StockLocation[]): Map<string, StockLocation[]> {
    const byParent = new Map<string, StockLocation[]>();
    for (const loc of locations) {
        const parent = loc.parent_id ?? '';
        const bucket = byParent.get(parent) ?? [];
        bucket.push(loc);
        byParent.set(parent, bucket);
    }
    for (const bucket of byParent.values()) {
        bucket.sort((a, b) => (a.pick_sequence ?? 0) - (b.pick_sequence ?? 0) || a.name.localeCompare(b.name));
    }
    return byParent;
}

function locationToNode(loc: StockLocation, parentId: string, kidCount: number): PlatformTreeNode {
    const labels: string[] = [loc.name];
    if (loc.removal_blocked || loc.putaway_blocked) labels.push('🔒');
    return {
        id: loc.location_id,
        parent_id: parentId,
        label: labels.join(' '),
        icon: usageIcon(loc.usage),
        dimmed: loc.is_active === false,
        ...(kidCount > 0 ? { count: kidCount } : {}),
    };
}

export function buildLocationTree(
    locations: readonly StockLocation[],
    warehouses: readonly StockWarehouse[],
    t: (k: string) => string,
): LocationTreeData {
    const byId = new Map<string, StockLocation>();
    for (const loc of locations) byId.set(loc.location_id, loc);
    const childrenOf = childrenIndex(locations);
    const nodes: PlatformTreeNode[] = [];

    const emitSubtree = (loc: StockLocation, parentId: string): void => {
        const kids = childrenOf.get(loc.location_id) ?? [];
        nodes.push(locationToNode(loc, parentId, kids.length));
        for (const kid of kids) emitSubtree(kid, loc.location_id);
    };

    for (const wh of warehouses) {
        const whId = `wh:${wh.warehouse_id}`;
        const roots = locations.filter((l) => l.warehouse_id === wh.warehouse_id && !l.parent_id);
        const virtuals = locations.filter((l) => l.warehouse_id === wh.warehouse_id && isVirtualUsage(l.usage)
            && !roots.some((r) => r.location_id === l.location_id));
        nodes.push({
            id: whId,
            parent_id: null,
            label: wh.name,
            icon: 'store',
            count: roots.length + virtuals.length,
        });
        for (const root of roots) emitSubtree(root, whId);
        for (const v of virtuals) emitSubtree(v, whId);
    }

    const orphans = locations.filter((l) => !l.warehouse_id
        || !warehouses.some((w) => w.warehouse_id === l.warehouse_id));
    const orphanRoots = orphans.filter((l) => !l.parent_id || !byId.has(l.parent_id));
    if (orphanRoots.length > 0) {
        nodes.push({
            id: 'virtual',
            parent_id: null,
            label: t('explorer.virtual_locations'),
            icon: 'layers',
            count: orphanRoots.length,
        });
        for (const root of orphanRoots) emitSubtree(root, 'virtual');
    }
    return { nodes, byId, childrenOf };
}

/** Ids локации и всех потомков — для `subtree_location_id` фильтров. */
export function subtreeIds(rootId: string, childrenOf: Map<string, StockLocation[]>): string[] {
    const ids = [rootId];
    const stack = [...(childrenOf.get(rootId) ?? [])];
    while (stack.length > 0) {
        const loc = stack.pop();
        if (loc === undefined) break;
        ids.push(loc.location_id);
        stack.push(...(childrenOf.get(loc.location_id) ?? []));
    }
    return ids;
}

/** Узлы, отфильтрованные поиском: совпавшие + все их предки (плоский список). */
export function filterTree(nodes: readonly PlatformTreeNode[], query: string): PlatformTreeNode[] {
    const q = query.trim().toLowerCase();
    if (q === '') return [...nodes];
    const byId = new Map<string, PlatformTreeNode>();
    for (const node of nodes) byId.set(node.id, node);
    const keep = new Set<string>();
    for (const node of nodes) {
        if (!node.label.toLowerCase().includes(q)) continue;
        let current: PlatformTreeNode | undefined = node;
        while (current !== undefined && !keep.has(current.id)) {
            keep.add(current.id);
            const parentId: string | null | undefined = current.parent_id;
            current = typeof parentId === 'string' ? byId.get(parentId) : undefined;
        }
    }
    return nodes.filter((node) => keep.has(node.id));
}

export interface QuantGroupRow {
    key: string;
    items: StockQuant[];
    qty: number;
    reserved: number;
    available: number;
}

/** Группировка quants по произвольному ключу с субсуммами qty/reserved/available. */
export function groupQuants(quants: readonly StockQuant[], keyOf: (q: StockQuant) => string): QuantGroupRow[] {
    const groups = new Map<string, QuantGroupRow>();
    for (const q of quants) {
        const key = keyOf(q);
        let row = groups.get(key);
        if (row === undefined) {
            row = { key, items: [], qty: 0, reserved: 0, available: 0 };
            groups.set(key, row);
        }
        row.items.push(q);
        row.qty += Number(q.quantity);
        row.reserved += Number(q.reserved_quantity);
        row.available += Number(q.quantity) - Number(q.reserved_quantity);
    }
    return [...groups.values()];
}

export function asLocation(value: unknown): StockLocation | null {
    if (!isPlainRecord(value)) return null;
    if (typeof value.location_id !== 'string') return null;
    return value as unknown as StockLocation;
}
