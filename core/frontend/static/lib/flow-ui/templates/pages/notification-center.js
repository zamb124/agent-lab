import { flexLayout, stackLayout, submitAction } from '../component-factory.js';
import { component, copy, surface } from './_shared.js';

export function notificationCenterSurface(surfaceId, locale) {
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['title', 'notifications', 'actions'],
            container_layout: stackLayout('space.4'),
        }),
        title: component({
            component_id: 'title',
            type: 'Heading',
            bindings: { text: '/content/title' },
            properties: { level: 2 },
        }),
        notifications: component({
            component_id: 'notifications',
            type: 'Stack',
            kind: 'container',
            children: ['n1', 'n2', 'n3'],
            container_layout: stackLayout('space.3'),
        }),
        n1: component({
            component_id: 'n1',
            type: 'Card',
            kind: 'container',
            children: ['n1-badge', 'n1-alert'],
            container_layout: stackLayout('space.2'),
        }),
        'n1-badge': component({
            component_id: 'n1-badge',
            type: 'Badge',
            properties: { label: copy(locale, 'Новое', 'New') },
        }),
        'n1-alert': component({
            component_id: 'n1-alert',
            type: 'Alert',
            properties: {
                message: copy(locale, 'Flow «Поддержка» завершил задачу.', 'Flow Support completed a task.'),
            },
        }),
        n2: component({
            component_id: 'n2',
            type: 'Card',
            kind: 'container',
            children: ['n2-badge', 'n2-alert'],
            container_layout: stackLayout('space.2'),
        }),
        'n2-badge': component({
            component_id: 'n2-badge',
            type: 'Badge',
            properties: { label: copy(locale, 'HITL', 'HITL') },
        }),
        'n2-alert': component({
            component_id: 'n2-alert',
            type: 'Alert',
            properties: {
                message: copy(
                    locale,
                    'Нужно подтверждение оператора по заявке #92.',
                    'Operator confirmation needed for request #92.',
                ),
            },
        }),
        n3: component({
            component_id: 'n3',
            type: 'Card',
            kind: 'container',
            children: ['n3-status', 'n3-text'],
            container_layout: stackLayout('space.2'),
        }),
        'n3-status': component({
            component_id: 'n3-status',
            type: 'Status',
            properties: { label: copy(locale, 'Прочитано', 'Read') },
        }),
        'n3-text': component({
            component_id: 'n3-text',
            type: 'Text',
            properties: {
                text: copy(locale, 'Экспорт отчёта готов к скачиванию.', 'Report export is ready to download.'),
            },
        }),
        actions: component({
            component_id: 'actions',
            type: 'Section',
            kind: 'container',
            children: ['mark-read', 'refresh'],
            container_layout: flexLayout({ direction: 'row', gap: 'space.3', justify: 'start' }),
        }),
        'mark-read': component({
            component_id: 'mark-read',
            type: 'Button',
            properties: { label: copy(locale, 'Прочитать все', 'Mark all read'), variant: 'secondary' },
            actions: submitAction(null),
        }),
        refresh: component({
            component_id: 'refresh',
            type: 'Button',
            properties: { label: copy(locale, 'Обновить', 'Refresh'), variant: 'primary' },
            actions: submitAction(null),
        }),
    }, {
        content: {
            title: copy(locale, 'Уведомления', 'Notifications'),
        },
        values: {},
        system: {},
    });
}
