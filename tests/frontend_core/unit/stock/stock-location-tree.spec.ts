/**
 * Stock location tree helpers: buildLocationTree, filterTree, subtreeIds,
 * groupQuantsByLocation — структура WMS-эксплорера и субсуммы отчёта.
 */

import { describe, it, expect } from 'vitest';
import {
    asLocation,
    buildLocationTree,
    childrenIndex,
    filterTree,
    groupQuants,
    isVirtualUsage,
    subtreeIds,
    usageIcon,
} from '../../../../apps/stock/ui/_helpers/stock-location-tree.js';
import type { PlatformTreeNode } from '@platform/lib/components/platform-tree.js';
import type { StockLocation, StockQuant, StockWarehouse } from '@platform/lib/events/wire/stock.gen.js';

function kids(nodes: readonly PlatformTreeNode[], id: string): PlatformTreeNode[] {
    return nodes.filter((n) => n.parent_id === id);
}

function loc(id: string, over: Partial<StockLocation> = {}): StockLocation {
    return {
        location_id: id,
        company_id: 'c1',
        name: id,
        usage: 'bin',
        created_at: '2026-01-01T00:00:00Z',
        ...over,
    };
}

function wh(id: string): StockWarehouse {
    return {
        warehouse_id: id,
        company_id: 'c1',
        code: id,
        name: `WH ${id}`,
        view_location_id: `${id}-view`,
        stock_location_id: `${id}-stock`,
        removal_strategy: 'fifo',
        created_at: '2026-01-01T00:00:00Z',
    };
}

const t = (k: string) => k;

describe('usageIcon / isVirtualUsage', () => {
    it('маппит известные usage и даёт дефолт на неизвестные', () => {
        expect(usageIcon('view')).toBe('folder');
        expect(usageIcon('bin')).toBe('pin');
        expect(usageIcon('container')).toBe('box');
        expect(usageIcon('whatever')).toBe('pin');
    });

    it('отличает служебные usage от складских', () => {
        expect(isVirtualUsage('supplier')).toBe(true);
        expect(isVirtualUsage('adjustment')).toBe(true);
        expect(isVirtualUsage('bin')).toBe(false);
        expect(isVirtualUsage('view')).toBe(false);
        expect(isVirtualUsage('container')).toBe(false);
    });
});

describe('childrenIndex', () => {
    it('сортирует детей по pick_sequence, затем по имени', () => {
        const index = childrenIndex([
            loc('b2', { parent_id: 'z', pick_sequence: 20, name: 'B' }),
            loc('b1', { parent_id: 'z', pick_sequence: 10, name: 'A' }),
            loc('b3', { parent_id: 'z', pick_sequence: 10, name: 'C' }),
        ]);
        const kids = index.get('z');
        expect(kids?.map((l) => l.location_id)).toEqual(['b1', 'b3', 'b2']);
    });
});

describe('buildLocationTree', () => {
    it('строит склад → корневая локация → дети и складывает служебные в ветку склада', () => {
        const warehouse = wh('w1');
        const root = loc('w1-stock', { warehouse_id: 'w1', name: 'Stock', usage: 'view' });
        const zone = loc('z1', { warehouse_id: 'w1', parent_id: 'w1-stock', name: 'Zone', usage: 'view' });
        const bin = loc('b1', { warehouse_id: 'w1', parent_id: 'z1', name: 'A-01' });
        const supplier = loc('sup', { warehouse_id: 'w1', name: 'Vendors', usage: 'partner' });

        const { nodes, byId } = buildLocationTree(
            [root, zone, bin, supplier],
            [warehouse],
            t,
        );

        expect(nodes).toHaveLength(5);
        const whNode = nodes[0];
        expect(whNode?.id).toBe('wh:w1');
        expect(whNode?.parent_id).toBeNull();
        const whKids = kids(nodes, 'wh:w1');
        expect(whKids).toHaveLength(2);

        const rootNode = whKids[0];
        expect(rootNode?.id).toBe('w1-stock');
        const zoneNode = kids(nodes, 'w1-stock')[0];
        expect(zoneNode?.id).toBe('z1');
        expect(kids(nodes, 'z1')[0]?.id).toBe('b1');

        const virtualNode = whKids[1];
        expect(virtualNode?.id).toBe('sup');

        expect(byId.get('b1')?.name).toBe('A-01');
    });

    it('локации без склада уходят в ветку virtual', () => {
        const orphan = loc('orph', { warehouse_id: null, name: 'Orphan', usage: 'partner' });
        const { nodes } = buildLocationTree([orphan], [], t);
        expect(nodes).toHaveLength(2);
        expect(nodes[0]?.id).toBe('virtual');
        expect(kids(nodes, 'virtual')[0]?.id).toBe('orph');
    });

    it('помечает заблокированные локации замком, неактивные — dimmed', () => {
        const warehouse = wh('w1');
        const root = loc('w1-stock', { warehouse_id: 'w1', usage: 'view' });
        const locked = loc('b1', {
            warehouse_id: 'w1', parent_id: 'w1-stock',
            putaway_blocked: true, is_active: false,
        });
        const { nodes } = buildLocationTree([root, locked], [warehouse], t);
        const binNode = nodes.find((n) => n.id === 'b1');
        expect(binNode?.label).toContain('🔒');
        expect(binNode?.dimmed).toBe(true);
    });
});

describe('subtreeIds', () => {
    it('собирает корень и всех потомков', () => {
        const index = childrenIndex([
            loc('z', {}),
            loc('b1', { parent_id: 'z' }),
            loc('b2', { parent_id: 'z' }),
            loc('c1', { parent_id: 'b1' }),
        ]);
        expect(subtreeIds('z', index).sort()).toEqual(['b1', 'b2', 'c1', 'z']);
    });
});

describe('filterTree', () => {
    it('оставляет совпавшие узлы и всех их предков', () => {
        const { nodes } = buildLocationTree(
            [
                loc('w1-stock', { warehouse_id: 'w1', name: 'Stock', usage: 'view' }),
                loc('z1', { warehouse_id: 'w1', parent_id: 'w1-stock', name: 'Zone', usage: 'view' }),
                loc('b1', { warehouse_id: 'w1', parent_id: 'z1', name: 'A-01' }),
                loc('b2', { warehouse_id: 'w1', parent_id: 'z1', name: 'B-02' }),
            ],
            [wh('w1')],
            t,
        );
        const filtered = filterTree(nodes, 'a-01');
        expect(filtered.map((n) => n.id)).toEqual(['wh:w1', 'w1-stock', 'z1', 'b1']);
        expect(filtered.every((n) => n.id !== 'b2')).toBe(true);
    });

    it('пустой запрос возвращает все узлы', () => {
        const { nodes } = buildLocationTree([loc('a'), loc('b')], [], t);
        const filtered = filterTree(nodes, '  ');
        expect(filtered).toHaveLength(nodes.length);
    });
});

describe('groupQuants', () => {
    function quant(locationId: string, qty: string, reserved: string): StockQuant {
        return {
            quant_id: `${locationId}-q`,
            company_id: 'c1',
            product_id: 'p1',
            location_id: locationId,
            quantity: qty,
            reserved_quantity: reserved,
            in_date: '2026-01-01T00:00:00Z',
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
        };
    }

    it('суммирует qty/reserved/available по ключу', () => {
        const rows = groupQuants([
            quant('b1', '10', '4'),
            quant('b1', '5', '0'),
            quant('b2', '3', '1'),
        ], (q) => q.location_id);
        expect(rows).toHaveLength(2);
        const b1 = rows.find((r) => r.key === 'b1');
        expect(b1?.qty).toBe(15);
        expect(b1?.reserved).toBe(4);
        expect(b1?.available).toBe(11);
    });

    it('группирует по любому ключу — например по product_id', () => {
        const q = quant('b1', '7', '2');
        const rows = groupQuants([q], (qq) => qq.product_id);
        expect(rows[0]?.key).toBe('p1');
    });
});

describe('asLocation', () => {
    it('принимает запись с location_id и отвергает остальное', () => {
        expect(asLocation({ location_id: 'x' })?.location_id).toBe('x');
        expect(asLocation({ name: 'x' })).toBeNull();
        expect(asLocation('x')).toBeNull();
        expect(asLocation(null)).toBeNull();
    });
});
