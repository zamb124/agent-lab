/**
 * Flows-catalog op — каталог flows и tools для выбора в embed/scheduler модалках.
 *
 * Один загрузочный вызов читает /flows/api/v1/flows/ и /flows/api/v1/tools/
 * параллельно и кладёт обе коллекции в lastResult = { flows, tools }. У каждого
 * LOCAL flow в items есть branches (ветки/skill); embed-модалка выбирает branch_id.
 *
 * Без toast'ов: операция идёт в фоне модалки.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const flowsCatalogOp = createAsyncOp({
    name: 'frontend/flows_catalog',
    silent: true,
    // Cross-service вызов: составной запрос /flows/api/v1/flows/ + /tools/.
    // CI (check_command_rest_mirror.py) распознаёт `service:` в restMirror
    // как явную декларацию cross-service и не верифицирует path.
    restMirror: { method: 'GET', path: '/flows/api/v1/flows/', service: 'flows' },
    request: async () => {
        const [flows, tools] = await Promise.all([
            httpRequest({ method: 'GET', url: '/flows/api/v1/flows/' }),
            httpRequest({ method: 'GET', url: '/flows/api/v1/tools/' }),
        ]);
        return {
            flows: Array.isArray(flows.items) ? flows.items : [],
            tools: Array.isArray(tools.items) ? tools.items : [],
        };
    },
});
