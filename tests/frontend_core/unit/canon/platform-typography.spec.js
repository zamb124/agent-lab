// Platform typography canon: manifest, tokens import, SPA shells, zero legacy fonts.

import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, '..', '..', '..', '..');

const MANIFEST_PATH = path.join(
    ROOT,
    'core/frontend/static/assets/fonts/platform-typography.json',
);
const TOKENS_PATH = path.join(ROOT, 'core/frontend/static/assets/css/tokens.css');
const RESET_PATH = path.join(ROOT, 'core/frontend/static/assets/css/reset.css');
const FONTS_CSS_PATH = path.join(
    ROOT,
    'core/frontend/static/assets/fonts/platform-fonts.css',
);
const FONTS_DIR = path.join(ROOT, 'core/frontend/static/assets/fonts');

const SPA_SHELLS = [
    'apps/frontend/ui/index.html',
    'apps/flows/ui/index.html',
    'apps/sync/ui/index.html',
    'apps/crm/ui/index.html',
    'apps/rag/ui/index.html',
    'apps/office/ui/index.html',
    'apps/worktracker/ui/index.html',
    'apps/provider_litserve/ui/index.html',
];

const PLATFORM_HTML = [
    'core/frontend/pwa/offline.html',
    'apps/agent/desktop/branding/humanitec-pairing.html',
];

const SCAN_ROOTS = [
    path.join(ROOT, 'apps'),
    path.join(ROOT, 'core/frontend/static/lib'),
    path.join(ROOT, 'core/frontend/pwa'),
    path.join(ROOT, 'apps/agent/desktop/branding'),
];

const SKIP_DIRS = new Set(['vendor', 'node_modules', 'design', 'mermaid', '.lighthouseci']);

const LEGACY_PATTERNS = [
    /fira-sans/i,
    /Fira Sans/,
    /Onest/,
    /SF Pro Display/,
    /Geist/,
    /--font-main\b/,
    /--font-condensed\b/,
    /font-family:\s*['"]?(Fira Sans|Onest|SF Pro|Geist)/,
    /font-family:\s*ui-monospace/,
    /font-family:\s*monospace\s*;/,
    /var\(--font-mono,/,
    /var\(--font-sans,/,
];

function _walk(dir, out = []) {
    if (!existsSync(dir)) return out;
    for (const name of readdirSync(dir)) {
        if (SKIP_DIRS.has(name)) continue;
        const full = path.join(dir, name);
        const st = statSync(full);
        if (st.isDirectory()) {
            _walk(full, out);
        } else if (/\.(js|css|html)$/.test(name)) {
            out.push(full);
        }
    }
    return out;
}

describe('platform typography canon', () => {
    const manifest = JSON.parse(readFileSync(MANIFEST_PATH, 'utf8'));

    it('manifest declares Inter sans and JetBrains Mono with existing woff2 files', () => {
        expect(manifest.sans.family).toBe('Inter');
        expect(manifest.mono.family).toBe('JetBrains Mono');
        for (const role of ['sans', 'mono']) {
            for (const face of manifest[role].faces) {
                const fontPath = path.join(FONTS_DIR, face.path);
                expect(existsSync(fontPath), face.path).toBe(true);
            }
        }
    });

    it('tokens.css imports platform fonts and uses manifest stacks', () => {
        const tokens = readFileSync(TOKENS_PATH, 'utf8');
        const reset = readFileSync(RESET_PATH, 'utf8');
        expect(tokens).toContain("@import url('../fonts/platform-fonts.css');");
        expect(tokens).toContain(`--font-sans: ${manifest.stacks.sans};`);
        expect(tokens).toContain(`--font-mono: ${manifest.stacks.mono};`);
        expect(tokens).toContain('--font-feature-sans:');
        expect(reset).toContain('font-family: var(--font-sans);');
        expect(reset).toContain('font-feature-settings: var(--font-feature-sans);');
    });

    it('platform-fonts.css declares manifest families with font-display swap', () => {
        const fontsCss = readFileSync(FONTS_CSS_PATH, 'utf8');
        expect(fontsCss).toContain(`font-family: '${manifest.sans.family}'`);
        expect(fontsCss).toContain(`font-family: '${manifest.mono.family}'`);
        expect(fontsCss).toContain('font-display: swap');
    });

    it('SPA and platform HTML shells do not load local fonts or legacy bundles', () => {
        for (const rel of [...SPA_SHELLS, ...PLATFORM_HTML]) {
            const html = readFileSync(path.join(ROOT, rel), 'utf8');
            expect(html, rel).not.toMatch(/@font-face/i);
            expect(html, rel).not.toMatch(/fira-sans/i);
            expect(html, rel).not.toMatch(/fonts\.google/i);
        }
        const offline = readFileSync(path.join(ROOT, 'core/frontend/pwa/offline.html'), 'utf8');
        expect(offline).toContain('/static/core/assets/css/tokens.css');
        expect(offline).toContain('var(--font-sans)');
    });

    it('runtime UI tree has no legacy typography patterns', () => {
        const files = SCAN_ROOTS.flatMap((dir) => _walk(dir));
        const hits = [];
        for (const filePath of files) {
            const rel = path.relative(ROOT, filePath);
            if (rel.endsWith('design/design.css')) continue;
            if (rel.endsWith('platform-fonts.css')) continue;
            if (rel.endsWith('tokens.css')) continue;
            const text = readFileSync(filePath, 'utf8');
            for (const pattern of LEGACY_PATTERNS) {
                if (pattern.test(text)) {
                    hits.push(`${rel}: ${pattern}`);
                    break;
                }
            }
        }
        expect(hits).toEqual([]);
    });
});
