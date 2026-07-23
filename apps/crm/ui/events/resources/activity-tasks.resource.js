/**
 * crm/activity_task_create — атомарная пара CRMEntity(task) + WorkItem(crm_activity).
 */

import { createAsyncOp, createForm } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const activityTaskCreateOp = createAsyncOp({
    name: 'crm/activity_task_create',
    successToastKey: 'crm:toast.activity_task_created',
    errorToastKey: 'crm:toast.activity_task_create_failed',
    restMirror: { method: 'POST', path: '/crm/api/v1/activity-tasks' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('activityTaskCreateOp: payload required');
        }
        if (typeof payload.title !== 'string' || payload.title.trim().length === 0) {
            throw new Error('activityTaskCreateOp: payload.title required');
        }
        const body = {
            title: payload.title.trim(),
            namespace: typeof payload.namespace === 'string' && payload.namespace.length > 0
                ? payload.namespace
                : 'default',
        };
        if (typeof payload.description === 'string') {
            body.description = payload.description;
        }
        if (typeof payload.entity_subtype === 'string' && payload.entity_subtype.length > 0) {
            body.entity_subtype = payload.entity_subtype;
        }
        if (typeof payload.priority === 'string' && payload.priority.length > 0) {
            body.priority = payload.priority;
        }
        if (typeof payload.due_date === 'string' && payload.due_date.length > 0) {
            body.due_date = payload.due_date;
        }
        if (Array.isArray(payload.assignees)) {
            body.assignees = payload.assignees.filter((id) => typeof id === 'string' && id.length > 0);
        }
        if (Array.isArray(payload.tags)) {
            body.tags = payload.tags.filter((tag) => typeof tag === 'string' && tag.length > 0);
        }
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/activity-tasks',
            body,
        });
    },
});

export const activityTaskCreateForm = createForm({
    name: 'crm/activity_task_create_form',
    schema: {
        title: { type: 'string', required: true },
        description: { type: 'string' },
        namespace: { type: 'string', required: true },
        priority: { type: 'string' },
        due_date: { type: 'string' },
    },
    initial: {
        title: '',
        description: '',
        namespace: 'default',
        priority: 'normal',
        due_date: '',
    },
    submitEvent: activityTaskCreateOp.events.REQUESTED,
    buildPayload: (draft) => {
        const payload = {
            title: typeof draft.title === 'string' ? draft.title.trim() : '',
            namespace: typeof draft.namespace === 'string' && draft.namespace.length > 0
                ? draft.namespace
                : 'default',
            priority: typeof draft.priority === 'string' && draft.priority
                ? draft.priority
                : 'normal',
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
