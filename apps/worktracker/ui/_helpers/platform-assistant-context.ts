function _nonEmptyString(value: unknown): string | null {
    return typeof value === 'string' && value.length > 0 ? value : null;
}

interface WorktrackerAssistantContext {
    service: string;
    route_key: string;
    screen: string;
    work_item_id?: string;
    work_queue_id?: string;
    [key: string]: unknown;
}

export function buildWorktrackerAssistantContext(
    routeKey: string | null,
    params: Record<string, string>,
    detailWorkItemId: unknown,
): WorktrackerAssistantContext {
    if (typeof routeKey !== 'string' || routeKey.length === 0) {
        throw new Error('buildWorktrackerAssistantContext: routeKey required');
    }
    if (!params || typeof params !== 'object') {
        throw new Error('buildWorktrackerAssistantContext: params required');
    }
    const context: WorktrackerAssistantContext = {
        service: 'worktracker',
        route_key: routeKey,
        screen: routeKey,
    };
    const routeWorkItemId = _nonEmptyString(params.workItemId);
    const panelWorkItemId = _nonEmptyString(detailWorkItemId);
    if (routeWorkItemId !== null) {
        context.work_item_id = routeWorkItemId;
    } else if (panelWorkItemId !== null) {
        context.work_item_id = panelWorkItemId;
    }
    const workQueueId = _nonEmptyString(params.workQueueId);
    if (workQueueId !== null) {
        context.work_queue_id = workQueueId;
    }
    return context;
}
