import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const rootDir = fileURLToPath(new URL('../../../../', import.meta.url));

describe('flows operator i18n', () => {
    it('ru and en define kanban status keys under operator', () => {
        const ru = JSON.parse(
            readFileSync(path.join(rootDir, 'core/i18n/translations/ru/flows.json'), 'utf8'),
        );
        const en = JSON.parse(
            readFileSync(path.join(rootDir, 'core/i18n/translations/en/flows.json'), 'utf8'),
        );
        const keys = [
            'status_open',
            'status_claimed',
            'status_user_dialog',
            'status_awaiting_agent',
            'status_completed',
            'status_cancelled',
        ];
        for (const k of keys) {
            expect(typeof ru.operator[k] === 'string' && ru.operator[k].length > 0).toBe(true);
            expect(typeof en.operator[k] === 'string' && en.operator[k].length > 0).toBe(true);
        }
    });
});
