import { flexLayout, gridCell, gridLayout, placement, stackLayout, submitAction } from '../component-factory.js';
import { component, copy, surface } from './_shared.js';

export function userProfileSurface(surfaceId, locale) {
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['header', 'profile-form'],
            container_layout: stackLayout('space.5'),
        }),
        header: component({
            component_id: 'header',
            type: 'Section',
            kind: 'container',
            children: ['avatar', 'heading'],
            container_layout: flexLayout({ direction: 'row', gap: 'space.3', justify: 'start' }),
        }),
        avatar: component({
            component_id: 'avatar',
            type: 'Avatar',
            properties: { name: copy(locale, 'Пользователь', 'User') },
        }),
        heading: component({
            component_id: 'heading',
            type: 'Heading',
            bindings: { text: '/content/title' },
            properties: { level: 2 },
        }),
        'profile-form': component({
            component_id: 'profile-form',
            type: 'Form',
            kind: 'container',
            children: ['field-name', 'field-email', 'field-role', 'field-bio', 'form-submit'],
            container_layout: gridLayout({ compact: 4, medium: 8, wide: 12, gap: 'space.3' }),
            properties: { formId: 'profile-form' },
        }),
        'field-name': component({
            component_id: 'field-name',
            type: 'TextField',
            bindings: { value: '/values/name' },
            properties: { label: copy(locale, 'Имя', 'Name') },
            placement: gridCell({ column: 1, span: 6, row: 1, narrowRow: 1 }),
        }),
        'field-email': component({
            component_id: 'field-email',
            type: 'TextField',
            bindings: { value: '/values/email' },
            properties: { label: 'Email' },
            placement: gridCell({ column: 7, span: 6, row: 1, narrowRow: 2 }),
        }),
        'field-role': component({
            component_id: 'field-role',
            type: 'TextField',
            bindings: { value: '/values/role' },
            properties: { label: copy(locale, 'Роль', 'Role') },
            placement: placement({ column_span: 'full' }),
        }),
        'field-bio': component({
            component_id: 'field-bio',
            type: 'TextArea',
            bindings: { value: '/values/bio' },
            properties: { label: copy(locale, 'О себе', 'Bio'), rows: 3 },
            placement: placement({ column_span: 'full' }),
        }),
        'form-submit': component({
            component_id: 'form-submit',
            type: 'Button',
            properties: { label: copy(locale, 'Сохранить', 'Save profile'), variant: 'primary' },
            actions: submitAction('profile-form'),
            placement: placement({ column_span: 'full' }),
        }),
    }, {
        content: {
            title: copy(locale, 'Профиль', 'User profile'),
        },
        values: {
            name: copy(locale, 'Иван Петров', 'John Smith'),
            email: 'john@company.com',
            role: copy(locale, 'Разработчик', 'Developer'),
            bio: '',
        },
        system: {},
    });
}
