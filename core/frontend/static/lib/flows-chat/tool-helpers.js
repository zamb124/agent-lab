import { toolCallIconName } from '../utils/tool-call-icon.js';

function isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function pairFlowChatToolCallsAndResults(toolCalls, toolResults) {
    const calls = Array.isArray(toolCalls) ? toolCalls : [];
    const results = Array.isArray(toolResults) ? toolResults : [];
    const used = new Set();
    const paired = calls.map((call) => ({ call, result: null }));

    for (let i = 0; i < calls.length; i += 1) {
        const call = calls[i];
        if (isPlainObject(call) && typeof call.id === 'string' && call.id.length > 0) {
            const callId = call.id;
            for (let j = 0; j < results.length; j += 1) {
                if (used.has(j)) {
                    continue;
                }
                const item = results[j];
                if (
                    isPlainObject(item)
                    && (item.tool_call_id === callId || item.id === callId)
                ) {
                    paired[i].result = item;
                    used.add(j);
                    break;
                }
            }
        }
    }

    for (let i = 0; i < calls.length; i += 1) {
        if (paired[i].result !== null) {
            continue;
        }
        const call = calls[i];
        if (isPlainObject(call) && typeof call.name === 'string' && call.name.length > 0) {
            const callName = call.name;
            for (let j = 0; j < results.length; j += 1) {
                if (used.has(j)) {
                    continue;
                }
                const item = results[j];
                if (!isPlainObject(item)) {
                    continue;
                }
                const resultName =
                    typeof item.name === 'string' && item.name.length > 0
                        ? item.name
                        : typeof item.tool === 'string' && item.tool.length > 0
                          ? item.tool
                          : '';
                if (resultName === callName) {
                    paired[i].result = item;
                    used.add(j);
                    break;
                }
            }
        }
    }

    for (let i = 0; i < paired.length; i += 1) {
        if (paired[i].result !== null) {
            continue;
        }
        for (let j = 0; j < results.length; j += 1) {
            if (used.has(j)) {
                continue;
            }
            paired[i].result = results[j];
            used.add(j);
            break;
        }
    }
    for (let j = 0; j < results.length; j += 1) {
        if (used.has(j)) {
            continue;
        }
        paired.push({ call: null, result: results[j] });
    }
    return paired;
}

export function flowChatToolArgsObject(call) {
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

export function flowChatToolResultBody(result) {
    if (!isPlainObject(result)) {
        return '';
    }
    const valueKeys = ['result', 'value', 'output', 'content', 'data'];
    let hasValue = false;
    let value;
    for (const key of valueKeys) {
        if (Object.prototype.hasOwnProperty.call(result, key)) {
            hasValue = true;
            value = result[key];
            break;
        }
    }
    if (!hasValue) {
        const body = {};
        for (const [key, item] of Object.entries(result)) {
            if (key === 'id' || key === 'tool_call_id' || key === 'name' || key === 'tool') {
                continue;
            }
            body[key] = item;
        }
        if (Object.keys(body).length === 0) {
            return '';
        }
        return JSON.stringify(body, null, 2);
    }
    if (typeof value === 'string') {
        return value;
    }
    if (value === null || value === undefined) {
        return '';
    }
    return JSON.stringify(value, null, 2);
}

export function flowChatToolRowDisplayName(call, result, defaultName) {
    if (isPlainObject(call) && typeof call.name === 'string' && call.name.length > 0) {
        return call.name;
    }
    if (isPlainObject(result) && typeof result.name === 'string' && result.name.length > 0) {
        return result.name;
    }
    return typeof defaultName === 'string' && defaultName.length > 0 ? defaultName : 'tool';
}

export function flowChatToolRowId(call, result) {
    if (isPlainObject(call) && typeof call.id === 'string' && call.id.length > 0) {
        return call.id;
    }
    if (isPlainObject(result) && typeof result.id === 'string' && result.id.length > 0) {
        return result.id;
    }
    if (isPlainObject(result) && typeof result.tool_call_id === 'string' && result.tool_call_id.length > 0) {
        return result.tool_call_id;
    }
    return '';
}

function _formatToolNameLine(formatter, displayName) {
    if (typeof formatter === 'function') {
        return String(formatter(displayName));
    }
    if (typeof formatter === 'string') {
        return formatter.replace(/\{name\}/g, displayName);
    }
    return displayName;
}

export function formatFlowChatToolPairHintText(call, result, strings, defaultName) {
    const source = strings && typeof strings === 'object' ? strings : {};
    const displayName = flowChatToolRowDisplayName(call, result, defaultName);
    const parts = [_formatToolNameLine(source.tool_hint_tool_name, displayName)];
    if (isPlainObject(call)) {
        const argsLine = JSON.stringify(flowChatToolArgsObject(call), null, 2);
        parts.push('');
        parts.push(typeof source.tool_hint_args_label === 'string' ? source.tool_hint_args_label : 'Arguments:');
        parts.push(argsLine);
    }
    if (isPlainObject(result)) {
        const body = flowChatToolResultBody(result);
        if (body.length > 0) {
            parts.push('');
            parts.push(typeof source.tool_hint_result_label === 'string' ? source.tool_hint_result_label : 'Result:');
            parts.push(body);
        }
    }
    return parts.join('\n');
}

export { toolCallIconName };
