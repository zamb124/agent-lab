import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '../../../..');

describe('submit Button busy contract', () => {
    it('wires platform.ui.submit Buttons to context.submitting spinner chrome', () => {
        const form = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/catalog/basic/form.js'),
            'utf8',
        );
        expect(form).toMatch(/activeContext\?\.submitting === true/);
        expect(form).toMatch(/button-spinner/);
        expect(form).toMatch(/aria-busy/);

        const surface = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/components/flow-ui-surface.js'),
            'utf8',
        );
        expect(surface).toMatch(/\.button-spinner/);
        expect(surface).toMatch(/activeContext\?\.submitting === true/);

        const controller = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/runtime/flow-ui-controller.js'),
            'utf8',
        );
        expect(controller).toMatch(/activeContext\?\.submitting === true\) return/);
        expect(controller).toMatch(/type: 'submit\.started'/);
        const startedIdx = controller.indexOf("type: 'submit.started'");
        const flushIdx = controller.indexOf('await this.autosync.flushNow()');
        expect(startedIdx).toBeGreaterThan(-1);
        expect(flushIdx).toBeGreaterThan(startedIdx);
    });
});
