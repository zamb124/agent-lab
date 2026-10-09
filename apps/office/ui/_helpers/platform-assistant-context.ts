function _nonEmptyString(value: unknown): string | null {
    return typeof value === 'string' && value.length > 0 ? value : null;
}

interface OfficeAssistantContext {
    service: string;
    route_key: string;
    screen: string;
    file_id?: string;
    catalog_id?: string;
    document_type?: string;
    [key: string]: unknown;
}

function _lookupDocumentType(items: unknown, fileId: string | null): string | null {
    if (!Array.isArray(items) || fileId === null) {
        return null;
    }
    const item = (items as { file_id?: unknown; onlyoffice_document_type?: unknown }[]).find(
        (candidate) => candidate && candidate.file_id === fileId,
    );
    return item ? _nonEmptyString(item.onlyoffice_document_type) : null;
}

export function buildOfficeAssistantContext(
    routeKey: string | null,
    params: Record<string, string>,
    documentsState: Record<string, unknown>,
): OfficeAssistantContext {
    if (typeof routeKey !== 'string' || routeKey.length === 0) {
        throw new Error('buildOfficeAssistantContext: routeKey required');
    }
    if (!params || typeof params !== 'object') {
        throw new Error('buildOfficeAssistantContext: params required');
    }
    if (!documentsState || typeof documentsState !== 'object') {
        throw new Error('buildOfficeAssistantContext: documentsState required');
    }
    const context: OfficeAssistantContext = {
        service: 'office',
        route_key: routeKey,
        screen: routeKey,
    };
    const routeFileId = _nonEmptyString(params.fileId);
    const selectedFileId = _nonEmptyString(documentsState.selectedFileId);
    const fileId = routeFileId !== null ? routeFileId : selectedFileId;
    if (fileId !== null) {
        context.file_id = fileId;
    }
    const catalogId = _nonEmptyString(documentsState.activeCatalogId);
    if (catalogId !== null) {
        context.catalog_id = catalogId;
    }
    const documentType = _lookupDocumentType(documentsState.items, fileId);
    if (documentType !== null) {
        context.document_type = documentType;
    }
    return context;
}
