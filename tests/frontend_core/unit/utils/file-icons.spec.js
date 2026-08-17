import { describe, it, expect } from 'vitest';
import { resolveUiIconFile, resolveFileIconBasename, resolveFileIconKey } from '@platform/lib/utils/file-icons.js';

describe('resolveUiIconFile', () => {
    it('maps minus to minus.svg basename', () => {
        expect(resolveUiIconFile('minus')).toBe('minus');
    });

    it('maps chevron-down and chevron-up to their own SVG basenames', () => {
        expect(resolveUiIconFile('chevron-down')).toBe('chevron-down');
        expect(resolveUiIconFile('chevron-up')).toBe('chevron-up');
    });

    it('maps arrow-up and arrow-down to chevron SVG basenames', () => {
        expect(resolveUiIconFile('arrow-up')).toBe('chevron-up');
        expect(resolveUiIconFile('arrow-down')).toBe('chevron-down');
    });

    it('preserves explicit collapse, expand, and minimize names', () => {
        expect(resolveUiIconFile('collapse')).toBe('collapse');
        expect(resolveUiIconFile('expand')).toBe('expand');
        expect(resolveUiIconFile('minimize')).toBe('minimize');
    });
});

describe('resolveFileIconBasename', () => {
    it('maps folder and catalog aliases to the colored folder asset', () => {
        expect(resolveFileIconBasename('folder')).toBe('033-folder');
        expect(resolveFileIconBasename('catalog')).toBe('033-folder');
    });

    it('maps database and data table aliases to distinct file assets', () => {
        expect(resolveFileIconBasename('db')).toBe('034-database');
        expect(resolveFileIconBasename('data_table')).toBe('035-data-table');
        expect(resolveFileIconBasename('sqlite')).toBe('035-data-table');
    });
});

describe('resolveFileIconKey', () => {
    it('resolves sqlite MIME and .db extension to their own keys', () => {
        expect(resolveFileIconKey('sales.sqlite', 'application/vnd.sqlite3')).toBe('sqlite');
        expect(resolveFileIconKey('cache.db', '')).toBe('db');
        expect(resolveFileIconKey('grid.sqlite', '')).toBe('sqlite');
    });
});
