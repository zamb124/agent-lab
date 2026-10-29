/**
 * Общие типы редактора flows — slice `flows/editor` и типизированный op-контроллер.
 * Type-only leaf: components/modals импортируют отсюда, чтобы не зависеть
 * от `events/resources/editor.resource` напрямую.
 */

import type { AsyncOpSlice } from '@platform/lib/events/factories/async-op.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { DocumentProblem, EditorHistory } from '../_helpers/interface-editor-domain.js';

export interface FlowEditorSlice extends AsyncOpSlice {
    flowId?: string | null;
    flowConfig?: Record<string, unknown> | null;
    branchData?: Record<string, unknown> | null;
    currentBranchId?: string | null;
    selectedNodeId?: string | null;
    selectedResourceId?: string | null;
    openNodePanelIds?: string[];
    propertyPanelLayouts?: Record<string, unknown>;
    panelOpen?: boolean;
    executionPanelOpen?: boolean;
    agentExecutionRunning?: boolean;
    activeTool?: string;
    previewExecutionState?: Record<string, unknown> | null;
    dataflow?: Record<string, unknown> | null;
    dataflowObservations?: Record<string, unknown>;
    workspace?: string;
    editorLayout?: string;
    isDirty?: boolean;
    isSaving?: boolean;
    publishedAt?: string | null;
    historyStack?: unknown[];
    historyPosition?: number;
    canUndo?: boolean;
    canRedo?: boolean;
    runningNodeIds?: string[];
    completedNodeIds?: string[];
    runningEdgeIndices?: number[];
    completedEdgeIndices?: number[];
    failedEdgeIndices?: number[];
    erroredNodes?: Record<string, unknown>;
    nodeRunResults?: Record<string, readonly unknown[]>;
    expandedNodeRunKeys?: readonly string[];
    breakpointNodeIds?: string[];
    breakpointHitNodeId?: string | null;
    showCanvasRunResults?: boolean;
    runSession?: Record<string, unknown>;
    runTrace?: readonly unknown[];
    startWireRunState?: string | null;
    endWireRunStateByNodeId?: Record<string, unknown>;
    entryNodeId?: string | null;
    inheritedNodeIds?: string[];
    inheritedEdgeKeys?: string[];
    multiSelection?: string[];
    viewBox?: Record<string, unknown>;
    smartGuides?: unknown[];
    smartGuidesEnabled?: boolean;
    showDataWires?: boolean;
    contextMenu?: Record<string, unknown> | null;
    stickyNotes?: Record<string, unknown>[];
    pendingNodeToolId?: string | null;
    [key: string]: unknown;
}

export type FlowEditorAction = (payload?: unknown) => void;

/** Динамические actions `flows/editor` (см. `actions:` в editor.resource). */

import type { SliceController } from '@platform/lib/base/use-resource.js';

export interface InterfaceEditorUiSlice extends Record<string, unknown> {
    documentKey?: string;
    history?: EditorHistory | null;
    pageId?: string;
    selectedBlockId?: string;
    viewport?: string;
    preview?: boolean;
    sidebarTab?: string;
    problems?: readonly DocumentProblem[];
}


export interface ExecutionUiSlice extends Record<string, unknown> {
    persistContext?: boolean;
    mockResponses?: unknown[];
}


export interface EvaluationUiSlice extends Record<string, unknown> {
    selectedSuiteId?: string;
    selectedCaseId?: string;
    selectedRunId?: string;
    selectedCaseRunId?: string;
    selectedCompareRunId?: string;
    activePanel?: string;
    fullscreenPanel?: string;
    runScope?: string;
    trials?: number;
    maxConcurrency?: number;
}


export interface RagNodeTestSlice extends Record<string, unknown> {
    queryByNodeId: Record<string, string>;
    resultByNodeId: Record<string, unknown>;
    errorByNodeId: Record<string, string | null>;
    lastNodeId: string | null;
}

