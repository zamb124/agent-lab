function _nonEmptyString(value: unknown) {
    return typeof value === 'string' && value.length > 0 ? value : null;
}

export function buildSyncAssistantContext(routeKey: unknown, params: Record<string, unknown>, channelsState: Record<string, unknown>, threadsState: Record<string, unknown>, callUiState: Record<string, unknown>) {
    if (typeof routeKey !== 'string' || routeKey.length === 0) {
        throw new Error('buildSyncAssistantContext: routeKey required');
    }
    if (!params || typeof params !== 'object') {
        throw new Error('buildSyncAssistantContext: params required');
    }
    if (!channelsState || typeof channelsState !== 'object') {
        throw new Error('buildSyncAssistantContext: channelsState required');
    }
    if (!threadsState || typeof threadsState !== 'object') {
        throw new Error('buildSyncAssistantContext: threadsState required');
    }
    if (!callUiState || typeof callUiState !== 'object') {
        throw new Error('buildSyncAssistantContext: callUiState required');
    }

    const context: Record<string, unknown> = {
        service: 'sync',
        route_key: routeKey,
        screen: routeKey,
    };
    const routeChannelId = _nonEmptyString(params.channelId);
    const selectedChannelId = _nonEmptyString(channelsState.selectedChannelId);
    if (routeChannelId !== null) {
        context.channel_id = routeChannelId;
    } else if (selectedChannelId !== null) {
        context.channel_id = selectedChannelId;
    }
    const threadId = _nonEmptyString(threadsState.selectedThreadId);
    if (threadId !== null) {
        context.thread_id = threadId;
    }
    if (callUiState.activeCall && typeof callUiState.activeCall === 'object') {
        const callId = _nonEmptyString((callUiState.activeCall as Record<string, unknown>).call_id);
        if (callId !== null) {
            context.call_id = callId;
        }
    }
    return context;
}
