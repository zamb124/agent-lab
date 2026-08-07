/**
 * Session descriptor + bootstrap/reconnect helpers for FlowUIController.
 */

import { createProtocolId } from '../protocol/a2a-codec.js';

/**
 * @param {{
 *   flowId: string,
 *   contextId?: string,
 *   taskId?: string,
 *   documentId?: string,
 *   revision?: number|string|null,
 *   branchId?: string,
 *   embedId?: string,
 * }} input
 */
export function createFlowUISessionDescriptor(input) {
    if (!input || typeof input !== 'object') {
        throw new Error('flow-ui-session: input required');
    }
    if (typeof input.flowId !== 'string' || input.flowId.trim() === '') {
        throw new Error('flow-ui-session: flowId required');
    }
    return Object.freeze({
        flowId: input.flowId.trim(),
        branchId: typeof input.branchId === 'string' && input.branchId.trim() !== ''
            ? input.branchId.trim()
            : 'default',
        embedId: typeof input.embedId === 'string' ? input.embedId.trim() : '',
        contextId: typeof input.contextId === 'string' ? input.contextId.trim() : '',
        taskId: typeof input.taskId === 'string' ? input.taskId.trim() : '',
        documentId: typeof input.documentId === 'string' ? input.documentId.trim() : '',
        revision: input.revision == null ? null : input.revision,
        sessionKey: createProtocolId('session'),
    });
}

/**
 * @param {import('./flow-ui-controller.js').FlowUIController} controller
 * @param {ReturnType<typeof createFlowUISessionDescriptor>} descriptor
 */
export async function bootstrapFlowUISession(controller, descriptor) {
    if (!controller || typeof controller.bootstrap !== 'function') {
        throw new Error('flow-ui-session: controller.bootstrap required');
    }
    if (!descriptor || typeof descriptor !== 'object') {
        throw new Error('flow-ui-session: descriptor required');
    }
    if (descriptor.contextId) {
        controller.contextId = descriptor.contextId;
    }
    await controller.bootstrap();
    return snapshotFlowUISession(controller, descriptor);
}

/**
 * @param {import('./flow-ui-controller.js').FlowUIController} controller
 * @param {ReturnType<typeof createFlowUISessionDescriptor>} descriptor
 */
export async function reconnectFlowUISession(controller, descriptor) {
    if (!controller || typeof controller.reconnect !== 'function') {
        if (!controller || typeof controller.bootstrap !== 'function') {
            throw new Error('flow-ui-session: controller.reconnect or bootstrap required');
        }
        await controller.bootstrap();
        return snapshotFlowUISession(controller, descriptor);
    }
    await controller.reconnect();
    return snapshotFlowUISession(controller, descriptor);
}

/**
 * @param {import('./flow-ui-controller.js').FlowUIController} controller
 * @param {ReturnType<typeof createFlowUISessionDescriptor>} [base]
 */
export function snapshotFlowUISession(controller, base = null) {
    if (!controller) {
        throw new Error('flow-ui-session: controller required');
    }
    const context = controller.activeContext;
    const document = controller.document;
    const tasks = context?.taskOrder
        ? context.taskOrder.map((taskId) => context.tasksById?.[taskId]).filter(Boolean)
        : [];
    const activeTask = tasks.length ? tasks[tasks.length - 1] : null;
    return Object.freeze({
        flowId: base?.flowId || controller.target?.flowId || '',
        branchId: base?.branchId || controller.target?.branchId || 'default',
        embedId: base?.embedId || controller.target?.embedId || '',
        contextId: controller.contextId || context?.contextId || '',
        taskId: activeTask?.id || base?.taskId || '',
        documentId: document?.document_id || base?.documentId || '',
        revision: document?.revision ?? context?.serverRevision ?? base?.revision ?? null,
        hydration: context?.hydration || 'idle',
        taskCount: tasks.length,
    });
}
