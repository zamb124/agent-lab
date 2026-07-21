/**
 * Work queues — список/создание очередей для hitl_node editor.
 *
 * REST зеркало: GET/POST /flows/api/v1/work-queues (WorkItemService →
 * platform_worktracker). В NodeConfig хранится work_queue_slug.
 */

import { createResourceCollection } from '@platform/lib/events/index.js';

/**
 * @param {unknown} raw
 * @returns {{
 *   work_queue_id: string,
 *   work_queue_slug: string,
 *   name: string,
 *   description: string | null,
 * }}
 */
function mapWorkQueue(raw) {
    if (raw === null || typeof raw !== 'object') {
        throw new Error('flows/work_queues.mapItem: object required');
    }
    const row = /** @type {Record<string, unknown>} */ (raw);
    if (typeof row.work_queue_id !== 'string' || row.work_queue_id.length === 0) {
        throw new Error('flows/work_queues.mapItem: work_queue_id required');
    }
    if (typeof row.work_queue_slug !== 'string' || row.work_queue_slug.length === 0) {
        throw new Error('flows/work_queues.mapItem: work_queue_slug required');
    }
    if (typeof row.name !== 'string' || row.name.length === 0) {
        throw new Error('flows/work_queues.mapItem: name required');
    }
    return {
        work_queue_id: row.work_queue_id,
        work_queue_slug: row.work_queue_slug,
        name: row.name,
        description: typeof row.description === 'string' ? row.description : null,
    };
}

export const workQueuesResource = createResourceCollection({
    name: 'flows/work_queues',
    baseUrl: '/flows/api/v1/work-queues',
    idField: 'work_queue_id',
    operations: ['list', 'create'],
    mapItem: mapWorkQueue,
    toastKeys: {
        create: 'flows:toast.work_queue_created',
        create_error: 'flows:toast.work_queue_create_error',
    },
});
