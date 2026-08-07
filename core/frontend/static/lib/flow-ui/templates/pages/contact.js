import { flexLayout, gridLayout, placement, stackLayout, submitAction } from '../component-factory.js';
import { component, copy, surface } from './_shared.js';

export function contactSurface(surfaceId, locale) {
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['profile-card', 'contact-form'],
            container_layout: stackLayout('space.5'),
        }),
        'profile-card': component({
            component_id: 'profile-card',
            type: 'Card',
            kind: 'container',
            children: ['avatar-row', 'role-badge', 'bio'],
            container_layout: stackLayout('space.3'),
        }),
        'avatar-row': component({
            component_id: 'avatar-row',
            type: 'Section',
            kind: 'container',
            children: ['avatar', 'name'],
            container_layout: flexLayout({ direction: 'row', gap: 'space.3', justify: 'start' }),
        }),
        avatar: component({
            component_id: 'avatar',
            type: 'Avatar',
            properties: { name: copy(locale, 'Анна К.', 'Anna K.') },
        }),
        name: component({
            component_id: 'name',
            type: 'Heading',
            bindings: { text: '/content/contactName' },
            properties: { level: 2 },
        }),
        'role-badge': component({
            component_id: 'role-badge',
            type: 'Badge',
            properties: { label: copy(locale, 'Менеджер', 'Account manager') },
        }),
        bio: component({
            component_id: 'bio',
            type: 'Text',
            bindings: { text: '/content/bio' },
        }),
        'contact-form': component({
            component_id: 'contact-form',
            type: 'Form',
            kind: 'container',
            children: ['field-subject', 'field-message', 'form-submit'],
            container_layout: gridLayout({ compact: 4, medium: 8, wide: 12, gap: 'space.3' }),
            properties: { formId: 'contact-form' },
        }),
        'field-subject': component({
            component_id: 'field-subject',
            type: 'TextField',
            bindings: { value: '/values/subject' },
            properties: { label: copy(locale, 'Тема', 'Subject') },
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
            properties: { label: copy(locale, 'Написать', 'Send message'), variant: 'primary' },
            actions: submitAction('contact-form'),
            placement: placement({ column_span: 'full' }),
        }),
    }, {
        content: {
            contactName: copy(locale, 'Анна К.', 'Anna K.'),
            bio: copy(
                locale,
                'Отвечу на вопросы по продукту и подключению.',
                'Happy to help with product and onboarding questions.',
            ),
        },
        values: { subject: '', message: '' },
        system: {},
    });
}
