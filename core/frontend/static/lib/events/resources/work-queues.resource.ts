/**
 * WorkQueue — фабрика владельца домена worktracker (worktracker SPA + HITL editor).
 */

import { createResourceCollection } from '../index.js';

export const workQueuesResource = createResourceCollection({
    name: 'worktracker/work_queues',
    baseUrl: '/worktracker/api/v1/work-queues',
    idField: 'work_queue_id',
    operations: ['list', 'create'],
    transport: 'ws',
    wsTimeoutMs: 5_000,
    toastKeys: {
        create: 'worktracker:toast.queue_created',
        create_error: 'worktracker:toast.queue_create_failed',
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'worktracker/work_queues': typeof workQueuesResource;
    }
}
