/**
 * Дизайн-токены ТСД (`/stock/tsd`) — локальный масштаб поверх core-токенов.
 *
 * ТСД живёт в светлой теме (lock в tsd.html) и держит собственные имена:
 * core-токены не правятся, мобильный масштаб консоли не страдает. Токены
 * монтируются один раз на `:host` приложения и наследуются всеми экранами.
 */

import { css } from 'lit';

export const tsdTokens = css`
    :host {
        /* Тач-цели: кладовщик в перчатках, одна рука, устойчивый промах. */
        --tsd-touch-min: 56px;
        --tsd-touch-lg: 72px;

        /* Типографика крупнее консольной — экран читается на расстоянии руки. */
        --tsd-text-body: var(--text-lg);
        --tsd-text-title: var(--text-2xl);
        --tsd-text-hero: var(--text-3xl);

        /* Поверхности ТСД непрозрачные: оператор работает одной рукой
           на ходу — сквозь лист не должна мерцать подложка экрана. */
        --glass-solid-strong: var(--bg-surface);

        /* Состояния шага: скан ok / предупреждение / ошибка / инфо-подсказка. */
        --tsd-ok: var(--color-success, #16a34a);
        --tsd-ok-subtle: var(--bg-success-subtle, #dcfce7);
        --tsd-warn: var(--color-warning, #d97706);
        --tsd-warn-subtle: var(--bg-warning-subtle, #fef3c7);
        --tsd-error: var(--color-danger, #dc2626);
        --tsd-error-subtle: var(--bg-danger-subtle, #fee2e2);
        --tsd-info: var(--accent);
        --tsd-info-subtle: var(--accent-subtle);
    }
`;
