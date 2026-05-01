/**
 * Сопоставление tool_calls и tool results для UI embed-чата (тот же контракт, что у flow chat-message).
 */

function isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * @param {unknown} toolCalls
 * @param {unknown} toolResults
 * @returns {Array<{ call: object|null, result: object|null }>}
 */
export function pairEmbedToolCallsAndResults(toolCalls, toolResults) {
    const calls = Array.isArray(toolCalls) ? toolCalls : [];
    const results = Array.isArray(toolResults) ? toolResults : [];
    const used = new Set();
    const paired = [];
    for (let i = 0; i < calls.length; i++) {
        const call = calls[i];
        let res = null;
        if (isPlainObject(call) && typeof call.id === 'string' && call.id.length > 0) {
            const callId = call.id;
            for (let j = 0; j < results.length; j++) {
                if (used.has(j)) {
                    continue;
                }
                const item = results[j];
                if (
                    isPlainObject(item) &&
                    (item.tool_call_id === callId || item.id === callId)
                ) {
                    res = item;
                    used.add(j);
                    break;
                }
            }
        }
        if (res === null && !used.has(i) && i < results.length) {
            res = results[i];
            used.add(i);
        }
        paired.push({ call, result: res });
    }
    for (let j = 0; j < results.length; j++) {
        if (used.has(j)) {
            continue;
        }
        paired.push({ call: null, result: results[j] });
    }
    return paired;
}

export function embedToolArgsObject(call) {
    if (!isPlainObject(call)) {
        return {};
    }
    if (isPlainObject(call.arguments)) {
        return call.arguments;
    }
    if (isPlainObject(call.args)) {
        return call.args;
    }
    return {};
}

export function embedToolResultBody(result) {
    if (!isPlainObject(result) || !Object.prototype.hasOwnProperty.call(result, 'result')) {
        return '';
    }
    const r = result.result;
    if (typeof r === 'string') {
        return r;
    }
    if (r === null || r === undefined) {
        return '';
    }
    return JSON.stringify(r, null, 2);
}

/**
 * @param {object|null} call
 * @param {object|null} result
 * @param {string} defaultName
 */
export function embedToolRowDisplayName(call, result, defaultName) {
    if (isPlainObject(call) && typeof call.name === 'string' && call.name.length > 0) {
        return call.name;
    }
    if (isPlainObject(result) && typeof result.name === 'string' && result.name.length > 0) {
        return result.name;
    }
    return defaultName;
}

/**
 * @param {object|null} call
 * @param {object|null} result
 * @param {{
 *   tool_hint_tool_name: string,
 *   tool_hint_args_label: string,
 *   tool_hint_result_label: string,
 * }} strings — подстановка `{name}` в tool_hint_tool_name
 * @param {string} defaultName — если имя тула в call/result отсутствует
 */
export function formatEmbedToolPairHintText(call, result, strings, defaultName) {
    const displayName = embedToolRowDisplayName(call, result, defaultName);
    const nameLine = strings.tool_hint_tool_name.replace(/\{name\}/g, displayName);
    const parts = [nameLine];
    if (isPlainObject(call)) {
        const argsLine = JSON.stringify(embedToolArgsObject(call), null, 2);
        parts.push('');
        parts.push(strings.tool_hint_args_label);
        parts.push(argsLine);
    }
    if (isPlainObject(result)) {
        const body = embedToolResultBody(result);
        if (body.length > 0) {
            parts.push('');
            parts.push(strings.tool_hint_result_label);
            parts.push(body);
        }
    }
    return parts.join('\n');
}
