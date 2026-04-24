/**
 * Сводка ответа POST /flows/api/v1/code/execute для пузыря «Запустить ноду».
 */

function _stringifyValue(val) {
    if (val === null) {
        return 'null';
    }
    if (val === undefined) {
        return 'undefined';
    }
    if (typeof val === 'string') {
        return val;
    }
    return JSON.stringify(val);
}

function _opErrorToMessage(err) {
    if (err === null || err === undefined) {
        return 'Unknown error';
    }
    if (typeof err === 'string') {
        return err;
    }
    if (typeof err.message === 'string' && err.message.length > 0) {
        return err.message;
    }
    return String(err);
}

/**
 * @param {{ opError: unknown, lastResult: unknown }} args
 * @returns {{
 *   kind: 'ok' | 'error',
 *   lines: string[],
 *   durationMs: number | null,
 *   fullPayload: object | null,
 *   canOpenFull: boolean,
 * } | null}
 */
export function formatExecuteViewModel({ opError, lastResult }) {
    if (opError !== null && opError !== undefined) {
        return {
            kind: 'error',
            lines: [_opErrorToMessage(opError)],
            durationMs: null,
            fullPayload: null,
            canOpenFull: false,
        };
    }
    if (lastResult === null || lastResult === undefined) {
        return null;
    }
    if (typeof lastResult !== 'object' || lastResult === null || Array.isArray(lastResult)) {
        throw new Error('formatExecuteViewModel: lastResult must be a plain object');
    }

    const durationRaw = lastResult.duration_ms;
    let durationMs = null;
    if (typeof durationRaw === 'number' && Number.isFinite(durationRaw)) {
        durationMs = durationRaw;
    }

    const success = lastResult.success;
    if (success === false) {
        const err = lastResult.error;
        const line = typeof err === 'string' ? err : JSON.stringify(err);
        return {
            kind: 'error',
            lines: [line],
            durationMs,
            fullPayload: lastResult,
            canOpenFull: true,
        };
    }
    if (success !== true) {
        throw new Error('formatExecuteViewModel: lastResult.success must be boolean');
    }

    const diff = lastResult.diff;
    const lines = [];
    if (Array.isArray(diff)) {
        for (let i = 0; i < diff.length; i += 1) {
            const entry = diff[i];
            if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
                throw new Error('formatExecuteViewModel: diff entry must be an object');
            }
            const path = entry.path;
            const changeType = entry.change_type;
            if (typeof path !== 'string') {
                throw new Error('formatExecuteViewModel: diff entry.path must be a string');
            }
            if (typeof changeType !== 'string') {
                throw new Error('formatExecuteViewModel: diff entry.change_type must be a string');
            }
            const oldVal = 'old_value' in entry ? entry.old_value : undefined;
            const newVal = 'new_value' in entry ? entry.new_value : undefined;
            lines.push(
                `${path} (${changeType}): ${_stringifyValue(oldVal)} \u2192 ${_stringifyValue(newVal)}`,
            );
        }
    } else {
        throw new Error('formatExecuteViewModel: lastResult.diff must be an array');
    }

    return {
        kind: 'ok',
        lines,
        durationMs,
        fullPayload: lastResult,
        canOpenFull: true,
    };
}
