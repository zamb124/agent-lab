/**
 * Общие типы Documents explorer — wire-модель и slice `office/documents`.
 * Type-only leaf: resources и pages/components импортируют отсюда,
 * чтобы pages/modals не зависели от `events/resources/*` напрямую.
 */

import type { AsyncOpSlice } from '@platform/lib/events/factories/async-op.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { OfficeDocumentItem } from '@platform/lib/events/wire/office.gen.js';

export type { OfficeDocumentItem };

export interface DocumentsSlice extends AsyncOpSlice {
    items?: OfficeDocumentItem[] | undefined;
    loadedCatalogIds?: string[] | undefined;
    activeCatalogId?: string | null | undefined;
    filterCatalogIds?: string[] | undefined;
    selectedFileId?: string | null | undefined;
    selectedCatalogId?: string | null | undefined;
    selectedFileIds?: string[] | undefined;
    uploadJobs?: { localId?: unknown; [key: string]: unknown }[] | undefined;
    expandedCatalogIds?: string[] | undefined;
    recentFileIds?: string[] | undefined;
    starredFileIds?: string[] | undefined;
    searchQuery?: string | undefined;
    searchMode?: string | undefined;
    sortKey?: string | undefined;
    sortDir?: string | undefined;
    [key: string]: unknown;
}

export type DocumentsAction = (payload?: unknown) => void;

/** Динамические actions `documentsOp` (см. `actions:` в documents.resource). */
