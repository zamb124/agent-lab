import { flexLayout, stackLayout, submitAction } from '../component-factory.js';
import { component, copy, surface } from './_shared.js';

export function taskListSurface(surfaceId, locale) {
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['title', 'task-list', 'refresh'],
            container_layout: stackLayout('space.4'),
        }),
        title: component({
            component_id: 'title',
            type: 'Heading',
            bindings: { text: '/content/title' },
            properties: { level: 2 },
        }),
        'task-list': component({
            component_id: 'task-list',
            type: 'Stack',
            kind: 'container',
            children: ['task-1', 'task-2', 'task-3'],
            container_layout: stackLayout('space.3'),
        }),
        'task-1': component({
            component_id: 'task-1',
            type: 'Card',
            kind: 'container',
            children: ['task-1-head', 'task-1-body'],
            container_layout: stackLayout('space.2'),
        }),
        'task-1-head': component({
            component_id: 'task-1-head',
            type: 'Section',
            kind: 'container',
            children: ['task-1-title', 'task-1-badge'],
            container_layout: flexLayout({ direction: 'row', gap: 'space.2', justify: 'space-between' }),
        }),
        'task-1-title': component({
            component_id: 'task-1-title',
            type: 'Heading',
            properties: { text: copy(locale, 'Проверить заявку', 'Review request'), level: 3 },
        }),
        'task-1-badge': component({
            component_id: 'task-1-badge',
            type: 'Badge',
            properties: { label: copy(locale, 'Срочно', 'Urgent') },
        }),
        'task-1-body': component({
            component_id: 'task-1-body',
            type: 'Text',
            properties: {
                text: copy(locale, 'Клиент ждёт ответ по интеграции.', 'Customer waiting on integration reply.'),
            },
        }),
        'task-2': component({
            component_id: 'task-2',
            type: 'Card',
            kind: 'container',
            children: ['task-2-head', 'task-2-body'],
            container_layout: stackLayout('space.2'),
        }),
        'task-2-head': component({
            component_id: 'task-2-head',
            type: 'Section',
            kind: 'container',
            children: ['task-2-title', 'task-2-status'],
            container_layout: flexLayout({ direction: 'row', gap: 'space.2', justify: 'space-between' }),
        }),
        'task-2-title': component({
            component_id: 'task-2-title',
            type: 'Heading',
            properties: { text: copy(locale, 'Обновить базу знаний', 'Update knowledge base'), level: 3 },
        }),
        'task-2-status': component({
            component_id: 'task-2-status',
            type: 'Status',
            properties: { label: copy(locale, 'В работе', 'In progress') },
        }),
        'task-2-body': component({
            component_id: 'task-2-body',
            type: 'Text',
            properties: {
                text: copy(locale, 'Добавить FAQ по биллингу.', 'Add billing FAQ entries.'),
            },
        }),
        'task-3': component({
            component_id: 'task-3',
            type: 'Card',
            kind: 'container',
            children: ['task-3-head', 'task-3-body'],
            container_layout: stackLayout('space.2'),
        }),
        'task-3-head': component({
            component_id: 'task-3-head',
            type: 'Section',
            kind: 'container',
            children: ['task-3-title', 'task-3-badge'],
            container_layout: flexLayout({ direction: 'row', gap: 'space.2', justify: 'space-between' }),
        }),
        'task-3-title': component({
            component_id: 'task-3-title',
            type: 'Heading',
            properties: { text: copy(locale, 'Подготовить отчёт', 'Prepare report'), level: 3 },
        }),
        'task-3-badge': component({
            component_id: 'task-3-badge',
            type: 'Badge',
            properties: { label: copy(locale, 'Позже', 'Later') },
        }),
        'task-3-body': component({
            component_id: 'task-3-body',
            type: 'Text',
            properties: {
                text: copy(locale, 'Сводка по задачам за неделю.', 'Weekly task summary.'),
            },
        }),
        refresh: component({
            component_id: 'refresh',
            type: 'Button',
            properties: { label: copy(locale, 'Обновить список', 'Refresh list'), variant: 'primary' },
            actions: submitAction(null),
        }),
    }, {
        content: {
            title: copy(locale, 'Задачи', 'Tasks'),
        },
        values: {},
        system: {},
    });
}
