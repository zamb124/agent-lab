import { stackLayout, submitAction } from '../component-factory.js';
import { component, copy, surface } from './_shared.js';

export function productDetailSurface(surfaceId, locale) {
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['image', 'title', 'price', 'description', 'cta'],
            container_layout: stackLayout('space.4'),
        }),
        image: component({
            component_id: 'image',
            type: 'Image',
            properties: {
                src: '/static/core/assets/service_logos/linnex_spinner_logo.png',
                alt: copy(locale, 'Продукт', 'Product'),
            },
        }),
        title: component({
            component_id: 'title',
            type: 'Heading',
            bindings: { text: '/content/title' },
            properties: { level: 1 },
        }),
        price: component({
            component_id: 'price',
            type: 'Metric',
            bindings: { value: '/content/price' },
            properties: { label: copy(locale, 'Цена', 'Price') },
        }),
        description: component({
            component_id: 'description',
            type: 'Markdown',
            bindings: { content: '/content/description' },
        }),
        cta: component({
            component_id: 'cta',
            type: 'Button',
            properties: { label: copy(locale, 'Купить', 'Buy now'), variant: 'primary' },
            actions: submitAction(null),
        }),
    }, {
        content: {
            title: copy(locale, 'Платформенный тариф Pro', 'Platform Pro plan'),
            price: '₽4 990',
            description: copy(
                locale,
                'Полный доступ к flows, sync и CRM для команды до 20 человек.',
                'Full access to flows, sync and CRM for teams up to 20.',
            ),
        },
        values: {},
        system: {},
    });
}
