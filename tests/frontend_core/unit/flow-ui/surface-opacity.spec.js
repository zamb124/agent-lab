import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '../../../..');

describe('Flow UI surface opacity contract', () => {
    it('defines opaque page background token and transparent overlay token', () => {
        const tokens = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/shell/tokens.css'),
            'utf8',
        );
        expect(tokens).toMatch(/--flow-ui-page-background:\s*var\(--bg-primary/);
        expect(tokens).toMatch(/--flow-ui-background:\s*transparent/);
    });

    it('platform-flow-ui paints opaque page fill (no spa transparent chat)', () => {
        const source = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/components/platform-flow-ui.js'),
            'utf8',
        );
        expect(source).toMatch(/background:\s*var\(--flow-ui-page-background/);
        expect(source).not.toMatch(/:host\(\[profile="spa"\]\)\s*\{[^}]*--flow-ui-page-background:\s*transparent/s);
    });

    it('page-shell inherits opaque page fill', () => {
        const source = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/components/flow-ui-surface.js'),
            'utf8',
        );
        expect(source).toMatch(/\.page-shell\s*\{[^}]*background:\s*var\(--flow-ui-page-background/s);
    });
});
