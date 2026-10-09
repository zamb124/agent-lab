/** Стили chrome ``<platform-flow-ui>``: тема (embed без tokens.css), topbar, статусбар, HITL. */

import { css } from '../../lit-shim.js';

export const platformFlowUIStyles = css`
        :host {
            /* Типографика, радиусы и колонка чтения — одинаковы для SPA и embed (tokens.css их дублирует). */
            --flow-ui-font-size-body: 15px;
            --flow-ui-font-size-sm: 13px;
            --flow-ui-font-size-xs: 12px;
            --flow-ui-font-size-hero: 22px;
            --flow-ui-font-size-mono: 13px;
            --flow-ui-line-height: 1.6;
            --flow-ui-line-height-tight: 1.3;
            --flow-ui-radius-sm: 8px;
            --flow-ui-radius-md: 12px;
            --flow-ui-radius-lg: 16px;
            --flow-ui-radius-xl: 20px;
            --flow-ui-radius-2xl: 24px;
            --flow-ui-radius-full: 9999px;
            --flow-ui-radius: 24px;
            --flow-ui-space-1: 4px;
            --flow-ui-space-2: 8px;
            --flow-ui-space-3: 12px;
            --flow-ui-space-4: 16px;
            --flow-ui-space-5: 20px;
            --flow-ui-space-6: 24px;
            --flow-ui-space-8: 32px;
            --flow-ui-feed-width: 760px;
            --flow-ui-content-medium: 960px;
            --flow-ui-hero-mark: 64px;
            --flow-ui-glyph-filter: brightness(0) saturate(100%) invert(88%) opacity(0.92);
            --flow-ui-glyph-on-accent-filter: brightness(0) opacity(0.9);
            --flow-ui-transition:
                background-color 120ms cubic-bezier(0.4, 0, 0.2, 1),
                border-color 120ms cubic-bezier(0.4, 0, 0.2, 1),
                color 120ms cubic-bezier(0.4, 0, 0.2, 1),
                box-shadow 120ms cubic-bezier(0.4, 0, 0.2, 1),
                opacity 120ms cubic-bezier(0.4, 0, 0.2, 1),
                transform 120ms cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            flex-direction: column;
            min-width: 0;
            min-height: 0;
            height: 100%;
            overflow: hidden;
            color: var(--flow-ui-text);
            font-family: var(--font-sans);
            font-size: var(--flow-ui-font-size-body);
            line-height: var(--flow-ui-line-height);
            -webkit-font-smoothing: antialiased;
            scrollbar-width: thin;
            scrollbar-color: color-mix(in srgb, var(--flow-ui-text) 22%, transparent) transparent;
            background: var(--flow-ui-page-background, var(--bg-primary, #16213e));
        }
        :host([display='drawer']) {
            --flow-ui-font-size-body: 14px;
            --flow-ui-font-size-hero: 18px;
            --flow-ui-hero-mark: 52px;
        }
        /*
         * Embed host pages do not load platform tokens.css. Literal values only:
         * host --text-primary / color must not leak into the widget.
         */
        :host([data-resolved-theme="dark"]) {
            --flow-ui-text: rgba(255, 255, 255, 0.95);
            --flow-ui-text-secondary: rgba(255, 255, 255, 0.65);
            --flow-ui-heading: rgba(255, 255, 255, 0.95);
            --flow-ui-muted: rgba(255, 255, 255, 0.45);
            --flow-ui-border: rgba(255, 255, 255, 0.1);
            --flow-ui-border-strong: rgba(255, 255, 255, 0.06);
            --flow-ui-panel: rgba(35, 35, 55, 0.85);
            --flow-ui-panel-strong: rgba(40, 40, 64, 0.92);
            --flow-ui-surface: rgba(35, 35, 55, 0.85);
            --flow-ui-surface-subtle: rgba(28, 28, 46, 0.75);
            --flow-ui-surface-hover: rgba(255, 255, 255, 0.08);
            --flow-ui-card: rgba(255, 255, 255, 0.05);
            --flow-ui-input: rgba(0, 0, 0, 0.22);
            --flow-ui-code-bg: rgba(0, 0, 0, 0.28);
            --flow-ui-composer-bg: rgba(255, 255, 255, 0.06);
            --flow-ui-composer-shadow: 0 10px 32px rgba(0, 0, 0, 0.28);
            --flow-ui-user-bubble: rgba(255, 255, 255, 0.09);
            --flow-ui-user-bubble-text: rgba(255, 255, 255, 0.95);
            --flow-ui-page-background: #16213e;
            --flow-ui-accent: #99A6F9;
            --flow-ui-accent-hover: #8794F0;
            --flow-ui-on-accent: #0f0f1a;
            --flow-ui-accent-muted: rgba(153, 166, 249, 0.15);
            --flow-ui-button-text: #0f0f1a;
            --flow-ui-chip: rgba(153, 166, 249, 0.15);
            --flow-ui-interrupt-bg: rgba(153, 166, 249, 0.15);
            --flow-ui-focus-ring: 0 0 0 3px rgba(153, 166, 249, 0.4);
            --flow-ui-danger: #f43f5e;
            --flow-ui-success: #10b981;
            --flow-ui-warning: #f59e0b;
            --flow-ui-info: #3b82f6;
            --flow-ui-panel-shadow: 0 16px 48px rgba(0, 0, 0, 0.4), 0 4px 16px rgba(0, 0, 0, 0.25);
            --flow-ui-glyph-filter: brightness(0) saturate(100%) invert(88%) opacity(0.92);
            --flow-ui-glyph-on-accent-filter: brightness(0) opacity(0.9);
            --flow-ui-logo-disc-bg: #0c0c0f;
            --flow-ui-logo-disc-border: rgba(255, 255, 255, 0.14);
            --flow-ui-logo-disc-shadow: 0 1px 0 rgba(255, 255, 255, 0.1) inset, 0 10px 28px rgba(0, 0, 0, 0.5), 0 2px 8px rgba(0, 0, 0, 0.35);
            color: var(--flow-ui-text);
            background: var(--flow-ui-page-background);
        }
        :host([data-resolved-theme="light"]) {
            --flow-ui-text: #1c1f2e;
            --flow-ui-text-secondary: rgba(28, 31, 46, 0.65);
            --flow-ui-heading: #1c1f2e;
            --flow-ui-muted: rgba(28, 31, 46, 0.52);
            --flow-ui-border: rgba(28, 31, 46, 0.1);
            --flow-ui-border-strong: rgba(28, 31, 46, 0.08);
            --flow-ui-panel: rgba(255, 255, 255, 0.98);
            --flow-ui-panel-strong: #ffffff;
            --flow-ui-surface: rgba(28, 31, 46, 0.05);
            --flow-ui-surface-subtle: #f2f3f8;
            --flow-ui-surface-hover: rgba(28, 31, 46, 0.08);
            --flow-ui-card: #ffffff;
            --flow-ui-input: rgba(255, 255, 255, 0.92);
            --flow-ui-code-bg: #eef0f6;
            --flow-ui-composer-bg: #ffffff;
            --flow-ui-composer-shadow: 0 10px 32px rgba(22, 26, 38, 0.1);
            --flow-ui-user-bubble: #eceef5;
            --flow-ui-user-bubble-text: #1c1f2e;
            --flow-ui-page-background: #f8fafc;
            --flow-ui-accent: #6d62e8;
            --flow-ui-accent-hover: #5a50d4;
            --flow-ui-on-accent: #ffffff;
            --flow-ui-accent-muted: rgba(109, 98, 232, 0.2);
            --flow-ui-button-text: #ffffff;
            --flow-ui-chip: rgba(109, 98, 232, 0.14);
            --flow-ui-interrupt-bg: rgba(109, 98, 232, 0.1);
            --flow-ui-focus-ring: 0 0 0 3px rgba(109, 98, 232, 0.3);
            --flow-ui-danger: #e11d48;
            --flow-ui-success: #059669;
            --flow-ui-warning: #d97706;
            --flow-ui-info: #2563eb;
            --flow-ui-panel-shadow: 0 24px 64px rgba(22, 26, 38, 0.12);
            --flow-ui-glyph-filter: brightness(0) opacity(0.72);
            --flow-ui-glyph-on-accent-filter: brightness(0) invert(1);
            --flow-ui-logo-disc-bg: #0c0c0f;
            --flow-ui-logo-disc-border: rgba(255, 255, 255, 0.16);
            --flow-ui-logo-disc-shadow: 0 1px 0 rgba(255, 255, 255, 0.12) inset, 0 14px 40px rgba(15, 15, 20, 0.28), 0 4px 12px rgba(15, 15, 20, 0.14);
            color: var(--flow-ui-text);
            background: var(--flow-ui-page-background);
        }
        /*
         * Viewport row MUST be minmax(0, 1fr): bare 1fr is minmax(auto, 1fr) and
         * refuses to shrink below content, so ConversationFeed never becomes a
         * scrollport and overflow:hidden ancestors just clip the chat.
         */
        .shell {
            position: relative;
            flex: 1 1 0;
            min-height: 0;
            height: 100%;
            display: grid;
            grid-template-rows: auto minmax(0, 1fr) auto;
        }
        /*
         * Minimal chrome: Share overlays the viewport. Absolute topbar must NOT create
         * a grid track — auto-placement would park <main.viewport> in a 0px first row
         * and overflow:hidden clips the entire conversation (blank SPA chat).
         */
        :host([data-chrome="minimal"]) .shell,
        :host([data-chrome="none"]) .shell {
            grid-template-rows: minmax(0, 1fr);
        }
        :host([data-chrome="minimal"]) .viewport,
        :host([data-chrome="none"]) .viewport {
            grid-row: 1;
            min-height: 0;
            height: 100%;
        }
        :host([editing]),
        :host([editing]) .shell,
        :host([editing]) .viewport,
        :host([data-fit='document']),
        :host([data-fit='document']) .shell,
        :host([data-fit='document']) .viewport {
            height: auto;
            min-height: 0;
            overflow: visible;
            flex: none;
        }
        .topbar {
            min-height: 52px; display: flex; align-items: center; justify-content: space-between; gap: var(--flow-ui-space-3);
            padding: 0 var(--flow-ui-space-4); border-bottom: 1px solid var(--flow-ui-border);
            background: color-mix(in srgb, var(--flow-ui-page-background) 86%, transparent);
            position: sticky; top: 0; z-index: 4; backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
        }
        :host([data-chrome="minimal"]) .topbar,
        :host([data-chrome="none"]) .topbar {
            min-height: 0; justify-content: flex-end; border-bottom: 0; background: transparent; backdrop-filter: none; -webkit-backdrop-filter: none;
            position: absolute; inset: 10px 12px auto auto; padding: 0; pointer-events: none;
            z-index: 5;
        }
        :host([data-chrome="minimal"]) .top-actions,
        :host([data-chrome="none"]) .top-actions { pointer-events: auto; }
        :host([display='drawer']) .topbar {
            cursor: grab;
            touch-action: none;
            pointer-events: auto;
        }
        .brand { display: flex; align-items: center; gap: 10px; min-width: 0; font-weight: 650; font-size: 14px; letter-spacing: -.01em; color: var(--flow-ui-heading); }
        .brand-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .mark {
            width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0;
            display: grid; place-items: center;
            background: var(--flow-ui-logo-disc-bg, #0c0c0f);
            border: 1px solid var(--flow-ui-logo-disc-border, rgba(255, 255, 255, 0.14));
            box-shadow: var(--flow-ui-logo-disc-shadow);
            /* overflow visible: disc shadow must paint outside the mark. */
            overflow: visible;
        }
        .mark img { width: 18px; height: 18px; object-fit: contain; display: block; }
        nav { display: flex; gap: 4px; overflow: auto; padding: 2px; scrollbar-width: none; }
        nav button {
            border: 0; background: transparent; color: var(--flow-ui-muted); padding: 6px 12px; border-radius: var(--flow-ui-radius-full);
            font: inherit; font-size: var(--flow-ui-font-size-sm); font-weight: 550; white-space: nowrap; cursor: pointer; transition: var(--flow-ui-transition);
        }
        nav button:hover { color: var(--flow-ui-text); background: var(--flow-ui-surface-hover); }
        nav button[aria-current="page"] { color: var(--flow-ui-text); background: var(--flow-ui-accent-muted); }
        nav button:focus-visible { outline: none; box-shadow: var(--flow-ui-focus-ring); }
        .top-actions { display: flex; align-items: center; gap: 6px; }
        .readonly-pill { padding: 4px 10px; border: 1px solid var(--flow-ui-border); border-radius: var(--flow-ui-radius-full); color: var(--flow-ui-muted); font-size: 11.5px; font-weight: 550; white-space: nowrap; }
        .viewport {
            min-height: 0;
            overflow: hidden;
            container-type: inline-size;
            display: flex;
            flex-direction: column;
        }
        flow-ui-page { flex: 1 1 0; min-height: 0; }
        .input-required-banner {
            flex: 0 0 auto;
            display: flex;
            align-items: center;
            gap: 10px;
            width: min(100% - 32px, var(--flow-ui-feed-width));
            margin: var(--flow-ui-space-3) auto 0;
            padding: 10px 14px;
            box-sizing: border-box;
            border-radius: var(--flow-ui-radius-md);
            border: 1px solid color-mix(in srgb, var(--flow-ui-info) 35%, var(--flow-ui-border));
            background: color-mix(in srgb, var(--flow-ui-info) 9%, transparent);
            color: var(--flow-ui-text);
            font-size: var(--flow-ui-font-size-sm);
            line-height: 1.45;
        }
        .input-required-banner span { min-width: 0; }
        .hitl-host-composer {
            flex: 0 0 auto;
            width: min(100% - 24px, var(--flow-ui-feed-width));
            box-sizing: border-box;
            display: grid;
            gap: 8px;
            margin: 8px auto 12px;
            padding: 10px 12px 10px 14px;
            border-radius: var(--flow-ui-radius-2xl);
            border: 1px solid var(--flow-ui-border);
            background: var(--flow-ui-composer-bg);
            box-shadow: var(--flow-ui-composer-shadow);
            transition: var(--flow-ui-transition);
        }
        .hitl-host-composer:focus-within { border-color: color-mix(in srgb, var(--flow-ui-accent) 55%, var(--flow-ui-border)); box-shadow: var(--flow-ui-composer-shadow), var(--flow-ui-focus-ring); }
        .hitl-host-composer textarea {
            width: 100%;
            min-height: 44px;
            resize: none;
            box-sizing: border-box;
            border: 0;
            background: transparent;
            color: var(--flow-ui-text);
            padding: 6px 0;
            font: inherit;
            line-height: 1.5;
            outline: none;
        }
        .hitl-host-composer textarea::placeholder { color: var(--flow-ui-muted); }
        .hitl-host-composer-row {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 8px;
        }
        .hitl-host-composer-row input[type='file'] { flex: 1 1 auto; min-width: 0; font-size: var(--flow-ui-font-size-xs); color: var(--flow-ui-muted); }
        .hitl-host-send {
            min-height: 34px;
            padding: 0 16px;
            border: 0;
            border-radius: var(--flow-ui-radius-full);
            background: var(--flow-ui-accent);
            color: var(--flow-ui-on-accent, #fff);
            font: inherit;
            font-size: var(--flow-ui-font-size-sm);
            font-weight: 600;
            cursor: pointer;
            transition: var(--flow-ui-transition);
        }
        .hitl-host-send:not(:disabled):hover { background: var(--flow-ui-accent-hover); }
        .hitl-host-send:focus-visible { outline: none; box-shadow: var(--flow-ui-focus-ring); }
        .hitl-host-send:disabled { opacity: .45; cursor: not-allowed; }
        .statusbar { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 6px var(--flow-ui-space-4); border-top: 1px solid var(--flow-ui-border); color: var(--flow-ui-muted); font-size: 11.5px; }
        .status { display: inline-flex; align-items: center; gap: 7px; }
        .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--flow-ui-success); box-shadow: 0 0 0 3px color-mix(in srgb, var(--flow-ui-success) 20%, transparent); }
        .dot.pending { background: var(--flow-ui-warning); box-shadow: 0 0 0 3px color-mix(in srgb, var(--flow-ui-warning) 20%, transparent); }
        .dot.error { background: var(--flow-ui-danger); box-shadow: 0 0 0 3px color-mix(in srgb, var(--flow-ui-danger) 20%, transparent); }
        /* Скелет ленты: реплика пользователя справа, два абзаца ответа слева. */
        .skeleton { min-height: 320px; width: min(100% - 32px, var(--flow-ui-feed-width)); margin: 0 auto; padding: 28px 0; box-sizing: border-box; display: grid; align-content: start; gap: 14px; }
        .shimmer { height: 44px; border-radius: var(--flow-ui-radius-xl); background: linear-gradient(90deg, var(--flow-ui-surface-hover), color-mix(in srgb, var(--flow-ui-surface-hover) 40%, transparent), var(--flow-ui-surface-hover)); background-size: 220% 100%; animation: shimmer 1.4s infinite linear; }
        .shimmer:nth-child(1) { width: 42%; justify-self: end; }
        .shimmer:nth-child(2) { width: 88%; height: 64px; border-radius: var(--flow-ui-radius-md); }
        .shimmer:nth-child(3) { width: 64%; height: 40px; border-radius: var(--flow-ui-radius-md); }
        @keyframes shimmer { to { background-position: -220% 0; } }
        /*
         * Drawer/panel: never put box-shadow on the same box as overflow:hidden.
         * Chromium/WebKit then paint dark triangular nicks in the rounded corners.
         * Shadow stays on :host; content clips on .shell with matching radius.
         */
        :host([display="panel"]), :host([display="drawer"]) {
            border-radius: var(--flow-ui-radius-2xl);
            overflow: visible;
            box-shadow: var(--flow-ui-panel-shadow);
            background: var(--flow-ui-panel-strong, var(--flow-ui-page-background, var(--bg-surface, #1e2a47)));
        }
        :host([display="inline"]) {
            border-radius: var(--flow-ui-radius-lg);
            overflow: visible;
            background: var(--flow-ui-panel-strong, var(--flow-ui-page-background, var(--bg-surface, #1e2a47)));
        }
        :host([display="panel"]) .shell,
        :host([display="drawer"]) .shell,
        :host([display="inline"]) .shell {
            border-radius: inherit;
            overflow: hidden;
        }
        :host([data-fit='document'][display="panel"]) .shell,
        :host([data-fit='document'][display="drawer"]) .shell,
        :host([data-fit='document'][display="inline"]) .shell {
            overflow: visible;
        }
        /*
         * Editing canvas and interface-editor live test: chrome none/minimal otherwise
         * forces .viewport to height 100% and clips html/form blocks. Grow with the
         * document; the editor .canvas scrolls.
         */
        :host([editing][data-chrome="none"]) .shell,
        :host([editing][data-chrome="minimal"]) .shell,
        :host([editing][data-chrome="none"]) .viewport,
        :host([editing][data-chrome="minimal"]) .viewport,
        :host([data-fit='document'][data-chrome="none"]) .shell,
        :host([data-fit='document'][data-chrome="minimal"]) .shell,
        :host([data-fit='document'][data-chrome="none"]) .viewport,
        :host([data-fit='document'][data-chrome="minimal"]) .viewport {
            height: auto;
            min-height: 0;
            overflow: visible;
            flex: none;
        }
        :host([editing]) flow-ui-page,
        :host([data-fit='document']) flow-ui-page {
            flex: none;
            height: auto;
            min-height: 0;
        }
        @media (prefers-reduced-motion: reduce) { .shimmer { animation: none; } nav button, .hitl-host-composer, .hitl-host-send { transition: none; } }
        @media (max-width: 680px) { nav { order: 3; width: 100%; } .topbar { flex-wrap: wrap; padding-block: 6px; } .readonly-pill { display: none; } }
`;
