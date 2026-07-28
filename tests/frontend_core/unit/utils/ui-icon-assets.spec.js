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
import { resolveUiIconFile } from '@platform/lib/utils/file-icons.js';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
const iconsDir = path.join(rootDir, 'core/frontend/static/assets/icons');
const scanRoots = [
    path.join(rootDir, 'core/frontend/static/lib'),
    path.join(rootDir, 'apps'),
];

/** `<platform-icon ... name="foo">` — только строковый литерал, без `${}`. */
const ICON_TAG_RE = /<platform-icon\b[^>]*?\bname="([a-z0-9_-]+)"/gs;
/** `icon: 'foo'` в описаниях пунктов меню, вкладок и навигации. */
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
            for (const re of [ICON_TAG_RE, ICON_PROP_RE]) {
                re.lastIndex = 0;
                let match = re.exec(source);
                while (match !== null) {
                    const name = match[1];
                    if (!usages.has(name)) {
                        usages.set(name, path.relative(rootDir, file));
                    }
                    match = re.exec(source);
                }
            }
        }
    }
    return usages;
}

describe('UI icons', () => {
    it('у каждого имени иконки есть SVG в ассетах', () => {
        const usages = collectIconUsages();
        expect(usages.size).toBeGreaterThan(50);

        const missing = [];
        for (const [name, file] of usages) {
            const asset = path.join(iconsDir, `${resolveUiIconFile(name)}.svg`);
            if (!fs.existsSync(asset)) {
                missing.push(`${name} (${file})`);
            }
        }

        expect(missing).toEqual([]);
    });
});
