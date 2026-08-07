import { gridLayout, placement, stackLayout, submitAction } from '../component-factory.js';
import { component, copy, requiredCheck, surface } from './_shared.js';

export function validatedFormSurface(surfaceId, locale) {
    const requiredMessage = copy(locale, 'Обязательное поле', 'This field is required');
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['title', 'hint', 'validated-form'],
            container_layout: stackLayout('space.4'),
        }),
        title: component({
            component_id: 'title',
            type: 'Heading',
            bindings: { text: '/content/title' },
            properties: { level: 2 },
        }),
        hint: component({
            component_id: 'hint',
            type: 'Alert',
            properties: {
                message: copy(
                    locale,
                    'Поля с проверкой required — Submit не уйдёт, пока они пустые.',
                    'Required checks block Submit until the fields are filled.',
                ),
            },
        }),
        'validated-form': component({
            component_id: 'validated-form',
            type: 'Form',
            kind: 'container',
            children: ['field-name', 'field-email', 'field-company', 'form-submit'],
            container_layout: gridLayout({ compact: 4, medium: 8, wide: 12, gap: 'space.3' }),
            properties: { formId: 'validated-form' },
        }),
        'field-name': component({
            component_id: 'field-name',
            type: 'TextField',
            bindings: { value: '/values/name' },
            properties: { label: copy(locale, 'Имя', 'Name') },
            checks: [requiredCheck(requiredMessage)],
            placement: placement({ column_span: 'full' }),
        }),
        'field-email': component({
            component_id: 'field-email',
            type: 'TextField',
            bindings: { value: '/values/email' },
            properties: { label: 'Email', placeholder: 'name@company.com' },
            checks: [requiredCheck(requiredMessage)],
            placement: placement({ column_span: 'full' }),
        }),
        'field-company': component({
            component_id: 'field-company',
            type: 'TextField',
            bindings: { value: '/values/company' },
            properties: { label: copy(locale, 'Компания', 'Company') },
            placement: placement({ column_span: 'full' }),
        }),
        'form-submit': component({
            component_id: 'form-submit',
            type: 'Button',
            properties: { label: copy(locale, 'Отправить', 'Submit'), variant: 'primary' },
            actions: submitAction('validated-form'),
            placement: placement({ column_span: 'full' }),
        }),
    }, {
        content: {
            title: copy(locale, 'Форма с валидацией', 'Validated form'),
        },
        values: { name: '', email: '', company: '' },
        system: {},
    });
}
