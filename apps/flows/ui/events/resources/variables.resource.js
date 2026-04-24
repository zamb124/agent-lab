/**
 * Variables — глобальные переменные company-уровня (KV).
 * REST: `apps/flows/src/api/v1/variables.py`.
 *
 * `baseUrl` с завершающим `/` совпадает с каноничным POST/GET коллекции в тестах
 * (`/flows/api/v1/variables/`). Иначе браузер может получить редирект на URL со
 * слэшем и пустое тело ответа на create — фабрика падает с «create response missing key».
 */

import { createResourceCollection } from '@platform/lib/events/index.js';

const VARIABLES_COLLECTION_URL = '/flows/api/v1/variables/';

export const variablesResource = createResourceCollection({
    name: 'flows/variables',
    baseUrl: VARIABLES_COLLECTION_URL,
    idField: 'key',
    itemPathTemplate: '/flows/api/v1/variables/:key',
    buildItemUrl: (id) => `/flows/api/v1/variables/${encodeURIComponent(id)}`,
    operations: ['list', 'get', 'create', 'remove'],
    toastKeys: {
        create: 'flows:toast.variable_created',
        create_error: 'flows:toast.variable_create_error',
        remove: 'flows:toast.variable_removed',
        remove_error: 'flows:toast.variable_remove_error',
    },
});
