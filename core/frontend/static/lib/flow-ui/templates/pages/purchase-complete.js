import { flexLayout, stackLayout, submitAction } from '../component-factory.js';
import { component, copy, surface } from './_shared.js';

export function purchaseCompleteSurface(surfaceId, locale) {
    return surface(surfaceId, {
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['success', 'details', 'actions'],
            container_layout: stackLayout('space.5'),
        }),
        success: component({
            component_id: 'success',
            type: 'EmptyState',
            bindings: { message: '/content/message' },
        }),
        details: component({
            component_id: 'details',
            type: 'Alert',
            bindings: { message: '/content/receipt' },
        }),
        actions: component({
            component_id: 'actions',
            type: 'Section',
            kind: 'container',
            children: ['continue', 'receipt'],
            container_layout: flexLayout({ direction: 'row', gap: 'space.3', justify: 'start' }),
        }),
        continue: component({
            component_id: 'continue',
            type: 'Button',
            properties: { label: copy(locale, 'Продолжить', 'Continue'), variant: 'primary' },
            actions: submitAction(null),
        }),
        receipt: component({
            component_id: 'receipt',
            type: 'Button',
            properties: { label: copy(locale, 'Квитанция', 'View receipt'), variant: 'secondary' },
            actions: submitAction(null),
        }),
    }, {
        content: {
            message: copy(locale, 'Оплата прошла успешно', 'Payment complete'),
            receipt: copy(
                locale,
                'Заказ #1842 подтверждён. Чек отправлен на email.',
                'Order #1842 confirmed. Receipt sent to email.',
            ),
        },
        values: {},
        system: {},
    });
}
