import { gridLayout, placement, stackLayout, submitAction } from '../component-factory.js';
import { component, copy, surface } from './_shared.js';

export function loginSurface(surfaceId, locale) {
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['hero', 'login-form'],
            container_layout: stackLayout('space.5'),
        }),
        hero: component({
            component_id: 'hero',
            type: 'Section',
            kind: 'container',
            children: ['title', 'subtitle'],
            container_layout: stackLayout('space.2'),
        }),
        title: component({
            component_id: 'title',
            type: 'Heading',
            bindings: { text: '/content/title' },
            properties: { level: 1 },
        }),
        subtitle: component({
            component_id: 'subtitle',
            type: 'Text',
            bindings: { text: '/content/subtitle' },
        }),
        'login-form': component({
            component_id: 'login-form',
            type: 'Form',
            kind: 'container',
            children: ['field-email', 'field-password', 'form-submit'],
            container_layout: gridLayout({ compact: 4, medium: 8, wide: 12, gap: 'space.3' }),
            properties: { formId: 'login-form' },
        }),
        'field-email': component({
            component_id: 'field-email',
            type: 'TextField',
            bindings: { value: '/values/email' },
            properties: { label: 'Email', placeholder: 'name@company.com' },
            placement: placement({ column_span: 'full' }),
        }),
        'field-password': component({
            component_id: 'field-password',
            type: 'TextField',
            bindings: { value: '/values/password' },
            properties: {
                label: copy(locale, 'Пароль', 'Password'),
                placeholder: '••••••••',
            },
            placement: placement({ column_span: 'full' }),
        }),
        'form-submit': component({
            component_id: 'form-submit',
            type: 'Button',
            properties: { label: copy(locale, 'Войти', 'Sign in'), variant: 'primary' },
            actions: submitAction('login-form'),
            placement: placement({ column_span: 'full' }),
        }),
    }, {
        content: {
            title: copy(locale, 'Вход', 'Sign in'),
            subtitle: copy(
                locale,
                'Войдите, чтобы продолжить работу с агентом.',
                'Sign in to continue with the agent.',
            ),
        },
        values: { email: '', password: '' },
        system: {},
    });
}
