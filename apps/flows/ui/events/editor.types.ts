/**
 * Общие типы редактора flows — slice `flows/editor` и типизированный op-контроллер.
 * Type-only leaf: components/modals импортируют отсюда, чтобы не зависеть
 * от `events/resources/editor.resource` напрямую.
 */

import type { AsyncOpSlice } from '@platform/lib/events/factories/async-op.js';
import type { OpController } from '@platform/lib/base/use-resource.js';

export interface FlowEditorSlice extends AsyncOpSlice {
    flowId?: string | null;
    flowConfig?: Record<string, any> | null;
    branchData?: Record<string, any> | null;
    currentBranchId?: string | null;
    selectedNodeId?: string | null;
    selectedResourceId?: string | null;
    openNodePanelIds?: string[];
    propertyPanelLayouts?: Record<string, any>;
    panelOpen?: boolean;
    executionPanelOpen?: boolean;
    agentExecutionRunning?: boolean;
    activeTool?: string;
    previewExecutionState?: Record<string, any> | null;
    dataflow?: Record<string, any> | null;
    dataflowObservations?: Record<string, any>;
    workspace?: string;
    editorLayout?: string;
    isDirty?: boolean;
    isSaving?: boolean;
    publishedAt?: string | null;
    historyStack?: any[];
    historyPosition?: number;
    canUndo?: boolean;
    canRedo?: boolean;
    runningNodeIds?: string[];
    completedNodeIds?: string[];
    runningEdgeIndices?: number[];
    completedEdgeIndices?: number[];
    failedEdgeIndices?: number[];
    erroredNodes?: Record<string, any>;
    nodeRunResults?: Record<string, any[]>;
    expandedNodeRunKeys?: Record<string, boolean>;
    breakpointNodeIds?: string[];
    breakpointHitNodeId?: string | null;
    showCanvasRunResults?: boolean;
    runSession?: Record<string, any>;
    runTrace?: Record<string, any>;
    startWireRunState?: Record<string, any> | null;
    endWireRunStateByNodeId?: Record<string, any>;
    entryNodeId?: string | null;
    inheritedNodeIds?: string[];
    inheritedEdgeKeys?: string[];
    multiSelection?: string[];
    viewBox?: Record<string, any>;
    smartGuides?: any[];
    smartGuidesEnabled?: boolean;
    showDataWires?: boolean;
    contextMenu?: Record<string, any> | null;
    stickyNotes?: Record<string, any>[];
    pendingNodeToolId?: string | null;
    [key: string]: unknown;
}

export type FlowEditorAction = (payload?: any) => void;

/** Динамические actions `flows/editor` (см. `actions:` в editor.resource). */

import type { SliceController } from '@platform/lib/base/use-resource.js';

export interface InterfaceEditorUiSlice extends Record<string, unknown> {
    documentKey?: string;
    history?: any;
    pageId?: string;
    selectedBlockId?: string;
    viewport?: string;
    preview?: boolean;
    sidebarTab?: string;
    problems?: readonly any[];
}


export interface ExecutionUiSlice extends Record<string, unknown> {
    persistContext?: boolean;
    mockResponses?: any[];
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
    queryByNodeId?: Record<string, string>;
    searchByNodeId?: Record<string, any>;
}

