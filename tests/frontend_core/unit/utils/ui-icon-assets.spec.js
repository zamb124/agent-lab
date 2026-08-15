/**
 * Каждое literal-имя иконки в UI обязано резолвиться в существующий SVG.
 *
 * Имя без ассета даёт 404 и пустое место в интерфейсе — молча, без ошибки в
 * коде. Так уже пропадали кнопки меню блока и панели форматирования редактора.
 */

import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveFileIconBasename, resolveUiIconFile } from '@platform/lib/utils/file-icons.js';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
const iconsDir = path.join(rootDir, 'core/frontend/static/assets/icons');
const fileIconsDir = path.join(iconsDir, 'files_icons');
const scanRoots = [
    path.join(rootDir, 'core/frontend/static/lib'),
    path.join(rootDir, 'apps'),
];

/** Целый тег: `file-icon` может стоять и до, и после `name`. */
const ICON_TAG_RE = /<platform-icon\b([^>]*)>/gs;
const ICON_NAME_ATTR_RE = /\bname="([a-z0-9_-]+)"/;
/** `icon: 'foo'` в описаниях пунктов меню, вкладок и навигации — UI-иконки. */
const ICON_PROP_RE = /\bicon:\s*'([a-z0-9_-]+)'/g;

function collectJsFiles(dir, acc) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === 'node_modules' || entry.name === 'vendor') continue;
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            collectJsFiles(full, acc);
        } else if (entry.name.endsWith('.js')) {
            acc.push(full);
        }
    }
    return acc;
}

function collectIconUsages() {
    const usages = new Map();
    for (const root of scanRoots) {
        for (const file of collectJsFiles(root, [])) {
            const source = fs.readFileSync(file, 'utf8');
            const relative = path.relative(rootDir, file);

            ICON_TAG_RE.lastIndex = 0;
            let tagMatch = ICON_TAG_RE.exec(source);
            while (tagMatch !== null) {
                const attrs = tagMatch[1];
                const nameMatch = ICON_NAME_ATTR_RE.exec(attrs);
                if (nameMatch !== null) {
                    const name = nameMatch[1];
                    const kind = /\bfile-icon\b/.test(attrs) ? 'file' : 'ui';
                    const key = `${kind}:${name}`;
                    if (!usages.has(key)) {
                        usages.set(key, { kind, name, file: relative });
                    }
                }
                tagMatch = ICON_TAG_RE.exec(source);
            }

            ICON_PROP_RE.lastIndex = 0;
            let propMatch = ICON_PROP_RE.exec(source);
            while (propMatch !== null) {
                const name = propMatch[1];
                const key = `ui:${name}`;
                if (!usages.has(key)) {
                    usages.set(key, { kind: 'ui', name, file: relative });
                }
                propMatch = ICON_PROP_RE.exec(source);
            }
        }
    }
    return usages;
}

function resolveIconAssetPath(kind, name) {
    if (kind === 'file') {
        return path.join(fileIconsDir, `${resolveFileIconBasename(name)}.svg`);
    }
    return path.join(iconsDir, `${resolveUiIconFile(name)}.svg`);
}

describe('UI icons', () => {
    it('у каждого имени иконки есть SVG в ассетах', () => {
        const usages = collectIconUsages();
        expect(usages.size).toBeGreaterThan(50);

        const missing = [];
        for (const { kind, name, file } of usages.values()) {
            const asset = resolveIconAssetPath(kind, name);
            if (!fs.existsSync(asset)) {
                missing.push(`${kind}:${name} (${file})`);
            }
        }

        expect(missing).toEqual([]);
    });
});
