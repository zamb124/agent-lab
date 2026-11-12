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
    mail_message: 'mail_attachment',
    wiki_page: 'wiki_page',
    code_agent_source: 'flow_asset',
    platform_auxiliary: 'platform_default',
    generated_ephemeral: 'generated_ephemeral',
    product: 'product',
    stock_entity: 'platform_default',
});

function defaultRetentionKind(sourceKind: string): string | undefined {
    switch (sourceKind) {
        case 'crm_entity':
            return DEFAULT_RETENTION_BY_SOURCE.crm_entity;
        case 'flow_session':
            return DEFAULT_RETENTION_BY_SOURCE.flow_session;
        case 'flow_asset':
            return DEFAULT_RETENTION_BY_SOURCE.flow_asset;
        case 'work_item':
            return DEFAULT_RETENTION_BY_SOURCE.work_item;
        case 'sync_message':
            return DEFAULT_RETENTION_BY_SOURCE.sync_message;
        case 'sync_channel_asset':
            return DEFAULT_RETENTION_BY_SOURCE.sync_channel_asset;
        case 'sync_call_recording':
            return DEFAULT_RETENTION_BY_SOURCE.sync_call_recording;
        case 'sync_speech_segment':
            return DEFAULT_RETENTION_BY_SOURCE.sync_speech_segment;
        case 'browser_artifact':
            return DEFAULT_RETENTION_BY_SOURCE.browser_artifact;
        case 'rag_document':
            return DEFAULT_RETENTION_BY_SOURCE.rag_document;
        case 'office_document':
            return DEFAULT_RETENTION_BY_SOURCE.office_document;
        case 'calendar_event':
            return DEFAULT_RETENTION_BY_SOURCE.calendar_event;
        case 'mail_message':
            return DEFAULT_RETENTION_BY_SOURCE.mail_message;
        case 'wiki_page':
            return DEFAULT_RETENTION_BY_SOURCE.wiki_page;
        case 'code_agent_source':
            return DEFAULT_RETENTION_BY_SOURCE.code_agent_source;
        case 'platform_auxiliary':
            return DEFAULT_RETENTION_BY_SOURCE.platform_auxiliary;
        case 'generated_ephemeral':
            return DEFAULT_RETENTION_BY_SOURCE.generated_ephemeral;
        case 'product':
            return DEFAULT_RETENTION_BY_SOURCE.product;
        case 'stock_entity':
            return DEFAULT_RETENTION_BY_SOURCE.stock_entity;
        default:
            return undefined;
    }
}

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
export interface FileCreateSpecParams {
    sourceKind: string;
    sourceRef?: Record<string, unknown>;
    retentionKind?: string;
    postCreate?: Record<string, unknown>;
    metadata?: Record<string, unknown> | undefined;
    placement?: Record<string, unknown>;
    tags?: string[];
}

export function buildFileCreateSpecJson(params: FileCreateSpecParams): string {
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
        : defaultRetentionKind(sourceKind);
    if (typeof retentionKind !== 'string' || retentionKind.length === 0) {
        throw new Error(`buildFileCreateSpecJson: retentionKind required for sourceKind=${sourceKind}`);
    }
    const spec: Record<string, unknown> = {
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

export function buildFlowSessionFileCreateSpecJson({ flowId, sessionId, isPublic = false }: { flowId: string; sessionId: string; isPublic?: boolean }): string {
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

export function buildFlowAssetFileCreateSpecJson({ flowId, isPublic = false }: { flowId: string; isPublic?: boolean }): string {
    if (typeof flowId !== 'string' || flowId.length === 0) {
        throw new Error('buildFlowAssetFileCreateSpecJson: flowId required');
    }
    if (typeof isPublic !== 'boolean') {
        throw new Error('buildFlowAssetFileCreateSpecJson: isPublic must be boolean');
    }
    return buildFileCreateSpecJson({
        sourceKind: 'flow_asset',
        sourceRef: { flow_id: flowId },
        postCreate: { is_public: isPublic },
    });
}

export function buildSyncMessageFileCreateSpecJson({ channelId }: { channelId: string }): string {
    if (typeof channelId !== 'string' || channelId.length === 0) {
        throw new Error('buildSyncMessageFileCreateSpecJson: channelId required');
    }
    return buildFileCreateSpecJson({
        sourceKind: 'sync_message',
        sourceRef: { channel_id: channelId },
    });
}

export function buildSyncChannelAssetFileCreateSpecJson({ channelId, purpose }: { channelId: string; purpose?: string }): string {
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

export function buildWorkItemFileCreateSpecJson({ workItemId, workQueueId, boardId }: { workItemId: string; workQueueId?: string; boardId?: string }): string {
    if (typeof workItemId !== 'string' || workItemId.length === 0) {
        throw new Error('buildWorkItemFileCreateSpecJson: workItemId required');
    }
    const sourceRef: Record<string, string> = { work_item_id: workItemId };
    if (typeof workQueueId === 'string' && workQueueId.length > 0) {
        sourceRef.work_queue_id = workQueueId;
    }
    if (typeof boardId === 'string' && boardId.length > 0) {
        sourceRef.board_id = boardId;
    }
    return buildFileCreateSpecJson({
        sourceKind: 'work_item',
        sourceRef,
    });
}

export function buildCalendarEventFileCreateSpecJson({ eventId }: { eventId: string }): string {
    if (typeof eventId !== 'string' || eventId.length === 0) {
        throw new Error('buildCalendarEventFileCreateSpecJson: eventId required');
    }
    return buildFileCreateSpecJson({
        sourceKind: 'calendar_event',
        sourceRef: { event_id: eventId },
    });
}

export function buildPlatformAuxiliaryFileCreateSpecJson({ retentionKind, metadata }: { retentionKind?: string; metadata?: Record<string, unknown> }): string {
    return buildFileCreateSpecJson({
        sourceKind: 'platform_auxiliary',
        sourceRef: {},
        retentionKind: typeof retentionKind === 'string' && retentionKind.length > 0
            ? retentionKind
            : 'platform_default',
        metadata: metadata && typeof metadata === 'object' ? metadata : undefined,
    });
}

export function buildWikiPageFileCreateSpecJson({ wikiPageId, namespaceId, metadata }: { wikiPageId: string; namespaceId: string; metadata?: Record<string, unknown> }): string {
    if (typeof wikiPageId !== 'string' || wikiPageId.length === 0) {
        throw new Error('buildWikiPageFileCreateSpecJson: wikiPageId required');
    }
    if (typeof namespaceId !== 'string' || namespaceId.length === 0) {
        throw new Error('buildWikiPageFileCreateSpecJson: namespaceId required');
    }
    return buildFileCreateSpecJson({
        sourceKind: 'wiki_page',
        sourceRef: {
            wiki_page_id: wikiPageId,
            namespace_id: namespaceId,
        },
        metadata: metadata && typeof metadata === 'object' ? metadata : undefined,
    });
}

export function buildRagDocumentFileCreateSpecJson({ namespaceId, ragMetadata }: { namespaceId: string; ragMetadata?: Record<string, unknown> }): string {
    if (typeof namespaceId !== 'string' || namespaceId.length === 0) {
        throw new Error('buildRagDocumentFileCreateSpecJson: namespaceId required');
    }
    const postCreate: Record<string, unknown> = {
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

export function buildCrmEntityFileCreateSpecJson({ entityId, entityType, entityTitle }: { entityId: string; entityType: string; entityTitle?: string | undefined }): string {
    if (typeof entityId !== 'string' || entityId.length === 0) {
        throw new Error('buildCrmEntityFileCreateSpecJson: entityId required');
    }
    if (typeof entityType !== 'string' || entityType.length === 0) {
        throw new Error('buildCrmEntityFileCreateSpecJson: entityType required');
    }
    const title =
        typeof entityTitle === 'string' && entityTitle.length > 0 ? entityTitle : entityId;
    return buildFileCreateSpecJson({
        sourceKind: 'crm_entity',
        sourceRef: {
            entity_id: entityId,
            entity_type: entityType,
            entity_title: title,
        },
        postCreate: { is_public: false },
    });
}

export function buildCodeAgentSourceFileCreateSpecJson({
    flowId,
    nodeId,
    relativeDir,
}: {
    flowId: string;
    nodeId: string;
    relativeDir?: string | undefined;
}): string {
    if (typeof flowId !== 'string' || flowId.length === 0) {
        throw new Error('buildCodeAgentSourceFileCreateSpecJson: flowId required');
    }
    if (typeof nodeId !== 'string' || nodeId.length === 0) {
        throw new Error('buildCodeAgentSourceFileCreateSpecJson: nodeId required');
    }
    const sourceRef: Record<string, string> = { flow_id: flowId, node_id: nodeId };
    if (typeof relativeDir === 'string' && relativeDir.length > 0) {
        sourceRef.relative_dir = relativeDir;
    }
    return buildFileCreateSpecJson({
        sourceKind: 'code_agent_source',
        sourceRef,
        postCreate: { is_public: false },
    });
}

export function buildOfficeDocumentFileCreateSpecJson({ namespaceId, catalogId }: { namespaceId: string; catalogId: string }): string {
    if (typeof namespaceId !== 'string' || namespaceId.length === 0) {
        throw new Error('buildOfficeDocumentFileCreateSpecJson: namespaceId required');
    }
    if (typeof catalogId !== 'string' || catalogId.length === 0) {
        throw new Error('buildOfficeDocumentFileCreateSpecJson: catalogId required');
    }
    return buildFileCreateSpecJson({
        sourceKind: 'office_document',
        sourceRef: { entity_id: namespaceId },
        placement: { catalog_id: catalogId },
        postCreate: { is_public: false },
    });
}

export function buildShopProductFileCreateSpecJson({ shopId, productId }: { shopId: string; productId?: string }): string {
    if (typeof shopId !== 'string' || shopId.length === 0) {
        throw new Error('buildShopProductFileCreateSpecJson: shopId required');
    }
    const sourceRef: Record<string, string> = { shop_id: shopId };
    if (typeof productId === 'string' && productId.length > 0) {
        sourceRef.product_id = productId;
    }
    return buildFileCreateSpecJson({
        sourceKind: 'product',
        sourceRef,
        postCreate: { is_public: true },
    });
}
