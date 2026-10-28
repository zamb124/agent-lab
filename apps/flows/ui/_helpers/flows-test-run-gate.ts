/**
 * Кто последний вызвал test-run Play — чтобы пузырь результата показывался
 * только у того экземпляра flows-node-run-control (а не у всех на странице).
 */

let _seq = 0;
let _lastRequestClientId: string | null = null;

export function nextTestRunClientId() {
    _seq += 1;
    return `tr_${_seq}`;
}

export function setTestRunRequestClientId(id: string) {
    if (typeof id !== 'string' || id.length === 0) {
        throw new Error('flows-test-run-gate: client id must be a non-empty string');
    }
    _lastRequestClientId = id;
}

export function getTestRunRequestClientId() {
    return _lastRequestClientId;
}
