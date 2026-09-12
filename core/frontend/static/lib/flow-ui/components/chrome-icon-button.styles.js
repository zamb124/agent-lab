/** Круглая иконка-кнопка chrome ``<platform-flow-ui>`` и её меню; общая для хоста и share/embed. */

import { css } from '../../lit-shim.js';

export const chromeIconButtonStyles = css`
        .chrome-icon-btn {
            width: 36px; height: 36px; min-height: 36px; padding: 0; border-radius: 50%;
            display: inline-grid; place-items: center; cursor: pointer; box-sizing: border-box;
            border: 1px solid var(--flow-ui-border);
            background: color-mix(in srgb, var(--flow-ui-panel-strong, var(--flow-ui-panel)) 92%, transparent);
            color: var(--flow-ui-text);
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            transition: var(--flow-ui-transition);
        }
        .chrome-icon-btn:hover:not(:disabled) {
            border-color: color-mix(in srgb, var(--flow-ui-text) 22%, var(--flow-ui-border));
            background: color-mix(in srgb, var(--flow-ui-surface-hover) 70%, var(--flow-ui-panel-strong, var(--flow-ui-panel)));
        }
        .chrome-icon-btn:focus-visible { outline: none; box-shadow: var(--flow-ui-focus-ring); }
        .chrome-icon-btn:disabled { opacity: .72; cursor: default; }
        /* Глиф перекрашивается токеном темы хоста — без :host-context (нет в Safari/Firefox). */
        .chrome-icon-btn .fu-glyph {
            display: block;
            filter: var(--flow-ui-glyph-filter, brightness(0) saturate(100%) invert(88%) opacity(0.92));
        }
        .chrome-icon-btn:hover:not(:disabled) .fu-glyph {
            opacity: 1;
        }
        @media (prefers-reduced-motion: reduce) { .chrome-icon-btn { transition: none; } }
`;
