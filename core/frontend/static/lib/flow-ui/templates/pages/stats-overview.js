import { gridCell, gridLayout, stackLayout, submitAction } from '../component-factory.js';
import { component, copy, surface } from './_shared.js';

export function statsOverviewSurface(surfaceId, locale) {
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['title', 'alert', 'metrics', 'status-row', 'refresh'],
            container_layout: stackLayout('space.4'),
        }),
        title: component({
            component_id: 'title',
            type: 'Heading',
            bindings: { text: '/content/title' },
            properties: { level: 2 },
        }),
        alert: component({
            component_id: 'alert',
            type: 'Alert',
            bindings: { message: '/content/alert' },
        }),
        metrics: component({
            component_id: 'metrics',
            type: 'Grid',
            kind: 'container',
            children: ['metric-revenue', 'metric-users', 'metric-conversion', 'metric-latency'],
            container_layout: gridLayout({ compact: 4, medium: 8, wide: 12 }),
        }),
        'metric-revenue': component({
            component_id: 'metric-revenue',
            type: 'Metric',
            bindings: { value: '/content/metrics/revenue' },
            properties: { label: copy(locale, 'Выручка', 'Revenue') },
            placement: gridCell({ column: 1, span: 3, row: 1, narrowRow: 1 }),
        }),
        'metric-users': component({
            component_id: 'metric-users',
            type: 'Metric',
            bindings: { value: '/content/metrics/users' },
            properties: { label: copy(locale, 'Пользователи', 'Users') },
            placement: gridCell({ column: 4, span: 3, row: 1, narrowRow: 2 }),
        }),
        'metric-conversion': component({
            component_id: 'metric-conversion',
            type: 'Metric',
            bindings: { value: '/content/metrics/conversion' },
            properties: { label: copy(locale, 'Конверсия', 'Conversion') },
            placement: gridCell({ column: 7, span: 3, row: 1, narrowRow: 3 }),
        }),
        'metric-latency': component({
            component_id: 'metric-latency',
            type: 'Metric',
            bindings: { value: '/content/metrics/latency' },
            properties: { label: copy(locale, 'Задержка', 'Latency') },
            placement: gridCell({ column: 10, span: 3, row: 1, narrowRow: 4 }),
        }),
        'status-row': component({
            component_id: 'status-row',
            type: 'Section',
            kind: 'container',
            children: ['status', 'progress'],
            container_layout: stackLayout('space.3'),
        }),
        status: component({
            component_id: 'status',
            type: 'Status',
            properties: { label: copy(locale, 'Система в норме', 'All systems nominal') },
        }),
        progress: component({
            component_id: 'progress',
            type: 'Progress',
            properties: { value: 72, max: 100 },
        }),
        refresh: component({
            component_id: 'refresh',
            type: 'Button',
            properties: { label: copy(locale, 'Обновить', 'Refresh'), variant: 'primary' },
            actions: submitAction(null),
        }),
    }, {
        content: {
            title: copy(locale, 'Статистика', 'Stats overview'),
            alert: copy(locale, 'Данные за последние 24 часа.', 'Last 24 hours snapshot.'),
            metrics: {
                revenue: '₽1.2M',
                users: '4 812',
                conversion: '3.4%',
                latency: '180 ms',
            },
        },
        values: {},
        system: {},
    });
}
