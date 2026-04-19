/**
 * Variables — глобальные переменные company-уровня (KV).
 * REST: `apps/flows/src/api/v1/variables.py`.
 */

import { createResourceCollection } from '@platform/lib/events/index.js';

export const variablesResource = createResourceCollection({
    name: 'flows/variables',
    baseUrl: '/flows/api/v1/variables',
    idField: 'key',
    operations: ['list', 'get', 'create', 'remove'],
    toastKeys: {
        create: 'flows:toast.variable_created',
        create_error: 'flows:toast.variable_create_error',
        remove: 'flows:toast.variable_removed',
        remove_error: 'flows:toast.variable_remove_error',
    },
});
