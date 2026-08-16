import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { resolveFlowUITheme } from '../../../../core/frontend/static/lib/flow-ui/shell/resolve-theme.js';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
const HOST_SOURCE = readFileSync(
    path.join(REPO_ROOT, 'core/frontend/static/lib/flow-ui/components/platform-flow-ui.js'),
    'utf8',
);

describe('embed theme isolation', () => {
    it('resolves auto to dark when the host page has no data-theme', () => {
        const doc = {
            documentElement: {
                getAttribute() {
                    return null;
                },
            },
        };
        expect(resolveFlowUITheme('auto', doc)).toBe('dark');
    });

    it('paints dark and light palettes on the widget, not host --text-primary', () => {
        expect(HOST_SOURCE).toContain('data-resolved-theme="dark"');
        expect(HOST_SOURCE).toContain('data-resolved-theme="light"');
        expect(HOST_SOURCE).toContain("this.setAttribute('data-resolved-theme', this._resolvedTheme())");
        const darkBlock = HOST_SOURCE.slice(
            HOST_SOURCE.indexOf(':host([data-resolved-theme="dark"])'),
            HOST_SOURCE.indexOf(':host([data-resolved-theme="light"])'),
        );
        expect(darkBlock).toContain('--flow-ui-text: rgba(255, 255, 255, 0.95)');
        expect(darkBlock).not.toContain('var(--text-primary');
    });
});
