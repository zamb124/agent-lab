import { stackLayout, submitAction } from '../component-factory.js';
import { component, copy, surface } from './_shared.js';

export function statusTrackerSurface(surfaceId, locale) {
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['title', 'order-id', 'progress', 'steps', 'refresh'],
            container_layout: stackLayout('space.4'),
        }),
        title: component({
            component_id: 'title',
            type: 'Heading',
            bindings: { text: '/content/title' },
            properties: { level: 2 },
        }),
        'order-id': component({
            component_id: 'order-id',
            type: 'Badge',
            properties: { label: 'ORD-1842' },
        }),
        progress: component({
            component_id: 'progress',
            type: 'Progress',
            properties: { value: 60, max: 100 },
        }),
        steps: component({
            component_id: 'steps',
            type: 'Stack',
            kind: 'container',
            children: ['step-1', 'step-2', 'step-3', 'step-4'],
            container_layout: stackLayout('space.2'),
        }),
        'step-1': component({
            component_id: 'step-1',
            type: 'Status',
            properties: { label: copy(locale, 'Заказ принят', 'Order received') },
        }),
        'step-2': component({
            component_id: 'step-2',
            type: 'Status',
            properties: { label: copy(locale, 'Собран на складе', 'Packed at warehouse') },
        }),
        'step-3': component({
            component_id: 'step-3',
            type: 'Status',
            properties: { label: copy(locale, 'В пути', 'In transit') },
        }),
        'step-4': component({
            component_id: 'step-4',
            type: 'Alert',
            properties: {
                message: copy(locale, 'Ожидается доставка завтра.', 'Delivery expected tomorrow.'),
            },
        }),
        refresh: component({
            component_id: 'refresh',
            type: 'Button',
            properties: { label: copy(locale, 'Обновить статус', 'Refresh status'), variant: 'primary' },
            actions: submitAction(null),
        }),
    }, {
        content: {
            title: copy(locale, 'Статус доставки', 'Shipping status'),
        },
        values: {},
        system: {},
    });
}
