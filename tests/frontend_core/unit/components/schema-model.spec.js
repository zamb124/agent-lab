import { describe, it, expect } from 'vitest';
import {
    createEmptyParameterRow,
    detectAdvancedSchemaFeatures,
    normalizeParametersSchema,
    parameterRowsToSchema,
    parseSchemaForEditor,
    schemaToParameterRows,
    validateParameterRows,
} from '../../../../core/frontend/static/lib/components/schema/schema-model.js';

describe('schema-model', () => {
    it('normalize empty → object schema', () => {
        expect(normalizeParametersSchema(null)).toEqual({
            type: 'object',
            properties: {},
            required: [],
            rest: {},
        });
    });

    it('round-trip flat string/number/required + rest keys', () => {
        const raw = {
            type: 'object',
            properties: {
                query: { type: 'string', description: 'Search query' },
                limit: { type: 'integer', description: 'Max items' },
            },
            required: ['query'],
            additionalProperties: false,
            title: 'SearchArgs',
        };
        const normalized = normalizeParametersSchema(raw);
        expect(normalized.rest).toEqual({
            additionalProperties: false,
            title: 'SearchArgs',
        });
        const rows = schemaToParameterRows(normalized);
        expect(rows).toHaveLength(2);
        expect(rows[0].key).toBe('query');
        expect(rows[0].required).toBe(true);
        expect(rows[0].uiType).toBe('string');
        expect(rows[1].key).toBe('limit');
        expect(rows[1].uiType).toBe('integer');
        const back = parameterRowsToSchema(rows, normalized.rest);
        expect(back).toEqual({
            additionalProperties: false,
            title: 'SearchArgs',
            type: 'object',
            properties: {
                query: { type: 'string', description: 'Search query' },
                limit: { type: 'integer', description: 'Max items' },
            },
            required: ['query'],
        });
    });

    it('enum + array items enum round-trip', () => {
        const raw = {
            type: 'object',
            properties: {
                lane: { type: 'string', enum: ['text', 'vision'], description: 'Lane' },
                tags: { type: 'array', items: { type: 'string', enum: ['a', 'b'] } },
            },
            required: ['lane'],
        };
        const parsed = parseSchemaForEditor(raw);
        expect(parsed.advanced).toBe(false);
        expect(parsed.rows[0].uiType).toBe('enum');
        expect(parsed.rows[0].enumValues).toEqual(['text', 'vision']);
        expect(parsed.rows[1].uiType).toBe('array');
        expect(parsed.rows[1].itemsUiType).toBe('enum');
        expect(parameterRowsToSchema(parsed.rows, parsed.rest)).toEqual({
            type: 'object',
            properties: {
                lane: { type: 'string', enum: ['text', 'vision'], description: 'Lane' },
                tags: { type: 'array', items: { type: 'string', enum: ['a', 'b'] } },
            },
            required: ['lane'],
        });
    });

    it('one-level object nested properties', () => {
        const raw = {
            type: 'object',
            properties: {
                meta: {
                    type: 'object',
                    properties: {
                        source: { type: 'string', description: 'Origin' },
                        score: { type: 'number' },
                    },
                    required: ['source'],
                },
            },
        };
        const parsed = parseSchemaForEditor(raw);
        expect(parsed.advanced).toBe(false);
        expect(parsed.rows[0].uiType).toBe('object');
        expect(parsed.rows[0].nestedRows).toHaveLength(2);
        expect(parameterRowsToSchema(parsed.rows, parsed.rest).properties.meta).toEqual({
            type: 'object',
            properties: {
                source: { type: 'string', description: 'Origin' },
                score: { type: 'number' },
            },
            required: ['source'],
        });
    });

    it('detects $defs / $ref as advanced', () => {
        const withDefs = detectAdvancedSchemaFeatures({
            type: 'object',
            $defs: { ReadLane: { type: 'string', enum: ['text'] } },
            properties: {
                lane: { $ref: '#/$defs/ReadLane' },
            },
        });
        expect(withDefs.advanced).toBe(true);
        expect(withDefs.reasons.some((r) => r.includes('$defs') || r.includes('$ref'))).toBe(true);
    });

    it('detects deep nested object as advanced', () => {
        const deep = detectAdvancedSchemaFeatures({
            type: 'object',
            properties: {
                outer: {
                    type: 'object',
                    properties: {
                        inner: {
                            type: 'object',
                            properties: { x: { type: 'string' } },
                        },
                    },
                },
            },
        });
        expect(deep.advanced).toBe(true);
    });

    it('validateParameterRows rejects bad / duplicate keys and empty enum', () => {
        const badKey = createEmptyParameterRow();
        badKey.key = '1bad';
        expect(validateParameterRows([badKey]).valid).toBe(false);

        const a = createEmptyParameterRow();
        a.key = 'name';
        const b = createEmptyParameterRow();
        b.key = 'name';
        expect(validateParameterRows([a, b]).valid).toBe(false);

        const enumRow = createEmptyParameterRow();
        enumRow.key = 'lane';
        enumRow.uiType = 'enum';
        enumRow.enumValues = [];
        expect(validateParameterRows([enumRow]).valid).toBe(false);
    });

    it('parseSchemaForEditor returns empty rows for advanced schema', () => {
        const parsed = parseSchemaForEditor({
            type: 'object',
            oneOf: [{ type: 'object' }],
            properties: {},
        });
        expect(parsed.advanced).toBe(true);
        expect(parsed.rows).toEqual([]);
    });
});
