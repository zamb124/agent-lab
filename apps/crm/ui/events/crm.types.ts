/**
 * Типы контроллеров и slice CRM UI.
 *
 * Динамические actions фабрик (`useSlice`/`useOp`/`useResource`) видны на
 * контроллере только через index-signature — здесь типизированные
 * интерфейсы контроллеров и shape slice'ов, чтобы компоненты не
 * размножали `Record<string, any>`-касты.
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

export interface CrmGraphUiController extends SliceController {
    readonly value: CrmGraphUiSlice | undefined;
    setPanels: CrmAction;
    hydratePanels: CrmAction;
    markTimelineSeeded: CrmAction;
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

export interface CrmGraphViewController extends SliceController {
    readonly value: CrmGraphViewSlice | undefined;
    hydrate: CrmAction;
    setViewMode: CrmAction;
    setMaxDepth: CrmAction;
    setDisplayDepth: CrmAction;
    setSelection: CrmAction;
    setSearchInput: CrmAction;
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

export interface CrmDailyNotesUiController extends SliceController {
    readonly value: CrmDailyNotesUiSlice | undefined;
    setRange: CrmAction;
}

// ============================================================================
// crm/note_compose (note-compose.resource.ts)
// ============================================================================

export interface CrmNoteComposeSlice extends Record<string, unknown> {
    description: string;
}

export interface CrmNoteComposeController extends SliceController {
    readonly value: CrmNoteComposeSlice | undefined;
    setDescription: CrmAction;
}

// ============================================================================
// Общие alias для `useOp`/`useResource` без специальных actions.
// ============================================================================

export type CrmOpController = OpController;
export type CrmResourceController = ResourceController;
export type CrmCollectionSlice = ResourceCollectionSlice;
