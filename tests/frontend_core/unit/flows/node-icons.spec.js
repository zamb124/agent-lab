import { describe, expect, it } from 'vitest';
import { datasourceIconName } from '../../../../apps/flows/ui/constants/node-icons.js';

describe('datasourceIconName', () => {
    it('maps platform connector_id to brand icon', () => {
        expect(datasourceIconName('postgres')).toBe('postgres');
        expect(datasourceIconName('mysql')).toBe('mysql');
        expect(datasourceIconName('clickhouse')).toBe('clickhouse');
    });

    it('uses database for company stamp connector_id', () => {
        expect(datasourceIconName('mcp_warehouse')).toBe('database');
    });

    it('throws without connector_id', () => {
        expect(() => datasourceIconName('')).toThrow('connector_id required');
    });
});
