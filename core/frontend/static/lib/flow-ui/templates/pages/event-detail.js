import { gridCell, gridLayout, placement, stackLayout, submitAction } from '../component-factory.js';
import { component, copy, surface } from './_shared.js';

export function eventDetailSurface(surfaceId, locale) {
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['title', 'meta', 'description', 'rsvp-form'],
            container_layout: stackLayout('space.4'),
        }),
        title: component({
            component_id: 'title',
            type: 'Heading',
            bindings: { text: '/content/title' },
            properties: { level: 1 },
        }),
        meta: component({
            component_id: 'meta',
            type: 'Section',
            kind: 'container',
            children: ['when-badge', 'where-badge'],
            container_layout: stackLayout('space.2'),
        }),
        'when-badge': component({
            component_id: 'when-badge',
            type: 'Badge',
            properties: { label: copy(locale, 'Чт, 18:00', 'Thu, 6:00 PM') },
        }),
        'where-badge': component({
            component_id: 'where-badge',
            type: 'Status',
            properties: { label: copy(locale, 'Онлайн', 'Online') },
        }),
        description: component({
            component_id: 'description',
            type: 'Markdown',
            bindings: { content: '/content/description' },
        }),
        'rsvp-form': component({
            component_id: 'rsvp-form',
            type: 'Form',
            kind: 'container',
            children: ['field-date', 'field-guests', 'field-note', 'form-submit'],
            container_layout: gridLayout({ compact: 4, medium: 8, wide: 12, gap: 'space.3' }),
            properties: { formId: 'rsvp-form' },
        }),
        'field-date': component({
            component_id: 'field-date',
            type: 'DatePicker',
            bindings: { value: '/values/date' },
            properties: { label: copy(locale, 'Дата участия', 'Attendance date') },
            placement: gridCell({ column: 1, span: 6, row: 1, narrowRow: 1 }),
        }),
        'field-guests': component({
            component_id: 'field-guests',
            type: 'NumberField',
            bindings: { value: '/values/guests' },
            properties: { label: copy(locale, 'Гостей', 'Guests') },
            placement: gridCell({ column: 7, span: 6, row: 1, narrowRow: 2 }),
        }),
        'field-note': component({
            component_id: 'field-note',
            type: 'TextArea',
            bindings: { value: '/values/note' },
            properties: { label: copy(locale, 'Комментарий', 'Note'), rows: 3 },
            placement: placement({ column_span: 'full' }),
        }),
        'form-submit': component({
            component_id: 'form-submit',
            type: 'Button',
            properties: { label: copy(locale, 'Записаться', 'RSVP'), variant: 'primary' },
            actions: submitAction('rsvp-form'),
            placement: placement({ column_span: 'full' }),
        }),
    }, {
        content: {
            title: copy(locale, 'Демо Flow UI', 'Flow UI demo day'),
            description: copy(
                locale,
                'Покажем галерею шаблонов и live-редактор интерфейса.',
                'Walkthrough of the template gallery and live interface editor.',
            ),
        },
        values: { date: '', guests: 1, note: '' },
        system: {},
    });
}
