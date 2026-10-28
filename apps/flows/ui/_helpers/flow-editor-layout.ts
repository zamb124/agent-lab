/**
 * Agent Focus Mode — eligibility и preference layout редактора.
 *
 * Eligible: ровно одна нода и type === 'llm_node'.
 * Preference: localStorage `platform:flows:editor_layout.<flowId>` → 'agent' | 'canvas'.
 * Default при первом визите: 'agent'.
 */

import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import { storageGet, storageSet } from '@platform/lib/utils/platform-storage.js';
import { isPlainObject } from './flows-resolvers.js';

export const EDITOR_LAYOUT_AGENT = 'agent';
export const EDITOR_LAYOUT_CANVAS = 'canvas';

const LAYOUT_VALUES = new Set([EDITOR_LAYOUT_AGENT, EDITOR_LAYOUT_CANVAS]);

/**
 * @param {unknown} branchData
 * @returns {boolean}
 */
export function isAgentFocusEligible(branchData: any) {
    if (!isPlainObject(branchData)) {
        return false;
    }
    const nodes = branchData.nodes;
    if (!isPlainObject(nodes)) {
        return false;
    }
    const ids = Object.keys(nodes);
    if (ids.length !== 1) {
        return false;
    }
    const soleId = ids[0];
    if (soleId === undefined) {
        throw new Error('isAgentFocusEligible: node id missing');
    }
    const sole = nodes[soleId];
    return isPlainObject(sole) && sole.type === 'llm_node';
}

/**
 * @param {unknown} branchData
 * @returns {string}
 */
export function getSoleNodeId(branchData: any) {
    if (!isAgentFocusEligible(branchData)) {
        throw new Error('getSoleNodeId: branchData is not agent-focus eligible');
    }
    const nodes = /** @type {{ nodes: Record<string, unknown> }} */ (branchData).nodes;
    return Object.keys(nodes)[0];
}

/**
 * Сегмент ключа platformStorageKey: lowercase snake_case.
 * @param {string} flowId
 * @returns {string}
 */
function _storageSegmentForFlowId(flowId: string) {
    if (typeof flowId !== 'string' || flowId.length === 0) {
        throw new Error('flow-editor-layout: flowId is required');
    }
    const segment = flowId
        .toLowerCase()
        .replace(/[^a-z0-9_]+/g, '_')
        .replace(/^_+|_+$/g, '')
        .replace(/_+/g, '_');
    if (segment.length === 0 || !/^[a-z][a-z0-9_]*$/.test(segment)) {
        throw new Error(`flow-editor-layout: cannot derive storage segment from flowId "${flowId}"`);
    }
    return segment;
}

/**
 * @param {string} flowId
 * @returns {string}
 */
function _preferenceStorageKey(flowId: string) {
    return platformStorageKey('flows', `editor_layout.${_storageSegmentForFlowId(flowId)}`);
}

/**
 * @param {string} flowId
 * @returns {'agent' | 'canvas'}
 */
export function readEditorLayoutPreference(flowId: string) {
    const key = _preferenceStorageKey(flowId);
    let raw = null;
    try {
        raw = storageGet(key);
    } catch (err) {
        throw new Error(`flow-editor-layout: localStorage.getItem failed: ${err}`);
    }
    if (raw === EDITOR_LAYOUT_AGENT || raw === EDITOR_LAYOUT_CANVAS) {
        return raw;
    }
    return EDITOR_LAYOUT_AGENT;
}

/**
 * @param {string} flowId
 * @param {'agent' | 'canvas'} layout
 */
export function writeEditorLayoutPreference(flowId: string, layout: any) {
    if (!LAYOUT_VALUES.has(layout)) {
        throw new Error(`flow-editor-layout: layout must be agent|canvas, got "${layout}"`);
    }
    const key = _preferenceStorageKey(flowId);
    try {
        storageSet(key, layout);
    } catch (err) {
        throw new Error(`flow-editor-layout: localStorage.setItem failed: ${err}`);
    }
}

/**
 * @param {unknown} branchData
 * @param {string | null | undefined} flowId
 * @param {'agent' | 'canvas' | null | undefined} preferred
 * @returns {'agent' | 'canvas'}
 */
export function resolveEditorLayout(branchData: any, flowId: string, preferred: any) {
    if (!isAgentFocusEligible(branchData)) {
        return EDITOR_LAYOUT_CANVAS;
    }
    if (preferred === EDITOR_LAYOUT_AGENT || preferred === EDITOR_LAYOUT_CANVAS) {
        return preferred;
    }
    if (typeof flowId === 'string' && flowId.length > 0) {
        return readEditorLayoutPreference(flowId);
    }
    return EDITOR_LAYOUT_AGENT;
}

/**
 * @param {object} state
 * @param {'agent' | 'canvas'} layout
 * @param {unknown} branchData
 * @returns {object}
 */
export function applyEditorLayoutToState(state: any, layout: any, branchData: any) {
    if (layout === EDITOR_LAYOUT_AGENT && isAgentFocusEligible(branchData)) {
        const soleId = getSoleNodeId(branchData);
        return {
            ...state,
            editorLayout: EDITOR_LAYOUT_AGENT,
            selectedNodeId: soleId,
            selectedResourceId: null,
            openNodePanelIds: [soleId],
            panelOpen: true,
            multiSelection: [soleId],
        };
    }
    return {
        ...state,
        editorLayout: EDITOR_LAYOUT_CANVAS,
    };
}
