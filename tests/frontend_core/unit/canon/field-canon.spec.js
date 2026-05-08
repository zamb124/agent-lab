// Канон-тест Field canon (PHASE 1.5).
//
// Дублирует логику детекторов:
//   - scripts/check_field_canon.sh    (raw input/textarea/select без pill-обёртки)
//   - scripts/check_ui_canon.sh п.17   (локальные .form-x / .field-pill-x CSS в apps)
//   - scripts/check_ui_canon.sh п.18   (импорт удалённых glass-input/glass-textarea)
//
// Цель — быстрая регрессия в watch-режиме vitest и подтверждение, что после
// PHASE 1.5 ни одно нарушение пп.17/18 не попало в репозиторий, а проверка
// самих regex-правил работает корректно (положительные + отрицательные кейсы).

import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, '..', '..', '..', '..');
const APPS = path.join(ROOT, 'apps');
const CORE = path.join(ROOT, 'core');

function _walk(dir, predicate) {
    const out = [];
    if (!existsSync(dir)) return out;
    for (const name of readdirSync(dir)) {
        if (name === 'node_modules' || name === '.git') continue;
        const full = path.join(dir, name);
        const st = statSync(full);
        if (st.isDirectory()) {
            out.push(..._walk(full, predicate));
        } else if (name.endsWith('.js')) {
            if (!predicate || predicate(full)) {
                out.push(full);
            }
        }
    }
    return out;
}

const APPS_UI_FILES = _walk(APPS, (f) => f.includes('/ui/'));

const PILL_CSS_RE = new RegExp(
    String.raw`\.(form-(input|textarea|select|group|label)|field-pill(-(input|textarea|select|label|empty|readonly-text|readonly-muted|readonly-inline)|--(textarea|tags))?)\s*[\{,]`,
);

const GLASS_IMPORT_RE = new RegExp(
    String.raw`['"]@platform/lib/components/glass-(input|textarea)\.js['"]`,
);

const RAW_INPUT_RE = new RegExp(
    String.raw`<input\b(?![^>]*\btype=["'](?:file|hidden|range|color|checkbox|radio|search)["'])(?![^>]*\bclass=["'][^"']*\b(?:form-input|field-pill-input)\b)(?![^>]*\bdata-canon=)[^>]*>`,
    's',
);

const RAW_TEXTAREA_RE = new RegExp(
    String.raw`<textarea\b(?![^>]*\bclass=["'][^"']*\b(?:form-textarea|field-pill-textarea)\b)(?![^>]*\bdata-canon=)[^>]*>`,
    's',
);

const RAW_SELECT_RE = new RegExp(
    String.raw`<select\b(?![^>]*\bclass=["'][^"']*\b(?:form-select|field-pill-select)\b)(?![^>]*\bdata-canon=)[^>]*>`,
    's',
);

describe('check_ui_canon p.17 — локальные .form-*/.field-pill* CSS в apps/**', () => {
    it('ноль нарушений после PHASE 1.5', () => {
        const offenders = [];
        for (const f of APPS_UI_FILES) {
            const src = readFileSync(f, 'utf8');
            if (PILL_CSS_RE.test(src)) {
                offenders.push(path.relative(ROOT, f));
            }
        }
        expect(offenders, `файлы с локальными .form-*/.field-pill* CSS правилами: ${offenders.join(', ')}`).toEqual([]);
    });

    it('regex ловит положительный кейс', () => {
        expect(PILL_CSS_RE.test('css`.form-input { padding: 12px }`')).toBe(true);
        expect(PILL_CSS_RE.test('.field-pill-label, .form-label { color: red }')).toBe(true);
    });

    it('regex не ловит другие имена классов', () => {
        expect(PILL_CSS_RE.test('.tag-input { padding: 0 }')).toBe(false);
        expect(PILL_CSS_RE.test('.field-pill-hint-color')).toBe(false);
    });
});

describe('check_ui_canon p.18 — импорт удалённых glass-input/glass-textarea', () => {
    const FILES = _walk(APPS).concat(_walk(path.join(CORE, 'frontend', 'static', 'lib')));

    it('ноль импортов после удаления компонентов', () => {
        const offenders = [];
        for (const f of FILES) {
            const src = readFileSync(f, 'utf8');
            if (GLASS_IMPORT_RE.test(src)) {
                offenders.push(path.relative(ROOT, f));
            }
        }
        expect(offenders, `файлы с импортом glass-input/glass-textarea: ${offenders.join(', ')}`).toEqual([]);
    });

    it('regex ловит обе формы', () => {
        expect(GLASS_IMPORT_RE.test("import '@platform/lib/components/glass-input.js';")).toBe(true);
        expect(GLASS_IMPORT_RE.test("import x from '@platform/lib/components/glass-textarea.js';")).toBe(true);
    });

    it('regex не ловит другие компоненты', () => {
        expect(GLASS_IMPORT_RE.test("import '@platform/lib/components/glass-button.js';")).toBe(false);
        expect(GLASS_IMPORT_RE.test("import '@platform/lib/components/glass-card.js';")).toBe(false);
    });
});

describe('check_field_canon p.16 — regex для raw <input>/<textarea>/<select>', () => {
    it('ловит сырой <input> без класса', () => {
        expect(RAW_INPUT_RE.test('<input type="text" .value=${x} />')).toBe(true);
    });

    it('пропускает <input class="form-input">', () => {
        expect(RAW_INPUT_RE.test('<input class="form-input" .value=${x} />')).toBe(false);
    });

    it('пропускает <input class="field-pill-input">', () => {
        expect(RAW_INPUT_RE.test('<input class="field-pill-input" />')).toBe(false);
    });

    it('пропускает <input type="file"> и другие whitelisted type', () => {
        for (const t of ['file', 'hidden', 'range', 'color', 'checkbox', 'radio', 'search']) {
            expect(RAW_INPUT_RE.test(`<input type="${t}" />`)).toBe(false);
        }
    });

    it('пропускает <input data-canon="composer">', () => {
        expect(RAW_INPUT_RE.test('<input type="text" data-canon="composer" />')).toBe(false);
    });

    it('ловит сырой <textarea>', () => {
        expect(RAW_TEXTAREA_RE.test('<textarea .value=${x}></textarea>')).toBe(true);
    });

    it('пропускает <textarea class="form-textarea">', () => {
        expect(RAW_TEXTAREA_RE.test('<textarea class="form-textarea"></textarea>')).toBe(false);
    });

    it('пропускает <textarea data-canon="composer">', () => {
        expect(RAW_TEXTAREA_RE.test('<textarea data-canon="composer"></textarea>')).toBe(false);
    });

    it('ловит сырой <select>', () => {
        expect(RAW_SELECT_RE.test('<select .value=${x}></select>')).toBe(true);
    });

    it('пропускает <select class="form-select">', () => {
        expect(RAW_SELECT_RE.test('<select class="form-select"></select>')).toBe(false);
    });

    it('пропускает <select data-canon="combobox">', () => {
        expect(RAW_SELECT_RE.test('<select data-canon="combobox"></select>')).toBe(false);
    });
});
