import { gridCell, gridLayout, stackLayout, submitAction } from '../component-factory.js';
import { component, copy, surface } from './_shared.js';

export function dashboardSurface(surfaceId, locale) {
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['title', 'metrics', 'table', 'refresh'],
            container_layout: stackLayout('space.5'),
        }),
        title: component({
            component_id: 'title',
            type: 'Heading',
            bindings: { text: '/content/title' },
            properties: { level: 2 },
        }),
        metrics: component({
            component_id: 'metrics',
            type: 'Grid',
            kind: 'container',
            children: ['metric-total', 'metric-open', 'metric-done'],
            container_layout: gridLayout({ compact: 4, medium: 8, wide: 12 }),
        }),
        'metric-total': component({
            component_id: 'metric-total',
            type: 'Metric',
            bindings: { value: '/content/metrics/total' },
            properties: { label: copy(locale, 'Всего', 'Total') },
            placement: gridCell({ column: 1, span: 4, row: 1, narrowRow: 1 }),
        }),
        'metric-open': component({
            component_id: 'metric-open',
            type: 'Metric',
            bindings: { value: '/content/metrics/open' },
            properties: { label: copy(locale, 'В работе', 'Open') },
            placement: gridCell({ column: 5, span: 4, row: 1, narrowRow: 2 }),
        }),
        'metric-done': component({
            component_id: 'metric-done',
            type: 'Metric',
            bindings: { value: '/content/metrics/done' },
            properties: { label: copy(locale, 'Готово', 'Done') },
            placement: gridCell({ column: 9, span: 4, row: 1, narrowRow: 3 }),
        }),
        table: component({
            component_id: 'table',
            type: 'DataTable',
            bindings: { rows: '/content/rows' },
            properties: {
                columns: [
                    { key: 'name', label: copy(locale, 'Название', 'Name') },
                    { key: 'status', label: copy(locale, 'Статус', 'Status') },
                ],
            },
        }),
        refresh: component({
            component_id: 'refresh',
            type: 'Button',
            properties: { label: copy(locale, 'Обновить', 'Refresh'), variant: 'primary' },
            actions: submitAction(null),
        }),
    }, {
        content: {
            title: copy(locale, 'Обзор', 'Overview'),
            metrics: { total: 0, open: 0, done: 0 },
            rows: [],
        },
        values: {},
        system: {},
    });
}
