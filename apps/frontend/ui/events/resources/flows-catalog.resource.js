/**
 * Flows-catalog op — каталог flows и tools для выбора в embed/scheduler модалках.
 *
 * Один загрузочный вызов читает /flows/api/v1/flows/ и /flows/api/v1/tools/
 * параллельно и кладёт обе коллекции в lastResult = { flows, tools }. Тулзы и
 * флоу нужны вместе при настройке виджета: пользователь выбирает flow_id и
 * skill_id, поэтому хранение их в одном слайсе оправдано.
 *
 * Без toast'ов: операция идёт в фоне модалки.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const flowsCatalogOp = createAsyncOp({
    name: 'frontend/flows_catalog',
    silent: true,
    request: async () => {
        const [flows, tools] = await Promise.all([
            httpRequest({ method: 'GET', url: '/flows/api/v1/flows/' }),
            httpRequest({ method: 'GET', url: '/flows/api/v1/tools/' }),
        ]);
        return {
            flows: flows.items || [],
            tools: tools.items || [],
        };
    },
});
