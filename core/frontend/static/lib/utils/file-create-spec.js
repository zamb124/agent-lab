/**
 * JSON FileCreateSpec для platform/file_create (контракт core/files/create_spec.py).
 */

const DEFAULT_RETENTION_BY_SOURCE = Object.freeze({
    crm_entity: 'crm_entity',
    flow_session: 'flow_session',
    flow_asset: 'flow_asset',
    work_item: 'work_item',
    sync_message: 'sync_message_attachment',
    sync_channel_asset: 'sync_channel_asset',
    sync_call_recording: 'sync_call_recording',
    sync_speech_segment: 'sync_speech_segment',
    browser_artifact: 'browser_artifact',
    rag_document: 'rag_document',
    office_document: 'office_document',
    calendar_event: 'calendar_event_attachment',
    platform_auxiliary: 'platform_default',
    generated_ephemeral: 'generated_ephemeral',
});

/**
 * @param {{
 *   sourceKind: string,
 *   sourceRef?: Record<string, string>,
 *   retentionKind?: string,
 *   postCreate?: Record<string, unknown>,
 *   metadata?: Record<string, unknown>,
 *   placement?: Record<string, unknown>,
 *   tags?: string[],
 * }} params
 * @returns {string}
 */
export function buildFileCreateSpecJson(params) {
    if (!params || typeof params !== 'object') {
        throw new Error('buildFileCreateSpecJson: params object required');
    }
    const sourceKind = params.sourceKind;
    if (typeof sourceKind !== 'string' || sourceKind.length === 0) {
        throw new Error('buildFileCreateSpecJson: sourceKind required');
    }
    const sourceRef = params.sourceRef && typeof params.sourceRef === 'object'
        ? params.sourceRef
        : {};
    const retentionKind = typeof params.retentionKind === 'string' && params.retentionKind.length > 0
        ? params.retentionKind
        : DEFAULT_RETENTION_BY_SOURCE[sourceKind];
    if (typeof retentionKind !== 'string' || retentionKind.length === 0) {
        throw new Error(`buildFileCreateSpecJson: retentionKind required for sourceKind=${sourceKind}`);
    }
    const spec = {
        source_kind: sourceKind,
        source_ref: sourceRef,
        retention: { kind: retentionKind },
    };
    if (params.postCreate && typeof params.postCreate === 'object') {
        spec.post_create = params.postCreate;
    }
    if (params.metadata && typeof params.metadata === 'object') {
        spec.metadata = params.metadata;
    }
    if (params.placement && typeof params.placement === 'object') {
        spec.placement = params.placement;
    }
    if (Array.isArray(params.tags) && params.tags.length > 0) {
        spec.tags = params.tags;
    }
    return JSON.stringify(spec);
}

export function buildFlowSessionFileCreateSpecJson({ flowId, sessionId, isPublic = false }) {
    if (typeof flowId !== 'string' || flowId.length === 0) {
        throw new Error('buildFlowSessionFileCreateSpecJson: flowId required');
    }
    if (typeof sessionId !== 'string' || sessionId.length === 0) {
        throw new Error('buildFlowSessionFileCreateSpecJson: sessionId required');
    }
    return buildFileCreateSpecJson({
        sourceKind: 'flow_session',
        sourceRef: { session_id: sessionId, flow_id: flowId },
        postCreate: { is_public: isPublic },
    });
}

export function buildFlowAssetFileCreateSpecJson({ flowId }) {
    if (typeof flowId !== 'string' || flowId.length === 0) {
        throw new Error('buildFlowAssetFileCreateSpecJson: flowId required');
    }
    return buildFileCreateSpecJson({
        sourceKind: 'flow_asset',
        sourceRef: { flow_id: flowId },
    });
}

export function buildSyncMessageFileCreateSpecJson({ channelId }) {
    if (typeof channelId !== 'string' || channelId.length === 0) {
        throw new Error('buildSyncMessageFileCreateSpecJson: channelId required');
    }
    return buildFileCreateSpecJson({
        sourceKind: 'sync_message',
        sourceRef: { channel_id: channelId },
    });
}

export function buildSyncChannelAssetFileCreateSpecJson({ channelId, purpose }) {
    if (typeof channelId !== 'string' || channelId.length === 0) {
        throw new Error('buildSyncChannelAssetFileCreateSpecJson: channelId required');
    }
    const metadata = typeof purpose === 'string' && purpose.length > 0
        ? { purpose }
        : undefined;
    return buildFileCreateSpecJson({
        sourceKind: 'sync_channel_asset',
        sourceRef: { channel_id: channelId },
        metadata,
    });
}

export function buildWorkItemFileCreateSpecJson({ workItemId }) {
    if (typeof workItemId !== 'string' || workItemId.length === 0) {
        throw new Error('buildWorkItemFileCreateSpecJson: workItemId required');
    }
    return buildFileCreateSpecJson({
        sourceKind: 'work_item',
        sourceRef: { work_item_id: workItemId },
    });
}

export function buildCalendarEventFileCreateSpecJson({ eventId }) {
    const sourceRef = typeof eventId === 'string' && eventId.length > 0
        ? { event_id: eventId }
        : {};
    return buildFileCreateSpecJson({
        sourceKind: 'calendar_event',
        sourceRef,
    });
}

export function buildPlatformAuxiliaryFileCreateSpecJson({ retentionKind, metadata }) {
    return buildFileCreateSpecJson({
        sourceKind: 'platform_auxiliary',
        sourceRef: {},
        retentionKind: typeof retentionKind === 'string' && retentionKind.length > 0
            ? retentionKind
            : 'platform_default',
        metadata: metadata && typeof metadata === 'object' ? metadata : undefined,
    });
}

export function buildRagDocumentFileCreateSpecJson({ namespaceId, ragMetadata }) {
    if (typeof namespaceId !== 'string' || namespaceId.length === 0) {
        throw new Error('buildRagDocumentFileCreateSpecJson: namespaceId required');
    }
    const postCreate = {
        is_public: false,
        rag_index_namespace: namespaceId,
    };
    if (ragMetadata && typeof ragMetadata === 'object') {
        postCreate.rag_metadata = ragMetadata;
    }
    return buildFileCreateSpecJson({
        sourceKind: 'rag_document',
        sourceRef: { namespace_id: namespaceId },
        postCreate,
    });
}
