/**
 * Типы контроллеров и slice CRM UI.
 *
 * Динамические actions фабрик (`useSlice`/`useOp`/`useResource`) видны на
 * контроллере только через index-signature — здесь типизированные
 * интерфейсы контроллеров и shape slice'ов, чтобы компоненты не
 * размножали `Record<string, unknown>`-касты.
 */

import type {
    OpController,
    ResourceController,
    SliceController,
} from '@platform/lib/base/use-resource.js';
import type {
    ResourceCollectionSlice,
    ResourceItem,
} from '@platform/lib/events/factories/resource-collection.js';

export type CrmAction = (payload?: unknown) => void;

/** Элементы crm-ресурсов (сущность/заметка/связь) — свободная форма payload. */
export type CrmItem = ResourceItem;

// ============================================================================
// crm/graph_ui (graph-ui.resource.ts)
// ============================================================================

export interface CrmGraphUiSlice extends Record<string, unknown> {
    panels: Readonly<Record<string, boolean>>;
    timelineSeeded: boolean;
}


// ============================================================================
// crm/graph_view (graph-view.resource.ts)
// ============================================================================

export interface CrmGraphViewSelection {
    nodeId: string | null;
    edgeId: string | null;
}

export interface CrmGraphViewSearchInput {
    query: string;
    mode: string;
    minScore: number;
}

export interface CrmGraphViewSlice extends Record<string, unknown> {
    viewMode: string;
    maxDepth: number;
    displayDepth: number;
    selection: CrmGraphViewSelection;
    searchInput: CrmGraphViewSearchInput;
}


// ============================================================================
// crm/daily_notes_ui (daily-notes-ui.resource.ts)
// ============================================================================

export interface CrmDateRange {
    from: string;
    to: string;
}

export interface CrmDailyNotesUiSlice extends Record<string, unknown> {
    range: CrmDateRange;
}


// ============================================================================
// crm/note_compose (note-compose.resource.ts)
// ============================================================================

export interface CrmNoteComposeSlice extends Record<string, unknown> {
    description: string;
}


// ============================================================================
// Общие alias для `useOp`/`useResource` без специальных actions.
// ============================================================================

export type CrmCollectionSlice = ResourceCollectionSlice;
