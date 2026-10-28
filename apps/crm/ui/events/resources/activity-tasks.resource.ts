/**
 * crm/activity_task_create — атомарная пара CRMEntity(task) + WorkItem(crm_activity).
 */

import { createAsyncOp, createForm } from '@platform/lib/events/index.js';

export const activityTaskCreateOp = createAsyncOp({
    name: 'crm/activity_task_create',
    successToastKey: 'crm:toast.activity_task_created',
    errorToastKey: 'crm:toast.activity_task_create_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/activity_tasks/create_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/activity-tasks' },
});

export const activityTasksListOp = createAsyncOp({
    name: 'crm/activity_tasks_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/activity_tasks/list_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/activity-tasks' },
});

export const activityTaskCreateForm = createForm({
    name: 'crm/activity_task_create_form',
    schema: {
        title: { required: true },
        description: {},
        namespace: { required: true },
        priority: { required: true },
        due_date: {},
    },
    initial: {
        title: '',
        description: '',
        namespace: '',
        priority: 'normal',
        due_date: '',
    },
    submitEvent: activityTaskCreateOp.events.REQUESTED,
    buildPayload: (draft) => {
        if (!draft || typeof draft !== 'object') {
            throw new Error('activityTaskCreateForm: draft required');
        }
        if (typeof draft.title !== 'string' || draft.title.trim().length === 0) {
            throw new Error('activityTaskCreateForm: title required');
        }
        if (typeof draft.namespace !== 'string' || draft.namespace.length === 0) {
            throw new Error('activityTaskCreateForm: namespace required');
        }
        if (typeof draft.priority !== 'string' || draft.priority.length === 0) {
            throw new Error('activityTaskCreateForm: priority required');
        }
        const payload: Record<string, any> = {
            title: draft.title.trim(),
            namespace: draft.namespace,
            priority: draft.priority,
        };
        if (typeof draft.description === 'string' && draft.description.length > 0) {
            payload.description = draft.description;
        }
        if (typeof draft.due_date === 'string' && draft.due_date.length > 0) {
            payload.due_date = draft.due_date;
        }
        return payload;
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/activity_task_create': typeof activityTaskCreateOp;
        'crm/activity_tasks_list': typeof activityTasksListOp;
        'crm/activity_task_create_form': typeof activityTaskCreateForm;
    }
}
