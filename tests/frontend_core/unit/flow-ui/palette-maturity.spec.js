import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
    FLOW_UI_CATALOG_MANIFEST,
    FLOW_UI_EDITOR_GROUPS,
    FLOW_UI_PALETTE_PSEUDO_ENTRIES,
    flowUIPaletteComponentEntries,
} from '../../../../core/frontend/static/lib/flow-ui/catalog/manifest.js';
import { resolveFlowUIGlyphFile } from '../../../../core/frontend/static/lib/flow-ui/catalog/flow-ui-glyph-resolve.js';

const STUB_TYPES = Object.freeze([
    'Chart',
    'JsonInspector',
    'BrowserPreview',
    'SkillActivity',
    'ReflectionResult',
    'ActionPreview',
    'ActionResult',
    'ActivityCard',
    'FileCollection',
]);

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');

describe('flow-ui palette maturity', () => {
    it('exposes maturity and palette on every catalog entry', () => {
        for (const entry of Object.values(FLOW_UI_CATALOG_MANIFEST.components)) {
            expect(entry.editor.maturity).toMatch(/^(production|partial|runtime_owned|stub)$/);
            expect(typeof entry.editor.palette).toBe('boolean');
        }
    });

    it('hides stub types and PageShell from palette enumeration', () => {
        const types = flowUIPaletteComponentEntries().map((entry) => entry.type);
        expect(types).not.toContain('PageShell');
        expect(types).not.toContain('Quote');
        for (const stub of STUB_TYPES) {
            expect(FLOW_UI_CATALOG_MANIFEST.components[stub].editor.maturity).toBe('stub');
            expect(FLOW_UI_CATALOG_MANIFEST.components[stub].editor.palette).toBe(false);
            expect(types).not.toContain(stub);
        }
        expect(types).toContain('TextField');
        expect(types).toContain('Icon');
        expect(types).toContain('ConversationFeed');
    });

    it('keeps stub renderers registered in the catalog for runtime projection', () => {
        for (const stub of STUB_TYPES) {
            expect(FLOW_UI_CATALOG_MANIFEST.components[stub]).toBeTruthy();
        }
    });
});

describe('flow-ui Icon glyph', () => {
    it('resolves catalog icon names to static SVG assets', () => {
        expect(resolveFlowUIGlyphFile('star')).toBe('star');
        expect(resolveFlowUIGlyphFile('file')).toBe('file-text');
    });

    it('rejects unsafe icon basenames', () => {
        expect(() => resolveFlowUIGlyphFile('../etc/passwd')).toThrow(/invalid glyph name/);
        expect(() => resolveFlowUIGlyphFile('')).toThrow(/glyph name required/);
    });

    it('implements Icon via flowUIGlyph, not a 2-char badge', () => {
        const extrasSrc = readFileSync(
            path.join(REPO_ROOT, 'core/frontend/static/lib/flow-ui/catalog/basic/extras.js'),
            'utf8',
        );
        const glyphSrc = readFileSync(
            path.join(REPO_ROOT, 'core/frontend/static/lib/flow-ui/catalog/flow-ui-glyph.js'),
            'utf8',
        );
        expect(extrasSrc).toMatch(/flowUIGlyph\(\s*String\(name\)\.trim\(\)\s*,\s*20\s*\)/);
        expect(extrasSrc).not.toMatch(/\.slice\(\s*0\s*,\s*2\s*\)/);
        expect(glyphSrc).toContain('/static/core/assets/icons/');
        expect(glyphSrc).toContain('flow-ui-glyph');
    });
});

describe('flow-ui palette names', () => {
    it('gives every insertable entry a pinned RU/EN name', () => {
        for (const entry of [...flowUIPaletteComponentEntries(), ...FLOW_UI_PALETTE_PSEUDO_ENTRIES]) {
            const label = entry.editor.label;
            expect(label, entry.type).to.be.an('object');
            for (const locale of ['ru', 'en']) {
                expect(typeof label[locale], `${entry.type}.${locale}`).toBe('string');
                expect(label[locale].trim(), `${entry.type}.${locale}`).not.toBe('');
            }
        }
    });

    it('reads as a name, not as a type id', () => {
        const byType = new Map(
            flowUIPaletteComponentEntries().map((entry) => [entry.type, entry.editor.label]),
        );
        expect(byType.get('Card').ru).toBe('Карточка');
        expect(byType.get('Section').ru).toBe('Секция');
        expect(byType.get('TextField').ru).toBe('Поле ввода');
        expect(byType.get('Card').en).toBe('Card');
    });

    it('says a Columns preset builds a row split into columns', () => {
        const byType = new Map(
            FLOW_UI_PALETTE_PSEUDO_ENTRIES.map((entry) => [entry.type, entry.editor.label]),
        );
        expect(byType.get('Columns2').ru).toBe('Ряд: 2 колонки');
        expect(byType.get('Columns3').ru).toBe('Ряд: 3 колонки');
        expect(byType.get('Columns4').en).toBe('Row: 4 columns');
        expect(byType.get('Submit').ru).toBe('Кнопка отправки');
    });

    it('keeps pseudo entries in real palette groups', () => {
        for (const entry of FLOW_UI_PALETTE_PSEUDO_ENTRIES) {
            expect(FLOW_UI_EDITOR_GROUPS).toContain(entry.editor.group);
            expect(entry.editor.palette).toBe(true);
        }
    });
});
