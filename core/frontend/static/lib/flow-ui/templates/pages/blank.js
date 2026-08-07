import { stackLayout, submitAction } from '../component-factory.js';
import { component, copy, surface } from './_shared.js';

export function blankSurface(surfaceId, locale) {
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['heading', 'submit'],
            container_layout: stackLayout('space.4'),
        }),
        heading: component({
            component_id: 'heading',
            type: 'Heading',
            properties: { text: copy(locale, 'Новая страница', 'New page'), level: 2 },
        }),
        submit: component({
            component_id: 'submit',
            type: 'Button',
            properties: { label: copy(locale, 'Отправить', 'Submit'), variant: 'primary' },
            actions: submitAction(null),
        }),
    }, { content: {}, values: {}, system: {} });
}
