import { getCachedSortedIanaTimeZones } from '@platform/lib/utils/iana-timezones.js';

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

function isObject(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function unwrapFlowVariable(value: unknown): unknown {
    if (isObject(value) && Object.hasOwn(value, 'value')) return value.value;
    return value;
}

function twoDigits(value: unknown) {
    return String(value).padStart(2, '0');
}

export function buildRuntimeDatetimePreview(now = new Date(), timeZone: string | null = null) {
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
        if (!getCachedSortedIanaTimeZones().includes(timeZone)) {
            throw new Error(`buildRuntimeDatetimePreview: unknown timeZone "${timeZone}"`);
        }
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

function typeOf(value: unknown, fallback = 'any') {
    if (value === null) return 'null';
    if (Array.isArray(value)) return 'array';
    if (value !== undefined) return typeof value;
    return fallback || 'any';
}

function descriptorAvailability(descriptor: Record<string, unknown>): string {
    const availability = descriptor.availability;
    if (typeof availability !== 'string' || availability === '') return 'guaranteed';
    return availability;
}

function sampleFromDescriptor(descriptor: unknown) {
    if (!isObject(descriptor) || !Object.hasOwn(descriptor, 'sample_value')) {
        return { hasValue: false, value: undefined };
    }
    const value = descriptor.sample_value;
    if (value === null || value === '<secret>') return { hasValue: false, value: undefined };
    return { hasValue: true, value };
}

/**
 * Builds the exact prompt namespace for one LLM node.
 * Precedence mirrors runtime: system < flow/state variables < interface fields < input_mapping < node locals.
 * Interface inputs write plain top-level state paths (`field: "email"` → `{email}`), the dataflow
 * inspector marks them with `source: "interface"`.
 */
export function buildPromptVariableContext({
    flowVariables = {},
    nodeLocalVariables = {},
    dataflowNode = null,
    previewExecutionState = null,
    now = new Date(),
}: {
    flowVariables?: Record<string, unknown> | null;
    nodeLocalVariables?: Record<string, unknown> | null;
    dataflowNode?: Record<string, unknown> | null;
    previewExecutionState?: Record<string, unknown> | null;
    now?: Date;
} = {}) {
    const entries = new Map<string, {
        name: string;
        source: string;
        type: string;
        availability: string;
        hasValue: boolean;
    }>();
    const values: Record<string, unknown> = {};

    const put = (name: string, entry: {
        value?: unknown;
        hasValue?: boolean;
        source: string;
        type?: string;
        availability?: string;
    }) => {
        if (typeof name !== 'string' || name.length === 0) return;
        const hasValue = entry.hasValue !== false;
        const type = entry.type === undefined ? 'any' : entry.type;
        const availability = entry.availability === undefined ? 'guaranteed' : entry.availability;
        entries.set(name, { name, source: entry.source, type: typeOf(entry.value, type), availability, hasValue });
        if (hasValue) values[name] = entry.value;
        else delete values[name];
    };

    const isInterfaceDescriptor = (descriptor: Record<string, unknown>) => {
        const source = descriptor.source;
        return source === 'interface' || (Array.isArray(source) && source.includes('interface'));
    };
    const interfaceFields = [];

    const previewStore = previewExecutionState === null || previewExecutionState === undefined
        ? null
        : previewExecutionState.store;
    const previewTimezone = isObject(previewStore) && typeof previewStore.timezone === 'string'
        ? previewStore.timezone
        : null;
    const datetimeValues: Record<string, string | number> = buildRuntimeDatetimePreview(now, previewTimezone);
    for (const name of RUNTIME_SYSTEM_KEYS) {
        const hasValue = Object.hasOwn(datetimeValues, name);
        const value = datetimeValues[name];
        put(name, {
            value,
            hasValue,
            source: 'system',
            type: name.startsWith('current_') ? typeOf(value, 'string') : 'string',
            availability: 'runtime',
        });
    }

    if (isObject(flowVariables)) {
        for (const [name, config] of Object.entries(flowVariables)) {
            const value = unwrapFlowVariable(config);
            put(name, { value, source: 'flow', type: typeOf(value) });
        }
    }

    const incomingState = dataflowNode === null || dataflowNode === undefined ? undefined : dataflowNode.incoming_state;
    const incoming = isObject(dataflowNode) && Array.isArray(incomingState)
        ? incomingState
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
                availability: descriptorAvailability(descriptor),
            });
            continue;
        }
        if (isInterfaceDescriptor(descriptor)) {
            const field = descriptor.path;
            if (field.includes('.')) continue;
            interfaceFields.push(field);
            const sample = sampleFromDescriptor(descriptor);
            put(field, {
                value: sample.value,
                hasValue: sample.hasValue,
                source: 'interface',
                type: typeof descriptor.type === 'string' ? descriptor.type : 'any',
                availability: descriptorAvailability(descriptor),
            });
        }
    }

    const previewVariables = previewExecutionState === null || previewExecutionState === undefined
        ? undefined
        : previewExecutionState.variables;
    if (isObject(previewExecutionState) && isObject(previewVariables)) {
        for (const [name, value] of Object.entries(previewVariables)) {
            put(name, { value: unwrapFlowVariable(value), source: 'preview', type: typeOf(value), availability: 'observed' });
        }
    }

    if (isObject(previewExecutionState)) {
        for (const field of interfaceFields) {
            if (!Object.hasOwn(previewExecutionState, field)) continue;
            const value = previewExecutionState[field];
            put(field, { value, source: 'interface', type: typeOf(value), availability: 'observed' });
        }
    }

    const inputMapping = dataflowNode === null || dataflowNode === undefined ? undefined : dataflowNode.input_mapping;
    const mappings = isObject(dataflowNode) && Array.isArray(inputMapping)
        ? inputMapping
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
            const sourceOrder: Record<string, number> = {
                local: 0,
                input: 1,
                interface: 2,
                upstream: 2,
                preview: 2,
                flow: 3,
                system: 4,
            };
            const left = sourceOrder[a.source];
            const right = sourceOrder[b.source];
            if (left === undefined || right === undefined) {
                throw new Error(`prompt variable catalog: unknown source "${left === undefined ? a.source : b.source}"`);
            }
            return left - right || a.name.localeCompare(b.name);
        }),
    };
}
