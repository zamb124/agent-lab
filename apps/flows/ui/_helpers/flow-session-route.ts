/**
 * Route params that open a session on the branch it belongs to.
 * `SessionConfig.branch_id` is authoritative: a session cannot change branch, and a
 * base-flow session uses the plain session route.
 *
 * @param {{ flow_id?: string, session_id?: string, branch_id?: string }} session
 * @returns {{ routeKey: string, params: object } | null}
 */
export function flowSessionRoute(session: any) {
    if (session === null || typeof session !== 'object') {
        throw new Error('flowSessionRoute: session object required');
    }
    const flowId = typeof session.flow_id === 'string' ? session.flow_id.trim() : '';
    const sessionId = typeof session.session_id === 'string' ? session.session_id.trim() : '';
    if (flowId.length === 0 || sessionId.length === 0) {
        return null;
    }
    const branchId = typeof session.branch_id === 'string' ? session.branch_id.trim() : '';
    if (branchId.length > 0 && branchId !== 'default' && branchId !== 'base') {
        return {
            routeKey: 'flow_chat_branch_session',
            params: { flowId, branchId, sessionId },
        };
    }
    return { routeKey: 'flow_chat_session', params: { flowId, sessionId } };
}
