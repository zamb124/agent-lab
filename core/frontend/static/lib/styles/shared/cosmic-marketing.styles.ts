/**
 * Cosmic marketing primitives — общие стили публичных «космических» страниц
 * (landing + product pages). Реализуют язык quantumwallet.tech поверх DS:
 * Michroma→Unbounded display-заголовки, моно-микролейблы, тёмные glass-панели,
 * chamfered-кнопки, градиентный текст, reveal по IntersectionObserver.
 *
 * Значения — только токены `--marketing-cosmic-*` из tokens.css. Пин-секции
 * `[data-cosmic-pin]` и reveal действуют только при no-preference motion.
 */
import { css } from 'lit';

/** Типографика и микролейблы космического маркетинга. */
export const cosmicTypeStyles = css`
    .cosmic-headline {
        font-family: var(--font-display);
        font-size: var(--marketing-cosmic-headline-size);
        font-weight: 400;
        line-height: 0.98;
        letter-spacing: -0.01em;
        text-transform: uppercase;
        color: var(--marketing-cosmic-text);
        margin: 0;
    }

    .cosmic-headline--right { text-align: right; }
    .cosmic-headline--center { text-align: center; }

    .cosmic-sub {
        font-size: var(--marketing-cosmic-sub-size);
        font-weight: 500;
        line-height: 1.25;
        color: var(--marketing-cosmic-text);
        margin: 0;
    }

    .cosmic-copy {
        font-size: var(--text-lg);
        line-height: var(--leading-relaxed);
        color: var(--marketing-cosmic-muted);
        margin: 0;
    }

    .cosmic-mono {
        font-family: var(--font-mono);
        font-size: var(--text-xs);
        font-weight: 600;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: var(--marketing-cosmic-label);
    }

    .cosmic-grad-text {
        background: var(--marketing-cosmic-grad);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
`;

/** Панели, кнопки, разметка глав. */
export const cosmicUiStyles = css`
    .cosmic-panel {
        background: var(--marketing-cosmic-panel-bg);
        border: 1px solid var(--marketing-cosmic-panel-border);
        border-radius: var(--radius-xl);
        box-shadow: var(--marketing-cosmic-panel-shadow);
        backdrop-filter: blur(18px);
    }

    .cosmic-panel--pad {
        padding: var(--space-8);
    }

    .cosmic-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: var(--space-2);
        min-height: 3rem;
        padding: 0 var(--space-6);
        border: 1px solid var(--marketing-cosmic-panel-border-strong);
        border-radius: 0;
        clip-path: var(--marketing-cosmic-btn-clip);
        background: var(--marketing-cosmic-glass);
        color: var(--marketing-cosmic-text);
        font-family: var(--font-sans);
        font-size: var(--text-base);
        font-weight: 500;
        letter-spacing: 0.02em;
        text-decoration: none;
        cursor: pointer;
        overflow: hidden;
        position: relative;
        transition:
            background var(--motion-duration-enter) var(--motion-ease-decelerate),
            border-color var(--motion-duration-enter) var(--motion-ease-decelerate),
            transform var(--motion-duration-enter) var(--motion-ease-decelerate);
    }

    .cosmic-btn:hover {
        background: var(--marketing-cosmic-glass-strong);
        border-color: var(--marketing-cosmic-cyan);
        transform: translateY(-1px);
    }

    .cosmic-btn--primary {
        background: var(--marketing-cosmic-cyan);
        border-color: var(--marketing-cosmic-cyan);
        color: var(--marketing-cosmic-bg);
        font-weight: 600;
    }

    .cosmic-btn--primary:hover {
        background: var(--marketing-cosmic-text);
        border-color: var(--marketing-cosmic-text);
        color: var(--marketing-cosmic-bg);
    }

    /* Вертикальный ролл текста в кнопке (hover-приём QW):
       .cosmic-btn-roll держит две копии label, при hover уезжает вверх. */
    .cosmic-btn-roll {
        display: inline-flex;
        flex-direction: column;
        height: 1.2em;
        overflow: hidden;
        line-height: 1.2;
    }

    .cosmic-btn-roll > span {
        display: block;
        transition: transform 300ms cubic-bezier(0.19, 1, 0.22, 1);
    }

    .cosmic-btn:hover .cosmic-btn-roll > span {
        transform: translateY(-100%);
    }

    .cosmic-rule {
        height: 1px;
        background: var(--marketing-cosmic-line);
        border: 0;
        margin: 0;
    }

    .cosmic-section {
        position: relative;
        padding: var(--space-16) var(--marketing-section-padding-x);
    }

    .cosmic-chapter-head {
        display: grid;
        gap: var(--space-4);
        margin-bottom: var(--space-10);
        max-width: var(--marketing-content-max-width);
        margin-left: auto;
        margin-right: auto;
    }

    /* reveal: элемент входит во вьюпорт → IO ставит .inview */
    [data-cosmic-reveal] {
        opacity: 0;
        transform: translate3d(0, 2.5rem, 0);
        transition:
            opacity 700ms cubic-bezier(0.19, 1, 0.22, 1),
            transform 700ms cubic-bezier(0.19, 1, 0.22, 1);
        transition-delay: var(--cosmic-reveal-delay, 0ms);
    }

    [data-cosmic-reveal].inview {
        opacity: 1;
        transform: translate3d(0, 0, 0);
    }

    @media (prefers-reduced-motion: reduce) {
        [data-cosmic-reveal] {
            opacity: 1;
            transform: none;
            transition: none;
        }
    }
`;

/**
 * Sticky-траверс пин-секций: <section data-cosmic-pin="N"> растягивается на N
 * экранов, прямой потомок прилипает к вьюпорту, а CosmicScrollController
 * крутит --cosmic-section-t (0..1) — внутренние анимации секции читают var.
 */
export const cosmicPinStyles = css`
    @media (prefers-reduced-motion: no-preference) {
        section[data-cosmic-pin='2'] { height: 200vh; }
        section[data-cosmic-pin='3'] { height: 300vh; }
        section[data-cosmic-pin='4'] { height: 400vh; }

        section[data-cosmic-pin] > * {
            position: sticky;
            top: 0;
            height: var(--app-vh, 100vh);
            overflow: clip;
        }

        .cosmic-traverse {
            display: flex;
            gap: var(--space-6);
            will-change: transform;
            transform: translate3d(calc(var(--cosmic-section-t, 0) * -60%), 0, 0);
        }
    }
`;
