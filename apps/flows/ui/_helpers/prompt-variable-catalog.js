const RUNTIME_SYSTEM_KEYS = Object.freeze([
    'current_date',
    'current_time',
    'current_datetime',
    'current_year',
    'current_month',
    'current_day',
    'user_name',
    'user_id',
    'user_email',
]);

function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function unwrapFlowVariable(value) {
    if (isObject(value) && Object.hasOwn(value, 'value')) return value.value;
    return value;
}

function twoDigits(value) {
    return String(value).padStart(2, '0');
}

export function buildRuntimeDatetimePreview(now = new Date(), timeZone = null) {
    if (!(now instanceof Date) || Number.isNaN(now.getTime())) {
        throw new TypeError('buildRuntimeDatetimePreview: valid Date required');
    }
    let year = now.getFullYear();
    let month = now.getMonth() + 1;
    let day = now.getDate();
    let hours = now.getHours();
    let minutes = now.getMinutes();
    let seconds = now.getSeconds();
    if (typeof timeZone === 'string' && timeZone.length > 0) {
        try {
            const parts = new Intl.DateTimeFormat('en-GB', {
                timeZone,
                year: 'numeric', month: '2-digit', day: '2-digit',
                hour: '2-digit', minute: '2-digit', second: '2-digit',
                hourCycle: 'h23',
            }).formatToParts(now);
            const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
            year = Number(byType.year);
            month = Number(byType.month);
            day = Number(byType.day);
            hours = Number(byType.hour);
            minutes = Number(byType.minute);
            seconds = Number(byType.second);
        } catch {
            // Runtime also falls back to local time for an invalid timezone.
        }
    }
    const date = `${year}-${twoDigits(month)}-${twoDigits(day)}`;
    const time = `${twoDigits(hours)}:${twoDigits(minutes)}`;
    return {
        current_date: date,
        current_time: time,
        current_datetime: `${date} ${time}:${twoDigits(seconds)}`,
        current_year: year,
        current_month: month,
        current_day: day,
    };
}

function typeOf(value, fallback = 'any') {
    if (value === null) return 'null';
    if (Array.isArray(value)) return 'array';
    if (value !== undefined) return typeof value;
    return fallback || 'any';
}

function sampleFromDescriptor(descriptor) {
    if (!isObject(descriptor) || !Object.hasOwn(descriptor, 'sample_value')) {
        return { hasValue: false, value: undefined };
    }
    const value = descriptor.sample_value;
    if (value === null || value === '<secret>') return { hasValue: false, value: undefined };
    return { hasValue: true, value };
}

/**
 * Builds the exact prompt namespace for one LLM node.
 * Precedence mirrors runtime: system < flow/state variables < ui_values < input_mapping < node locals.
 * Flow UI fields appear as nested `values.ui_values` and catalog names `ui_values.<field>`
 * (inserts `{ui_values.field}` — same path as ExecutionState / Logic chips).
 */
export function buildPromptVariableContext({
    flowVariables = {},
    nodeLocalVariables = {},
    dataflowNode = null,
    previewExecutionState = null,
    now = new Date(),
} = {}) {
    const entries = new Map();
    const values = {};

    const put = (name, { value, hasValue = true, source, type = 'any', availability = 'guaranteed' }) => {
        if (typeof name !== 'string' || name.length === 0) return;
        entries.set(name, { name, source, type: typeOf(value, type), availability, hasValue });
        if (hasValue) values[name] = value;
        else delete values[name];
    };

    const putUiValue = (field, { value, hasValue = true, source, type = 'any', availability = 'guaranteed' }) => {
        if (typeof field !== 'string' || field.length === 0 || field.includes('.')) return;
        const name = `ui_values.${field}`;
        entries.set(name, { name, source, type: typeOf(value, type), availability, hasValue });
        if (!isObject(values.ui_values)) values.ui_values = {};
        if (hasValue) values.ui_values[field] = value;
        else delete values.ui_values[field];
    };

    const previewTimezone = isObject(previewExecutionState?.store)
        && typeof previewExecutionState.store.timezone === 'string'
        ? previewExecutionState.store.timezone
        : null;
    const datetimeValues = buildRuntimeDatetimePreview(now, previewTimezone);
    for (const name of RUNTIME_SYSTEM_KEYS) {
        const hasValue = Object.hasOwn(datetimeValues, name);
        put(name, {
            value: datetimeValues[name],
            hasValue,
            source: 'system',
            type: name.startsWith('current_') ? typeOf(datetimeValues[name], 'string') : 'string',
            availability: 'runtime',
        });
    }

    if (isObject(flowVariables)) {
        for (const [name, config] of Object.entries(flowVariables)) {
            const value = unwrapFlowVariable(config);
            put(name, { value, source: 'flow', type: typeOf(value) });
        }
    }

    const incoming = isObject(dataflowNode) && Array.isArray(dataflowNode.incoming_state)
        ? dataflowNode.incoming_state
        : [];
    for (const descriptor of incoming) {
        if (!isObject(descriptor) || typeof descriptor.path !== 'string') continue;
        if (descriptor.path.startsWith('variables.')) {
            const name = descriptor.path.slice('variables.'.length);
            if (!name || name.includes('.')) continue;
            const sample = sampleFromDescriptor(descriptor);
            put(name, {
                value: sample.value,
                hasValue: sample.hasValue,
                source: 'upstream',
                type: typeof descriptor.type === 'string' ? descriptor.type : 'any',
                availability: descriptor.availability || 'guaranteed',
            });
            continue;
        }
        if (descriptor.path.startsWith('ui_values.')) {
            const field = descriptor.path.slice('ui_values.'.length);
            if (!field || field.includes('.')) continue;
            const sample = sampleFromDescriptor(descriptor);
            putUiValue(field, {
                value: sample.value,
                hasValue: sample.hasValue,
                source: 'ui_value',
                type: typeof descriptor.type === 'string' ? descriptor.type : 'any',
                availability: descriptor.availability || 'guaranteed',
            });
        }
    }

    if (isObject(previewExecutionState) && isObject(previewExecutionState.variables)) {
        for (const [name, value] of Object.entries(previewExecutionState.variables)) {
            put(name, { value: unwrapFlowVariable(value), source: 'preview', type: typeOf(value), availability: 'observed' });
        }
    }

    if (isObject(previewExecutionState) && isObject(previewExecutionState.ui_values)) {
        for (const [field, value] of Object.entries(previewExecutionState.ui_values)) {
            putUiValue(field, {
                value: unwrapFlowVariable(value),
                source: 'ui_value',
                type: typeOf(value),
                availability: 'observed',
            });
        }
    }

    const mappings = isObject(dataflowNode) && Array.isArray(dataflowNode.input_mapping)
        ? dataflowNode.input_mapping
        : [];
    for (const row of mappings) {
        if (!isObject(row) || row.status !== 'ok' || typeof row.target !== 'string' || row.target.length === 0) continue;
        const sample = sampleFromDescriptor(row);
        put(row.target, {
            value: sample.value,
            hasValue: sample.hasValue,
            source: 'input',
            type: typeof row.type === 'string' ? row.type : 'any',
            availability: sample.hasValue ? 'observed' : 'guaranteed',
        });
    }

    if (isObject(nodeLocalVariables)) {
        for (const [name, value] of Object.entries(nodeLocalVariables)) {
            put(name, { value: unwrapFlowVariable(value), source: 'local', type: typeOf(value) });
        }
    }

    return {
        values,
        catalog: [...entries.values()].sort((a, b) => {
            const sourceOrder = {
                local: 0,
                input: 1,
                ui_value: 2,
                upstream: 2,
                preview: 2,
                flow: 3,
                system: 4,
            };
            return (sourceOrder[a.source] ?? 9) - (sourceOrder[b.source] ?? 9) || a.name.localeCompare(b.name);
        }),
    };
}
