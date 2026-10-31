/**
 * Слой platform motion.
 *
 * Motion по умолчанию сначала идёт через compositor: opacity + transform. Компоненты могут включать
 * семантические классы, но layout-свойства по умолчанию никогда не анимируются.
 */
import { css } from 'lit';

export const motionStyles = css`
    :host {
        --motion-transition-interactive:
            background-color var(--motion-duration-micro) var(--motion-ease-standard),
            border-color var(--motion-duration-micro) var(--motion-ease-standard),
            color var(--motion-duration-micro) var(--motion-ease-standard),
            box-shadow var(--motion-duration-micro) var(--motion-ease-standard),
            opacity var(--motion-duration-micro) var(--motion-ease-standard),
            transform var(--motion-duration-micro) var(--motion-ease-standard);
        --motion-transition-surface:
            opacity var(--motion-duration-enter) var(--motion-ease-decelerate),
            transform var(--motion-duration-enter) var(--motion-ease-decelerate);
    }

    @keyframes platformMotionFadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }

    @keyframes platformMotionFadeOut {
        from { opacity: 1; }
        to { opacity: 0; }
    }

    @keyframes platformMotionEnterUp {
        from {
            opacity: 0;
            transform: translate3d(0, var(--motion-enter-offset-y), 0) scale(0.98);
        }
        to {
            opacity: 1;
            transform: translate3d(0, 0, 0) scale(1);
        }
    }

    @keyframes platformMotionExitDown {
        from {
            opacity: 1;
            transform: translate3d(0, 0, 0) scale(1);
        }
        to {
            opacity: 0;
            transform: translate3d(0, var(--motion-exit-offset-y), 0) scale(0.98);
        }
    }

    @keyframes platformSkeletonPulse {
        0% { opacity: 0.48; }
        50% { opacity: 0.82; }
        100% { opacity: 0.48; }
    }

    .motion-surface,
    .motion-enter,
    .motion-exit {
        backface-visibility: hidden;
        transform: translateZ(0);
    }

    .motion-contained {
        contain: layout paint style;
    }

    .motion-interactive {
        transition: var(--motion-transition-interactive);
    }

    .motion-enter {
        animation: platformMotionEnterUp var(--motion-duration-enter)
            var(--motion-ease-decelerate) both;
    }

    .motion-exit {
        animation: platformMotionExitDown var(--motion-duration-exit)
            var(--motion-ease-accelerate) both;
        pointer-events: none;
    }

    .motion-fade-in {
        animation: platformMotionFadeIn var(--motion-duration-enter)
            var(--motion-ease-decelerate) both;
    }

    .motion-fade-out {
        animation: platformMotionFadeOut var(--motion-duration-exit)
            var(--motion-ease-accelerate) both;
        pointer-events: none;
    }

    .motion-skeleton {
        border-radius: var(--radius-md);
        background:
            linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.08), transparent),
            var(--glass-tint-medium);
        background-size: 220% 100%;
        animation: platformSkeletonPulse var(--motion-duration-loading)
            var(--motion-ease-standard) infinite;
    }

    .transition-fast,
    .transition-normal,
    .transition-slow,
    .transition-spring {
        transition: var(--motion-transition-interactive);
    }

    @supports (content-visibility: auto) {
        .motion-offscreen-contained {
            content-visibility: auto;
            contain-intrinsic-size: auto var(--motion-contain-intrinsic-block-size);
        }
    }

    @media (prefers-reduced-motion: reduce) {
        *,
        *::before,
        *::after {
            animation-duration: 1ms !important;
            animation-iteration-count: 1 !important;
            scroll-behavior: auto !important;
            transition-duration: 1ms !important;
        }
    }
`;
