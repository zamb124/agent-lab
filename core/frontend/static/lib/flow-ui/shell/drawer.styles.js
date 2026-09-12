/** Стили ``<flow-ui-drawer>``: launcher-кластер, панель, resize-handle, mobile fullscreen. */

import { css } from '../../lit-shim.js';

export const flowUIDrawerStyles = css`
        :host {
            position: fixed;
            z-index: 2147483000;
            font-family: system-ui;
        }
        :host([data-drawer-gestures='on']) {
            inset: 0;
            pointer-events: none;
        }
        :host(:not([data-drawer-gestures='on'])) {
            inset: auto 22px 22px auto;
        }
        :host(:not([data-drawer-gestures='on'])[data-embed-position='bottom-left']) {
            inset: auto auto 22px 22px;
        }
        .launcher {
            width: 58px; height: 58px; padding: 0; border: 1px solid var(--flow-ui-logo-disc-border, rgba(255, 255, 255, 0.14));
            border-radius: 50%; cursor: pointer; display: grid; place-items: center;
            background: var(--flow-ui-logo-disc-bg, #0c0c0f);
            box-shadow: var(
                --flow-ui-logo-disc-shadow,
                0 1px 0 rgba(255, 255, 255, 0.1) inset,
                0 14px 36px rgba(0, 0, 0, 0.45),
                0 4px 12px rgba(0, 0, 0, 0.3)
            );
            overflow: visible;
            touch-action: none;
            pointer-events: auto;
        }
        :host([data-drawer-gestures='on']) .launcher {
            position: absolute;
        }
        :host([data-drawer-dragging='move']) .launcher,
        :host([data-drawer-dragging='move']) .panel {
            cursor: grabbing;
        }
        .launcher img {
            width: 34px; height: 34px; object-fit: contain; display: block; pointer-events: none;
        }
        .panel {
            position: absolute; right: 0; bottom: 70px; width: min(430px, calc(100vw - 24px));
            height: min(720px, calc(100vh - 110px)); transform-origin: bottom right;
            transition: opacity .18s ease, transform .18s ease;
            display: flex;
            flex-direction: column;
            min-height: 0;
            overflow: visible;
            border-radius: var(--flow-ui-radius-2xl, 24px);
            pointer-events: auto;
        }
        :host([data-drawer-gestures='on']) .panel {
            right: auto;
            bottom: auto;
            width: var(--drawer-panel-width);
            height: var(--drawer-panel-height);
        }
        :host([data-embed-position='bottom-left']:not([data-drawer-gestures='on'])) .panel {
            right: auto; left: 0; transform-origin: bottom left;
        }
        :host(:not([open])) .panel { opacity: 0; transform: translateY(12px) scale(.98); pointer-events: none; }
        :host([expanded][open]) {
            inset: 0;
            pointer-events: none;
        }
        :host([expanded][open]) .panel {
            position: fixed;
            inset: 0;
            right: 0;
            left: 0;
            bottom: 0;
            width: 100vw;
            height: 100dvh;
            max-width: none;
            max-height: none;
            border-radius: 0;
            transform: none;
            pointer-events: auto;
        }
        :host([expanded][open]) platform-flow-ui {
            border-radius: 0;
        }
        :host([expanded][open]) .launcher,
        :host([expanded][open]) .resize-handle {
            display: none;
        }
        platform-flow-ui {
            flex: 1 1 0;
            min-height: 0;
            height: 100%;
            border: 1px solid var(--flow-ui-border, rgba(149, 163, 194, 0.2));
            border-radius: var(--flow-ui-radius-2xl, 24px);
        }
        .resize-handle {
            position: absolute;
            right: 2px;
            bottom: 2px;
            width: 18px;
            height: 18px;
            padding: 0;
            border: 0;
            cursor: nwse-resize;
            background: transparent;
            z-index: 2;
            touch-action: none;
            pointer-events: auto;
        }
        .resize-handle::before {
            content: '';
            position: absolute;
            right: 3px;
            bottom: 3px;
            width: 10px;
            height: 10px;
            border-right: 2px solid var(--flow-ui-muted, rgba(149, 163, 194, 0.7));
            border-bottom: 2px solid var(--flow-ui-muted, rgba(149, 163, 194, 0.7));
            border-radius: 0 0 2px 0;
        }
        :host(:not([open])) .resize-handle,
        :host(:not([data-drawer-gestures='on'])) .resize-handle {
            display: none;
        }
        @media (max-width: 520px) {
            :host { inset: auto 10px 10px 10px; pointer-events: none; }
            .panel {
                position: fixed;
                inset: 0;
                width: 100vw;
                height: 100dvh;
                left: 0;
                top: 0;
                right: 0;
                bottom: 0;
                pointer-events: auto;
            }
            .launcher {
                position: relative;
                margin-left: auto;
                display: grid;
                pointer-events: auto;
            }
            .resize-handle { display: none; }
        }
        @media (prefers-reduced-motion: reduce) { .panel { transition: none; } }
    `;
