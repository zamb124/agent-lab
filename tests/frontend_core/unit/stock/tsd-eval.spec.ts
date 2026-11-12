/** @vitest-environment node */
import { describe, it, expect } from 'vitest';

describe('tsd factory graph eval', () => {
    it('stock-tsd.resource.ts module evals without throw', async () => {
        const mod = await import('../../../../apps/stock/ui/events/resources/stock-tsd.resource.js');
        expect(mod.stockTsdOutboxSlice.name).toBe('stock/tsd_outbox');
    });
    it('stock.resource.ts module evals without throw', async () => {
        const mod = await import('../../../../apps/stock/ui/events/resources/stock.resource.js');
        expect(typeof mod.stockContainerMoveOp).toBe('object');
    });
    it('tsd-persist.effect.ts module evals without throw', async () => {
        const mod = await import('../../../../apps/stock/ui/events/tsd-persist.effect.js');
        expect(typeof mod.createTsdPersistEffect).toBe('function');
    });
});
