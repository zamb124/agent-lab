/**
 * Play для resource type=rag: поиск в namespace bind с query из slice.
 */

import { isPlainObject } from './flows-resolvers.js';
import { packSearchRequestOptions } from '@platform/lib/rag/pack_search_request_options.js';
import { resolveResourceForPanel, pinnedResourceIds } from './flows-branch-resource.js';
import { setTestRunRequestClientId } from './flows-test-run-gate.js';

export function buildRagSearchPayload({ nodeId, query, nodeConfig, editorState, catalogItems }) {
    if (typeof nodeId !== 'string' || nodeId.length === 0) {
        throw new Error('buildRagSearchPayload: nodeId required');
    }
    if (typeof query !== 'string' || query.trim().length === 0) {
        throw new Error('buildRagSearchPayload: query required');
    }
    const ids = pinnedResourceIds(nodeConfig);
    if (ids.length !== 1) {
        throw new Error(`buildRagSearchPayload: expected 1 pinned resource, got ${ids.length}`);
    }
    const resolved = resolveResourceForPanel(ids[0], editorState, catalogItems);
    if (resolved === null) {
        throw new Error(`buildRagSearchPayload: resource ${ids[0]} unresolved`);
    }
    if (resolved.resource.type !== 'rag') {
        throw new Error(`buildRagSearchPayload: pinned type is ${resolved.resource.type}, expected rag`);
    }
    const cfg = isPlainObject(resolved.resource.config) ? resolved.resource.config : null;
    if (cfg === null) {
        throw new Error('buildRagSearchPayload: rag config object required');
    }
    const namespace = typeof cfg.namespace === 'string' ? cfg.namespace.trim() : '';
    if (namespace.length === 0) {
        throw new Error('buildRagSearchPayload: namespace required');
    }
    if (typeof cfg.default_top_k !== 'number' || !Number.isFinite(cfg.default_top_k) || cfg.default_top_k < 1) {
        throw new Error('buildRagSearchPayload: default_top_k >= 1 required');
    }
    const payload = {
        nodeId,
        namespaceId: namespace,
        query: query.trim(),
        limit: Math.trunc(cfg.default_top_k),
        ...packSearchRequestOptions(isPlainObject(cfg.search_options) ? cfg.search_options : null),
    };
    if (isPlainObject(cfg.filters)) {
        payload.filters = cfg.filters;
    }
    return payload;
}

export const ragSearchTestRunHandler = {
    id: 'rag_search',
    opName: 'flows/rag_search',
    match: ({ nodeType, resourceType }) => nodeType === 'resource' && resourceType === 'rag',
    busyOf: (op) => op.busy === true,
    formatViewModel: ({ op, nodeId, t }) => {
        if (typeof nodeId !== 'string' || nodeId.length === 0) {
            throw new Error('ragSearchTestRunHandler: nodeId required');
        }
        if (typeof t !== 'function') {
            throw new Error('ragSearchTestRunHandler: t required');
        }
        const errorByNodeId = op.state.errorByNodeId;
        const resultByNodeId = op.state.resultByNodeId;
        if (!isPlainObject(errorByNodeId) || !isPlainObject(resultByNodeId)) {
            throw new Error('ragSearchTestRunHandler: resultByNodeId/errorByNodeId required');
        }
        const opError = Object.prototype.hasOwnProperty.call(errorByNodeId, nodeId)
            ? errorByNodeId[nodeId]
            : null;
        if (opError !== null && opError !== undefined) {
            const line = typeof opError === 'string' ? opError : String(opError);
            return {
                kind: 'error',
                lines: [line],
                durationMs: null,
                fullPayload: null,
                canOpenFull: false,
            };
        }
        const lastResult = Object.prototype.hasOwnProperty.call(resultByNodeId, nodeId)
            ? resultByNodeId[nodeId]
            : null;
        if (lastResult === null || lastResult === undefined) {
            return null;
        }
        if (!isPlainObject(lastResult) || !Array.isArray(lastResult.results)) {
            throw new Error('ragSearchTestRunHandler: lastResult.results array required');
        }
        const count = lastResult.results.length;
        return {
            kind: 'ok',
            lines: [t('rag_resource_editor.test_hits', { count: String(count) })],
            durationMs: null,
            fullPayload: lastResult,
            canOpenFull: true,
        };
    },
    run: async ({ host, op, requestClientId, matchCtx }) => {
        const queryByNodeId = host._ragNodeTest.value.queryByNodeId;
        if (!isPlainObject(queryByNodeId)) {
            throw new Error('ragSearchTestRunHandler: queryByNodeId object required');
        }
        const rawQuery = Object.prototype.hasOwnProperty.call(queryByNodeId, host.nodeId)
            ? queryByNodeId[host.nodeId]
            : '';
        if (typeof rawQuery !== 'string' || rawQuery.trim().length === 0) {
            host.toast('rag_resource_editor.test_query_required', { type: 'error' });
            return;
        }
        const payload = buildRagSearchPayload({
            nodeId: host.nodeId,
            query: rawQuery,
            nodeConfig: host.nodeConfig,
            editorState: matchCtx.editorState,
            catalogItems: matchCtx.catalogItems,
        });
        setTestRunRequestClientId(requestClientId);
        await op.run(payload);
    },
};
