/**
 * Общие типы Documents explorer — wire-модель и slice `office/documents`.
 * Type-only leaf: resources и pages/components импортируют отсюда,
 * чтобы pages/modals не зависели от `events/resources/*` напрямую.
 */

import type { AsyncOpSlice } from '@platform/lib/events/factories/async-op.js';
import type { OpController } from '@platform/lib/base/use-resource.js';

export interface OfficeDocumentItem {
    file_id?: string;
    catalog_id?: string;
    title?: string;
    [key: string]: unknown;
}

export interface DocumentsSlice extends AsyncOpSlice {
    items?: OfficeDocumentItem[];
    loadedCatalogIds?: string[];
    activeCatalogId?: string | null;
    filterCatalogIds?: string[];
    selectedFileId?: string | null;
    selectedCatalogId?: string | null;
    selectedFileIds?: string[];
    uploadJobs?: { localId?: unknown; [key: string]: unknown }[];
    expandedCatalogIds?: string[];
    recentFileIds?: string[];
    starredFileIds?: string[];
    searchQuery?: string;
    searchMode?: string;
    sortKey?: string;
    sortDir?: string;
    [key: string]: unknown;
}

export type DocumentsAction = (payload?: unknown) => void;

/** Динамические actions `documentsOp` (см. `actions:` в documents.resource). */
export interface DocumentsOpController extends OpController {
    readonly state: DocumentsSlice;
    setActiveCatalog: DocumentsAction;
    setCatalogExpanded: DocumentsAction;
    setFilterCatalogs: DocumentsAction;
    clearFilter: DocumentsAction;
    setViewMode: DocumentsAction;
    setSearchQuery: DocumentsAction;
    setSearchMode: DocumentsAction;
    setSort: DocumentsAction;
    setSelectedFile: DocumentsAction;
    setSelectedCatalog: DocumentsAction;
    toggleFileSelection: DocumentsAction;
    setFileSelection: DocumentsAction;
    clearFileSelection: DocumentsAction;
    setExplorerView: DocumentsAction;
    toggleStarred: DocumentsAction;
    recordRecentOpen: DocumentsAction;
    patchRagIndexStatuses: DocumentsAction;
}
