import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { FLOW_UI_CATALOG_MANIFEST } from '../../../../core/frontend/static/lib/flow-ui/catalog/manifest.js';
import { flowUIText } from '../../../../core/frontend/static/lib/flow-ui/utils/text.js';
import { dashboardSurface } from '../../../../core/frontend/static/lib/flow-ui/templates/pages/dashboard.js';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');

describe('flow-ui live DataTable', () => {
    it('uses file_id schema kind and empty defaults (no throw on insert)', () => {
        const table = FLOW_UI_CATALOG_MANIFEST.components.DataTable;
        const fileIdField = table.editor.schema.find((field) => field.name === 'file_id');
        expect(fileIdField).toBeTruthy();
        expect(fileIdField.kind).toBe('file_id');
        const tableNameField = table.editor.schema.find((field) => field.name === 'table_name');
        expect(tableNameField).toBeTruthy();
        expect(tableNameField.kind).toBe('string');
        expect(table.editor.defaults.properties.file_id).toBe('');
        expect(table.editor.defaults.properties.table_name).toBe('');
        expect(table.editor.defaults.properties.columns).toEqual([]);
        expect(table.editor.defaults.properties.rows).toEqual([]);
    });

    it('renders empty DataTable as placeholder, not throw', () => {
        const feedSrc = readFileSync(
            path.join(REPO_ROOT, 'core/frontend/static/lib/flow-ui/catalog/platform/feed.js'),
            'utf8',
        );
        expect(feedSrc).toMatch(/table-empty/);
        expect(feedSrc).toMatch(/platform-data-table-host/);
        expect(feedSrc).toMatch(/interaction="view"/);
        expect(feedSrc).toMatch(/data_table_column_filter_placeholder/);
        expect(feedSrc).toMatch(/flowUIText\(host\.locale,\s*'data_table_empty'\)/);
        expect(flowUIText('ru', 'data_table_column_filter_placeholder')).toBe('Фильтр…');
        expect(flowUIText('en', 'data_table_column_filter_placeholder')).toBe('Filter…');
        expect(flowUIText('ru', 'data_table_empty')).toContain('file_id');
        expect(flowUIText('en', 'data_table_empty')).toContain('file_id');
    });

    it('keeps dashboard static rows binding', () => {
        const surface = dashboardSurface('main', 'en');
        const table = surface.components.table;
        expect(table.type).toBe('DataTable');
        expect(table.bindings.rows).toBe('/content/rows');
        expect(Array.isArray(table.properties.columns)).toBe(true);
        expect(table.properties.file_id).toBeUndefined();
    });

    it('wires inspector file_id picker to platform file_id, not download URL', () => {
        const inspectorSrc = readFileSync(
            path.join(
                REPO_ROOT,
                'apps/flows/ui/components/interface-editor/flows-interface-inspector.js',
            ),
            'utf8',
        );
        expect(inspectorSrc).toMatch(/kind === 'file_id'/);
        expect(inspectorSrc).toMatch(/acceptMimePrefix: 'application\/vnd\.sqlite3'/);
        expect(inspectorSrc).toMatch(/value: file\.file_id/);
        expect(inspectorSrc).toMatch(/inspector_file_id_pick/);
        expect(inspectorSrc).not.toMatch(/kind === 'file_id'[\s\S]{0,800}buildPlatformFileDownloadUrl/);
    });
});
