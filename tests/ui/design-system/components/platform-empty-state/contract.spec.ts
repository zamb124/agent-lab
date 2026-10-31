/**
 * platform-empty-state — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '@open-wc/testing';
import '@platform/lib/components/platform-empty-state.js';

declare function describe(name: string, fn: () => void): void;
declare function it(name: string, fn: () => void | Promise<void>): void;

describe('platform-empty-state', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-empty-state')).to.exist;
    });
});
