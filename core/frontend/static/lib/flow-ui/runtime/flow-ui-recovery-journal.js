const PREFIX = 'linnex.flow-ui.journal.v1';

function storage() {
    try { return globalThis.localStorage || null; } catch { return null; }
}

export function recoveryJournalKey({ flowId = '', embedId = '', branchId = 'default', contextId }) {
    return [PREFIX, embedId ? `embed:${embedId}` : `flow:${flowId}`, branchId, contextId].join(':');
}

export function readRecoveryJournal(target) {
    const store = storage();
    if (!store || !target.contextId) return [];
    try {
        const value = JSON.parse(store.getItem(recoveryJournalKey(target)) || '[]');
        return Array.isArray(value) ? value : [];
    } catch { return []; }
}

export function writeRecoveryJournal(target, mutations) {
    const store = storage();
    if (!store || !target.contextId) return;
    if (!Array.isArray(mutations) || mutations.length === 0) {
        store.removeItem(recoveryJournalKey(target));
        return;
    }
    store.setItem(recoveryJournalKey(target), JSON.stringify(mutations));
}

export function clearRecoveryJournal(target) {
    writeRecoveryJournal(target, []);
}
