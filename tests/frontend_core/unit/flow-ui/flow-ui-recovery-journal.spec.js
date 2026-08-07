import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
    clearRecoveryJournal,
    readRecoveryJournal,
    recoveryJournalKey,
    writeRecoveryJournal,
} from '../../../../core/frontend/static/lib/flow-ui/runtime/flow-ui-recovery-journal.js';

const target = Object.freeze({
    flowId: 'flow-journal-1',
    branchId: 'default',
    contextId: 'context-journal-1',
});

function installMemoryLocalStorage() {
    const rows = new Map();
    globalThis.localStorage = {
        getItem(key) {
            return rows.has(key) ? rows.get(key) : null;
        },
        setItem(key, value) {
            rows.set(String(key), String(value));
        },
        removeItem(key) {
            rows.delete(key);
        },
        clear() {
            rows.clear();
        },
    };
}

beforeEach(() => {
    installMemoryLocalStorage();
});

afterEach(() => {
    clearRecoveryJournal(target);
});

describe('Flow UI recovery journal', () => {
    it('scopes journal keys by flow/branch/context', () => {
        expect(recoveryJournalKey(target)).toBe(
            'linnex.flow-ui.journal.v1:flow:flow-journal-1:default:context-journal-1',
        );
        expect(
            recoveryJournalKey({
                embedId: 'embed-1',
                branchId: 'release',
                contextId: 'ctx-2',
            }),
        ).toBe('linnex.flow-ui.journal.v1:embed:embed-1:release:ctx-2');
    });

    it('persists pending mutations and clears them after empty write', () => {
        const mutations = [
            {
                clientMutationId: 'm1',
                revision: 2,
                values: { message: 'draft' },
            },
        ];
        writeRecoveryJournal(target, mutations);
        expect(readRecoveryJournal(target)).toEqual(mutations);
        clearRecoveryJournal(target);
        expect(readRecoveryJournal(target)).toEqual([]);
    });
});
