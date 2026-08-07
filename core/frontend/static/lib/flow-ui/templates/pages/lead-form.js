import { gridLayout, placement, stackLayout, submitAction } from '../component-factory.js';
import { component, copy, surface } from './_shared.js';

export function leadFormSurface(surfaceId, locale) {
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['hero', 'request-form'],
            container_layout: stackLayout('space.6'),
        }),
        hero: component({
            component_id: 'hero',
            type: 'Section',
            kind: 'container',
            children: ['hero-title', 'hero-text'],
            container_layout: gridLayout({ compact: 4, medium: 8, wide: 12, gap: 'space.2' }),
        }),
        'hero-title': component({
            component_id: 'hero-title',
            type: 'Heading',
            bindings: { text: '/content/title' },
            properties: { level: 1 },
            placement: placement({ column_span: 'full' }),
        }),
        'hero-text': component({
            component_id: 'hero-text',
            type: 'Text',
            bindings: { text: '/content/subtitle' },
            placement: placement({ column_span: 'full' }),
        }),
        'request-form': component({
            component_id: 'request-form',
            type: 'Form',
            kind: 'container',
            children: ['field-name', 'field-email', 'field-message', 'form-submit'],
            container_layout: gridLayout({ compact: 4, medium: 8, wide: 12, gap: 'space.3' }),
            properties: { formId: 'request-form' },
        }),
        'field-name': component({
            component_id: 'field-name',
            type: 'TextField',
            bindings: { value: '/values/name' },
            properties: { label: copy(locale, 'Имя', 'Name'), placeholder: 'Jane Doe' },
            placement: placement({ column_span: 'full' }),
        }),
        'field-email': component({
            component_id: 'field-email',
            type: 'TextField',
            bindings: { value: '/values/email' },
            properties: { label: 'Email', placeholder: 'name@company.com' },
            placement: placement({ column_span: 'full' }),
        }),
        'field-message': component({
            component_id: 'field-message',
            type: 'TextArea',
            bindings: { value: '/values/message' },
            properties: { label: copy(locale, 'Сообщение', 'Message'), rows: 4 },
            placement: placement({ column_span: 'full' }),
        }),
        'form-submit': component({
            component_id: 'form-submit',
            type: 'Button',
            properties: { label: copy(locale, 'Отправить заявку', 'Send request'), variant: 'primary' },
            actions: submitAction('request-form'),
            placement: placement({ column_span: 'full' }),
        }),
    }, {
        content: {
            title: copy(locale, 'Чем можем помочь?', 'How can we help?'),
            subtitle: copy(
                locale,
                'Оставьте заявку — агент ответит прямо в этом интерфейсе.',
                'Leave a request and the agent will reply in this interface.',
            ),
        },
        values: { name: '', email: '', message: '' },
        system: {},
    });
}
