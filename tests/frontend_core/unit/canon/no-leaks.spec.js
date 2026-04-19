/**
 * Канон-тест «no leaks»: дополнительная проверка для DX.
 *
 * Дублирует часть scripts/check_core_frontend_canon.py:
 *   - в core/frontend/static/lib/events/** нет ServiceRegistry/BaseStore/AppEvents/Zustand;
 *   - reducers и factories не используют `|| []`, `|| {}`, `?? '...'` фолбеки на чтение;
 *   - в core/frontend/static/lib/events/** нет `extends LitElement`.
 *
 * Цель — мгновенный фидбек в watch-режиме: если кто-то добавит фолбек в reducer
 * прямо сейчас, тест упадёт, не дожидаясь Python-канона.
 */

import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const LIB = path.resolve(here, '..', '..', '..', '..', 'core', 'frontend', 'static', 'lib');

function _walk(dir) {
    const out = [];
    for (const name of readdirSync(dir)) {
        if (name === 'embed-chat') continue;
        const full = path.join(dir, name);
        if (statSync(full).isDirectory()) {
            out.push(..._walk(full));
        } else if (name.endsWith('.js')) {
            out.push(full);
        }
    }
    return out;
}

const EVENTS_FILES = _walk(path.join(LIB, 'events'));
const REDUCER_AND_FACTORY_FILES = EVENTS_FILES.filter((f) => /\/(reducers|factories)\//.test(f) && !/(_internal|_transport|register)\.js$/.test(f));

const FALLBACK_RE = /\)\s*\|\|\s*(\[\]|\{\}|null)|\?\?\s*(\[\]|\{\}|null|['"][^'"]*['"])/;
const LEGACY_NAMES = /\b(ServiceRegistry|BaseStore|BaseService|AppEvents|Zustand)\b/;
const EXTENDS_LIT = /\bextends\s+(LitElement|HTMLElement)\b/;

describe('canon: no leaks in events/**', () => {
    it('собрали хоть какие-то файлы (sanity)', () => {
        expect(EVENTS_FILES.length).toBeGreaterThan(20);
        expect(REDUCER_AND_FACTORY_FILES.length).toBeGreaterThan(15);
    });

    it('в events/** нет ServiceRegistry/BaseStore/AppEvents/Zustand', () => {
        const violations = [];
        for (const file of EVENTS_FILES) {
            const text = readFileSync(file, 'utf8');
            if (LEGACY_NAMES.test(text)) {
                violations.push(path.relative(LIB, file));
            }
        }
        expect(violations).toEqual([]);
    });

    it('в events/** нет extends LitElement / HTMLElement', () => {
        const violations = [];
        for (const file of EVENTS_FILES) {
            const text = readFileSync(file, 'utf8');
            if (EXTENDS_LIT.test(text)) {
                violations.push(path.relative(LIB, file));
            }
        }
        expect(violations).toEqual([]);
    });

    it('в reducers/** и factories/** нет фолбеков `|| []`, `?? null`, `?? "..."`', () => {
        const violations = [];
        for (const file of REDUCER_AND_FACTORY_FILES) {
            const text = readFileSync(file, 'utf8');
            const cleaned = text
                .replace(/\/\*[\s\S]*?\*\//g, '')
                .replace(/^\s*\*[^\n]*$/gm, '')
                .replace(/(^|[^:\\])\/\/[^\n]*/g, (m, p1) => p1);
            const m = cleaned.match(FALLBACK_RE);
            if (m) {
                const line = cleaned.slice(0, m.index).split('\n').length;
                violations.push(`${path.relative(LIB, file)}:${line}`);
            }
        }
        expect(violations).toEqual([]);
    });
});
