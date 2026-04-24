/**
 * Кто последний вызвал flows/code_execute — чтобы пузырь результата показывался
 * только у того экземпляра flows-node-run-control (а не у всех на странице).
 */

let _seq = 0;
let _lastRequestClientId = null;

export function nextCodeExecuteClientId() {
    _seq += 1;
    return `ce_${_seq}`;
}

export function setCodeExecuteRequestClientId(id) {
    if (typeof id !== 'string' || id.length === 0) {
        throw new Error('flows-code-execute-run-gate: client id must be a non-empty string');
    }
    _lastRequestClientId = id;
}

export function getCodeExecuteRequestClientId() {
    return _lastRequestClientId;
}
