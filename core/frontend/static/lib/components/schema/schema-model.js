/**
 * Pure helpers: JSON Schema object ↔ parameter rows for <platform-schema-editor>.
 * Visual Form covers a tool-schema subset; advanced constructs stay in JSON mode.
 */

export const SCHEMA_KEY_RE = /^[a-zA-Z_][a-zA-Z0-9_]*$/;

/** @typedef {'string'|'number'|'integer'|'boolean'|'enum'|'object'|'array'} SchemaUiType */

export const SCHEMA_UI_TYPES = Object.freeze([
    'string',
    'number',
    'integer',
    'boolean',
    'enum',
    'object',
    'array',
]);

const SCALAR_JSON_TYPES = new Set(['string', 'number', 'integer', 'boolean']);

/**
 * @returns {{
 *   key: string,
 *   required: boolean,
 *   uiType: SchemaUiType,
 *   description: string,
 *   enumValues: string[],
 *   itemsUiType: 'string'|'number'|'integer'|'boolean'|'enum',
 *   itemsEnumValues: string[],
 *   nestedRows: Array<{
 *     key: string,
 *     required: boolean,
 *     uiType: 'string'|'number'|'integer'|'boolean'|'enum',
 *     description: string,
 *     enumValues: string[],
 *     extra: Record<string, unknown>,
 *   }>,
 *   extra: Record<string, unknown>,
 * }}
 */
export function createEmptyParameterRow() {
    return {
        key: '',
        required: false,
        uiType: 'string',
        description: '',
        enumValues: [],
        itemsUiType: 'string',
        itemsEnumValues: [],
        nestedRows: [],
        extra: {},
    };
}

/**
 * @param {unknown} value
 * @returns {value is Record<string, unknown>}
 */
function isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * @param {unknown} raw
 * @returns {string[]}
 */
function normalizeStringList(raw) {
    if (!Array.isArray(raw)) {
        return [];
    }
    return raw
        .map((item) => (typeof item === 'string' ? item.trim() : ''))
        .filter((item) => item.length > 0);
}

/**
 * @param {unknown} raw
 * @returns {{ type: 'object', properties: Record<string, unknown>, required: string[], rest: Record<string, unknown> }}
 */
export function normalizeParametersSchema(raw) {
    if (raw === null || raw === undefined) {
        return { type: 'object', properties: {}, required: [], rest: {} };
    }
    if (!isPlainObject(raw)) {
        throw new Error('parameters schema must be a JSON object');
    }
    const type = raw.type;
    if (type !== undefined && type !== 'object') {
        throw new Error('parameters schema root type must be object');
    }
    const propertiesRaw = raw.properties;
    const properties =
        propertiesRaw === undefined
            ? {}
            : isPlainObject(propertiesRaw)
              ? { ...propertiesRaw }
              : (() => {
                    throw new Error('parameters schema.properties must be an object');
                })();
    const requiredRaw = raw.required;
    const required = requiredRaw === undefined
        ? []
        : Array.isArray(requiredRaw)
          ? requiredRaw.filter((item) => typeof item === 'string' && item.length > 0)
          : (() => {
                throw new Error('parameters schema.required must be an array');
            })();
    const rest = {};
    for (const [key, value] of Object.entries(raw)) {
        if (key === 'type' || key === 'properties' || key === 'required') {
            continue;
        }
        rest[key] = value;
    }
    return { type: 'object', properties, required, rest };
}

/**
 * @param {unknown} prop
 * @returns {SchemaUiType}
 */
function propertyUiType(prop) {
    if (!isPlainObject(prop)) {
        return 'string';
    }
    if (Array.isArray(prop.enum) && prop.enum.length > 0) {
        return 'enum';
    }
    const type = prop.type;
    if (type === 'number' || type === 'integer' || type === 'boolean' || type === 'object' || type === 'array') {
        return type;
    }
    return 'string';
}

/**
 * @param {unknown} prop
 * @returns {Record<string, unknown>}
 */
function propertyExtra(prop) {
    if (!isPlainObject(prop)) {
        return {};
    }
    const reserved = new Set(['type', 'description', 'enum', 'items', 'properties', 'required']);
    const extra = {};
    for (const [key, value] of Object.entries(prop)) {
        if (reserved.has(key)) {
            continue;
        }
        extra[key] = value;
    }
    return extra;
}

/**
 * @param {string} key
 * @param {unknown} prop
 * @param {Set<string>} requiredSet
 */
function nestedPropertyToRow(key, prop, requiredSet) {
    const uiType = propertyUiType(prop);
    if (uiType === 'object' || uiType === 'array') {
        throw new Error(`nested property "${key}" must be a scalar or enum`);
    }
    const description =
        isPlainObject(prop) && typeof prop.description === 'string' ? prop.description : '';
    const enumValues =
        isPlainObject(prop) && Array.isArray(prop.enum) ? normalizeStringList(prop.enum) : [];
    return {
        key,
        required: requiredSet.has(key),
        uiType,
        description,
        enumValues,
        extra: propertyExtra(prop),
    };
}

/**
 * @param {string} key
 * @param {unknown} prop
 * @param {Set<string>} requiredSet
 */
export function schemaPropertyToRow(key, prop, requiredSet) {
    const row = createEmptyParameterRow();
    row.key = key;
    row.required = requiredSet.has(key);
    if (!isPlainObject(prop)) {
        row.extra = {};
        return row;
    }
    row.description = typeof prop.description === 'string' ? prop.description : '';
    row.extra = propertyExtra(prop);
    const uiType = propertyUiType(prop);
    row.uiType = uiType;
    if (uiType === 'enum') {
        row.enumValues = normalizeStringList(prop.enum);
        return row;
    }
    if (uiType === 'array') {
        const items = prop.items;
        if (isPlainObject(items)) {
            if (Array.isArray(items.enum) && items.enum.length > 0) {
                row.itemsUiType = 'enum';
                row.itemsEnumValues = normalizeStringList(items.enum);
            } else if (
                items.type === 'number'
                || items.type === 'integer'
                || items.type === 'boolean'
                || items.type === 'string'
            ) {
                row.itemsUiType = items.type;
            } else {
                row.itemsUiType = 'string';
            }
        }
        return row;
    }
    if (uiType === 'object') {
        const nestedProps = isPlainObject(prop.properties) ? prop.properties : {};
        const nestedRequired = new Set(
            Array.isArray(prop.required)
                ? prop.required.filter((item) => typeof item === 'string')
                : [],
        );
        row.nestedRows = Object.entries(nestedProps).map(([nestedKey, nestedProp]) =>
            nestedPropertyToRow(nestedKey, nestedProp, nestedRequired),
        );
        return row;
    }
    return row;
}

/**
 * @param {{ type: 'object', properties: Record<string, unknown>, required: string[], rest: Record<string, unknown> }} normalized
 */
export function schemaToParameterRows(normalized) {
    const requiredSet = new Set(normalized.required);
    return Object.entries(normalized.properties).map(([key, prop]) =>
        schemaPropertyToRow(key, prop, requiredSet),
    );
}

/**
 * @param {{
 *   key: string,
 *   required: boolean,
 *   uiType: string,
 *   description: string,
 *   enumValues: string[],
 *   extra?: Record<string, unknown>,
 * }} nested
 * @returns {Record<string, unknown>}
 */
function nestedRowToProperty(nested) {
    const descriptor = {
        ...(nested.extra && typeof nested.extra === 'object' ? nested.extra : {}),
    };
    if (nested.uiType === 'enum') {
        descriptor.type = 'string';
        descriptor.enum = [...nested.enumValues];
    } else {
        descriptor.type = nested.uiType;
    }
    const description = typeof nested.description === 'string' ? nested.description.trim() : '';
    if (description.length > 0) {
        descriptor.description = description;
    } else {
        delete descriptor.description;
    }
    return descriptor;
}

/**
 * @param {ReturnType<typeof createEmptyParameterRow>} row
 * @returns {Record<string, unknown>}
 */
export function parameterRowToProperty(row) {
    const descriptor = {
        ...(row.extra && typeof row.extra === 'object' ? row.extra : {}),
    };
    const description = typeof row.description === 'string' ? row.description.trim() : '';
    if (description.length > 0) {
        descriptor.description = description;
    } else {
        delete descriptor.description;
    }

    if (row.uiType === 'enum') {
        descriptor.type = 'string';
        descriptor.enum = [...row.enumValues];
        delete descriptor.items;
        delete descriptor.properties;
        delete descriptor.required;
        return descriptor;
    }
    if (row.uiType === 'array') {
        descriptor.type = 'array';
        if (row.itemsUiType === 'enum') {
            descriptor.items = { type: 'string', enum: [...row.itemsEnumValues] };
        } else {
            descriptor.items = { type: row.itemsUiType };
        }
        delete descriptor.enum;
        delete descriptor.properties;
        delete descriptor.required;
        return descriptor;
    }
    if (row.uiType === 'object') {
        descriptor.type = 'object';
        const properties = {};
        const required = [];
        for (const nested of row.nestedRows) {
            const nestedKey = typeof nested.key === 'string' ? nested.key.trim() : '';
            if (nestedKey.length === 0) {
                continue;
            }
            properties[nestedKey] = nestedRowToProperty(nested);
            if (nested.required) {
                required.push(nestedKey);
            }
        }
        descriptor.properties = properties;
        if (required.length > 0) {
            descriptor.required = required;
        } else {
            delete descriptor.required;
        }
        delete descriptor.enum;
        delete descriptor.items;
        return descriptor;
    }
    descriptor.type = row.uiType;
    delete descriptor.enum;
    delete descriptor.items;
    delete descriptor.properties;
    delete descriptor.required;
    return descriptor;
}

/**
 * @param {Array<ReturnType<typeof createEmptyParameterRow>>} rows
 * @returns {{ valid: true } | { valid: false, error: string }}
 */
export function validateParameterRows(rows) {
    if (!Array.isArray(rows)) {
        return { valid: false, error: 'parameter rows must be an array' };
    }
    const seen = new Set();
    for (const row of rows) {
        const key = typeof row.key === 'string' ? row.key.trim() : '';
        if (key.length === 0) {
            continue;
        }
        if (!SCHEMA_KEY_RE.test(key)) {
            return { valid: false, error: `invalid parameter key: ${key}` };
        }
        if (seen.has(key)) {
            return { valid: false, error: `duplicate parameter key: ${key}` };
        }
        seen.add(key);
        if (row.uiType === 'enum' && (!Array.isArray(row.enumValues) || row.enumValues.length === 0)) {
            return { valid: false, error: `enum parameter "${key}" needs at least one value` };
        }
        if (
            row.uiType === 'array'
            && row.itemsUiType === 'enum'
            && (!Array.isArray(row.itemsEnumValues) || row.itemsEnumValues.length === 0)
        ) {
            return { valid: false, error: `array enum parameter "${key}" needs at least one item value` };
        }
        if (row.uiType === 'object' && Array.isArray(row.nestedRows)) {
            const nestedSeen = new Set();
            for (const nested of row.nestedRows) {
                const nestedKey = typeof nested.key === 'string' ? nested.key.trim() : '';
                if (nestedKey.length === 0) {
                    continue;
                }
                if (!SCHEMA_KEY_RE.test(nestedKey)) {
                    return { valid: false, error: `invalid nested key: ${nestedKey}` };
                }
                if (nestedSeen.has(nestedKey)) {
                    return { valid: false, error: `duplicate nested key: ${nestedKey}` };
                }
                nestedSeen.add(nestedKey);
                if (
                    nested.uiType === 'enum'
                    && (!Array.isArray(nested.enumValues) || nested.enumValues.length === 0)
                ) {
                    return { valid: false, error: `enum nested "${nestedKey}" needs at least one value` };
                }
            }
        }
    }
    return { valid: true };
}

/**
 * @param {Array<ReturnType<typeof createEmptyParameterRow>>} rows
 * @param {Record<string, unknown>} [rest]
 * @returns {Record<string, unknown>}
 */
export function parameterRowsToSchema(rows, rest = {}) {
    const validation = validateParameterRows(rows);
    if (!validation.valid) {
        throw new Error(validation.error);
    }
    const properties = {};
    const required = [];
    for (const row of rows) {
        const key = typeof row.key === 'string' ? row.key.trim() : '';
        if (key.length === 0) {
            continue;
        }
        properties[key] = parameterRowToProperty(row);
        if (row.required) {
            required.push(key);
        }
    }
    const schema = {
        ...rest,
        type: 'object',
        properties,
    };
    if (required.length > 0) {
        schema.required = required;
    } else {
        delete schema.required;
    }
    return schema;
}

/**
 * @param {unknown} node
 * @param {number} depth
 * @param {string[]} reasons
 * @param {string} path
 */
function walkAdvanced(node, depth, reasons, path) {
    if (!isPlainObject(node)) {
        return;
    }
    for (const marker of ['$defs', 'definitions', '$ref', 'oneOf', 'anyOf', 'allOf', 'not', 'if', 'then', 'else']) {
        if (marker in node) {
            reasons.push(`${path}.${marker}`);
        }
    }
    if (Array.isArray(node.type)) {
        reasons.push(`${path}.type[]`);
    }
    if (isPlainObject(node.properties)) {
        if (depth > 1) {
            reasons.push(`${path}.properties.depth`);
        }
        for (const [key, child] of Object.entries(node.properties)) {
            walkAdvanced(child, depth + 1, reasons, `${path}.properties.${key}`);
        }
    }
    if (isPlainObject(node.items)) {
        if (isPlainObject(node.items.properties) || node.items.type === 'object') {
            if (depth >= 1) {
                reasons.push(`${path}.items.object`);
            }
            walkAdvanced(node.items, depth + 1, reasons, `${path}.items`);
        } else {
            walkAdvanced(node.items, depth, reasons, `${path}.items`);
        }
    }
}

/**
 * @param {unknown} raw
 * @returns {{ advanced: boolean, reasons: string[] }}
 */
export function detectAdvancedSchemaFeatures(raw) {
    const reasons = [];
    if (raw === null || raw === undefined) {
        return { advanced: false, reasons };
    }
    if (!isPlainObject(raw)) {
        return { advanced: true, reasons: ['root.not_object'] };
    }
    if (raw.type !== undefined && raw.type !== 'object') {
        reasons.push('root.type');
    }
    if (raw.properties !== undefined && !isPlainObject(raw.properties)) {
        reasons.push('root.properties');
    }
    for (const marker of ['$defs', 'definitions', '$ref', 'oneOf', 'anyOf', 'allOf', 'not', 'if', 'then', 'else']) {
        if (marker in raw) {
            reasons.push(`root.${marker}`);
        }
    }
    if (isPlainObject(raw.properties)) {
        for (const [key, prop] of Object.entries(raw.properties)) {
            if (!isPlainObject(prop)) {
                reasons.push(`properties.${key}.not_object`);
                continue;
            }
            if (Array.isArray(prop.type) && !(Array.isArray(prop.enum) && prop.enum.length > 0)) {
                reasons.push(`properties.${key}.type[]`);
            }
            if (prop.type === 'object' && isPlainObject(prop.properties)) {
                for (const [nestedKey, nestedProp] of Object.entries(prop.properties)) {
                    if (!isPlainObject(nestedProp)) {
                        reasons.push(`properties.${key}.${nestedKey}.not_object`);
                        continue;
                    }
                    const nestedType = propertyUiType(nestedProp);
                    if (nestedType === 'object' || nestedType === 'array') {
                        reasons.push(`properties.${key}.${nestedKey}.nested_complex`);
                    }
                    walkAdvanced(nestedProp, 2, reasons, `properties.${key}.${nestedKey}`);
                }
            }
            if (prop.type === 'array' && isPlainObject(prop.items)) {
                if (prop.items.type === 'object' || isPlainObject(prop.items.properties)) {
                    reasons.push(`properties.${key}.items.object`);
                }
                if (
                    prop.items.type !== undefined
                    && !SCALAR_JSON_TYPES.has(prop.items.type)
                    && !(Array.isArray(prop.items.enum) && prop.items.enum.length > 0)
                    && prop.items.type !== 'string'
                ) {
                    if (!SCALAR_JSON_TYPES.has(prop.items.type)) {
                        const itemsType = prop.items.type;
                        if (itemsType !== 'string' && itemsType !== 'number' && itemsType !== 'integer' && itemsType !== 'boolean') {
                            reasons.push(`properties.${key}.items.type`);
                        }
                    }
                }
                walkAdvanced(prop.items, 1, reasons, `properties.${key}.items`);
            }
            for (const marker of ['$ref', 'oneOf', 'anyOf', 'allOf', 'not', '$defs']) {
                if (marker in prop) {
                    reasons.push(`properties.${key}.${marker}`);
                }
            }
        }
    }
    return { advanced: reasons.length > 0, reasons };
}

/**
 * @param {unknown} raw
 * @returns {{
 *   schema: Record<string, unknown>,
 *   rows: Array<ReturnType<typeof createEmptyParameterRow>>,
 *   rest: Record<string, unknown>,
 *   advanced: boolean,
 *   reasons: string[],
 * }}
 */
export function parseSchemaForEditor(raw) {
    const normalized = normalizeParametersSchema(raw);
    const { advanced, reasons } = detectAdvancedSchemaFeatures({
        type: 'object',
        properties: normalized.properties,
        required: normalized.required,
        ...normalized.rest,
    });
    const rows = advanced ? [] : schemaToParameterRows(normalized);
    const schema = {
        type: 'object',
        properties: normalized.properties,
        ...(normalized.required.length > 0 ? { required: normalized.required } : {}),
        ...normalized.rest,
    };
    if (normalized.required.length === 0) {
        delete schema.required;
    }
    return {
        schema,
        rows,
        rest: normalized.rest,
        advanced,
        reasons,
    };
}
