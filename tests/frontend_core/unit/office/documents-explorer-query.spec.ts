import { describe, expect, it } from 'vitest';
import {
    documentsExplorerQuery,
    documentsExplorerPageQuery,
    documentsExplorerQueryNamespace,
} from '../../../../apps/office/ui/_helpers/documents-explorer-query.js';

describe('documentsExplorerQuery', () => {
    it('reads namespace, catalog_id and access', () => {
        expect(documentsExplorerQuery('?namespace=default&catalog_id=cat-1&access=1')).toEqual({
            catalogId: 'cat-1',
            namespace: 'default',
            access: true,
        });
    });

    it('empty search is empty query', () => {
        expect(documentsExplorerQuery('')).toEqual({
            catalogId: '',
            namespace: '',
            access: false,
        });
    });
});

describe('documentsExplorerQueryNamespace', () => {
    it('prefers explicit namespace', () => {
        expect(
            documentsExplorerQueryNamespace({ catalogId: 'cat-1', namespace: 'docs' }),
        ).toBe('docs');
    });

    it('uses default when only catalog_id is present', () => {
        expect(
            documentsExplorerQueryNamespace({ catalogId: 'cat-1', namespace: '' }),
        ).toBe('default');
    });

    it('empty without catalog_id', () => {
        expect(
            documentsExplorerQueryNamespace({ catalogId: '', namespace: '' }),
        ).toBe('');
    });
});

describe('documentsExplorerPageQuery', () => {
    it('prefers router search when it has catalog_id', () => {
        expect(
            documentsExplorerPageQuery(
                '?namespace=default&catalog_id=from-router',
                '?namespace=other&catalog_id=from-location',
            ),
        ).toEqual({
            catalogId: 'from-router',
            namespace: 'default',
            access: false,
        });
    });

    it('reads location.search when router search is empty', () => {
        expect(
            documentsExplorerPageQuery('', '?catalog_id=from-location'),
        ).toEqual({
            catalogId: 'from-location',
            namespace: '',
            access: false,
        });
        expect(
            documentsExplorerQueryNamespace(
                documentsExplorerPageQuery('', '?catalog_id=from-location'),
            ),
        ).toBe('default');
    });
});
