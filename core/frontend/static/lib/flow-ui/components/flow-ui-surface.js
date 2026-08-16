import { LitElement, css, html } from '../../lit-shim.js';
import { ensureFlowUICatalogRegistered } from '../catalog/register-all.js';
import { flowUIComponentRenderer } from '../catalog/registry.js';
import { resolveBound, unknownExternalComponent, wrapFlowNode } from '../catalog/render-helpers.js';
import { conversationUserText } from '../catalog/platform/conversation-turn.js';
import { flowUIText, resolveFlowUILocale } from '../utils/text.js';
import { copyTextToClipboard } from '../../utils/clipboard.js';

ensureFlowUICatalogRegistered();

export class FlowUISurfaceElement extends LitElement {
    static properties = {
        surface: { attribute: false },
        tasks: { attribute: false },
        controller: { attribute: false },
        readonly: { type: Boolean },
        locale: { type: String },
        platformUiOrigin: { type: String },
        selectedComponentId: { attribute: false },
        hitlMode: { type: String, attribute: false },
        uploadState: { state: true },
        feedJump: { state: true },
        copiedTaskId: { state: true },
    };

    static styles = css`
        :host {
            display: flex;
            flex-direction: column;
            width: 100%;
            min-width: 0;
            min-height: 0;
            height: 100%;
            color: var(--flow-ui-text);
        }
        * { box-sizing: border-box; }
        :host > .flow-node {
            width: 100%;
            flex: 1 1 0;
            min-height: 0;
        }
        .flow-node {
            min-width: 0;
            grid-column: var(--flow-ui-column-wide, auto);
            grid-row: var(--flow-ui-row-wide, auto);
            order: var(--flow-ui-order-wide, 0);
            align-self: var(--flow-ui-align-wide, auto);
            justify-self: var(--flow-ui-justify-wide, auto);
            max-height: var(--flow-ui-max-block-wide, none);
            overflow: var(--flow-ui-block-overflow-wide, visible);
            box-sizing: border-box;
        }
        .flow-grid {
            width: 100%;
            grid-template-columns: repeat(var(--flow-ui-cols-wide, 12), minmax(0, 1fr));
        }
        /* Non-component wrappers under a grid container must span all tracks. */
        .flow-grid > :not([data-flow-ui-component]) {
            grid-column: 1 / -1;
            width: 100%;
            min-width: 0;
        }
        @container (max-width: 599px) {
            .flow-grid { grid-template-columns: repeat(var(--flow-ui-cols-compact, 4), minmax(0, 1fr)); }
            .flow-node {
                grid-column: var(--flow-ui-column-compact, auto);
                grid-row: var(--flow-ui-row-compact, auto);
                order: var(--flow-ui-order-compact, 0);
                max-height: var(--flow-ui-max-block-compact, none);
                overflow: var(--flow-ui-block-overflow-compact, visible);
            }
        }
        @container (min-width: 600px) and (max-width: 959px) {
            .flow-grid { grid-template-columns: repeat(var(--flow-ui-cols-medium, 8), minmax(0, 1fr)); }
            .flow-node {
                grid-column: var(--flow-ui-column-medium, auto);
                grid-row: var(--flow-ui-row-medium, auto);
                order: var(--flow-ui-order-medium, 0);
                max-height: var(--flow-ui-max-block-medium, none);
                overflow: var(--flow-ui-block-overflow-medium, visible);
            }
        }
        @container (min-width: 960px) {
            .flow-grid { grid-template-columns: repeat(var(--flow-ui-cols-wide, 12), minmax(0, 1fr)); }
        }

        .page-shell {
            width: 100%;
            height: 100%;
            min-height: 0;
            position: relative;
            box-sizing: border-box;
            background: var(--flow-ui-page-background, var(--bg-primary, #16213e));
        }
        /*
         * Conversation shell geometry contract:
         * the shell never scrolls; ConversationFeed is the only scroll owner and
         * absorbs all free space, so the composer is pinned to the bottom by
         * flex geometry (no sticky/auto-margin hacks). Selectors key off
         * data-flow-ui-type so custom component ids keep the same behavior.
         */
        .page-shell--conversation {
            position: relative;
            display: flex;
            flex-direction: column;
            width: 100%;
            height: 100%;
            max-height: 100%;
            min-height: 0;
            overflow: hidden;
            gap: 0;
            padding: 0;
            background: var(--flow-ui-page-background, var(--bg-primary, #16213e));
        }
        .page-shell--conversation > .flow-node {
            width: 100%;
            min-width: 0;
            flex: 0 0 auto;
        }
        .page-shell--conversation > .flow-node[data-flow-ui-type="Section"] {
            padding: 0 var(--space-4, 16px);
        }
        .page-shell--conversation > .flow-node[data-flow-ui-type="ConversationFeed"] {
            flex: 1 1 0;
            min-height: 0;
            overflow: auto;
            overscroll-behavior: contain;
            /*
             * Bottom bleed must fit --flow-ui-logo-disc-shadow: overflow:auto on this
             * node otherwise hard-clips avatar drop shadows against the composer.
             * Keep inline padding in sync with Form so the 760px columns align.
             */
            padding: var(--space-2, 8px) var(--space-4, 16px) var(--flow-ui-disc-shadow-bleed, 32px);
        }
        .page-shell--conversation.page-shell--conversation-empty > .flow-node[data-flow-ui-type="ConversationFeed"] {
            flex: 0 0 auto;
            overflow: visible;
            padding: 0;
        }
        .page-shell--conversation.page-shell--conversation-empty > .flow-node[data-flow-ui-type="EmptyState"] {
            flex: 1 1 0;
            min-height: 0;
            display: grid;
            place-content: center;
            padding: 0 var(--space-4, 16px);
        }
        /*
         * Empty greeting returns no EmptyState node. Without a flex:1 spacer the
         * composer would sit under Share at the top of a tall blank panel — pin it.
         */
        .page-shell--conversation.page-shell--conversation-empty > .flow-node[data-flow-ui-type="Form"] {
            margin-top: auto;
        }
        .page-shell--conversation > .flow-node[data-flow-ui-type="SuggestedPrompts"] {
            padding: 0 var(--space-4, 16px);
        }
        .page-shell--conversation > .flow-node[data-flow-ui-type="Form"] {
            /* Bottom bleed: composer pill shadow vs page-shell overflow:hidden. */
            padding: var(--space-2, 8px) var(--space-4, 16px) var(--flow-ui-disc-shadow-bleed, 32px);
        }
        /*
         * width:100% is required: ArtifactFeed is a column flex stack, and
         * margin-inline:auto without an explicit width shrink-wraps the feed to
         * content then centers it — short first turns look middle-aligned until
         * later longer bubbles widen the track.
         */
        .page-shell--conversation .task-feed {
            width: 100%;
            max-width: min(100%, 760px);
            margin-inline: auto;
            box-sizing: border-box;
        }
        .page-shell--conversation .task-feed > .task {
            width: 100%;
            min-width: 0;
        }
        .page-shell--conversation .suggestions {
            max-width: min(100%, 760px);
            margin-inline: auto;
            justify-content: center;
        }
        .section, .field-group, .card {
            width: 100%;
            min-width: 0;
            box-sizing: border-box;
        }

        .section, .card, .field-group, .artifact-card, .empty, .alert, .metric {
            border: 1px solid var(--flow-ui-border);
            background: var(--flow-ui-panel);
            border-radius: var(--flow-ui-radius-lg);
            box-shadow: none;
        }
        .section { padding: 18px; }
        .card, .field-group, .artifact-card, .empty, .alert, .metric { padding: 16px; }

        .section--chat-header {
            border: 0;
            background: transparent;
            box-shadow: none;
            padding: var(--space-2, 8px) 0;
            border-radius: 0;
        }
        .field-group--composer {
            border: 1px solid var(--flow-ui-border);
            background: var(--flow-ui-composer-bg);
            border-radius: 28px;
            box-shadow: 0 8px 28px rgba(0, 0, 0, 0.18);
            padding: 0;
            display: grid;
            gap: 0;
            max-width: min(100%, 760px);
            width: 100%;
            margin: 0 auto;
        }
        .empty--greeting {
            border: 0;
            background: transparent;
            box-shadow: none;
            padding: 24px 8px;
            text-align: center;
            color: var(--flow-ui-muted);
        }
        .page-shell--conversation-empty .empty--greeting {
            max-width: 640px;
            font-size: var(--text-xl, 20px);
            font-weight: 650;
            letter-spacing: -.02em;
            color: var(--flow-ui-heading);
        }

        h1, h2, h3, h4 { margin: 0; letter-spacing: -.025em; color: var(--flow-ui-heading); }
        p { margin: 0; line-height: 1.6; }
        .muted { color: var(--flow-ui-muted); }
        .divider { height: 1px; background: var(--flow-ui-border); }
        button, input, textarea, select { font: inherit; }
        button {
            min-height: 42px; border: 1px solid transparent; border-radius: var(--flow-ui-radius-md);
            padding: 9px 15px; cursor: pointer; color: var(--flow-ui-button-text); font-weight: 650;
            background: var(--flow-ui-accent); transition: transform .16s ease, filter .16s ease;
            display: inline-flex; align-items: center; justify-content: center; gap: 8px;
        }
        button:hover { filter: brightness(1.08); transform: translateY(-1px); }
        button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible {
            outline: 3px solid color-mix(in srgb, var(--flow-ui-accent) 45%, transparent); outline-offset: 2px;
        }
        button.secondary { background: transparent; border-color: var(--flow-ui-border); color: inherit; }
        button:disabled { opacity: .48; cursor: not-allowed; transform: none; }
        .button-spinner {
            width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0;
            border: 2px solid color-mix(in srgb, var(--flow-ui-on-accent, #fff) 35%, transparent);
            border-top-color: var(--flow-ui-on-accent, #fff);
            animation: flow-ui-spin .7s linear infinite;
        }
        button.secondary .button-spinner {
            border-color: color-mix(in srgb, currentColor 35%, transparent);
            border-top-color: currentColor;
        }
        label { display: grid; gap: 7px; color: var(--flow-ui-muted); font-size: .84rem; font-weight: 600; }
        .field-label { min-width: 0; line-height: 1.35; }
        .field-required { color: var(--error, #ff8da3); margin-inline-start: 2px; font-weight: 700; }
        .field-error { color: var(--error, #ff8da3); font-size: 11px; font-weight: 500; line-height: 1.35; }
        input, textarea, select {
            width: 100%; border: 1px solid var(--flow-ui-border-strong); border-radius: 13px;
            background: var(--flow-ui-input); color: inherit; padding: 11px 13px;
        }
        textarea { resize: vertical; min-height: 86px; }

        .identity { display: flex; align-items: center; gap: 12px; }
        .avatar {
            width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center;
            background: var(--flow-ui-logo-disc-bg); color: var(--flow-ui-logo-disc-fg);
            border: 1px solid var(--flow-ui-logo-disc-border); box-shadow: var(--flow-ui-logo-disc-shadow);
            /* overflow must stay visible: logo-disc shadow paints outside the disc. */
            overflow: visible; flex-shrink: 0;
        }
        .avatar img { width: 24px; height: 24px; object-fit: contain; display: block; }
        .avatar.bot {
            background: var(--flow-ui-surface-subtle);
            border: 1px solid var(--flow-ui-border);
            box-shadow: none;
            color: var(--flow-ui-muted);
        }

        .task-run-control {
            position: relative;
            width: 36px;
            height: 36px;
            min-height: 36px;
            padding: 0;
            border-radius: 50%;
            display: grid;
            place-items: center;
            border: 1px solid var(--flow-ui-border);
            background: color-mix(in srgb, var(--flow-ui-surface) 82%, transparent);
            color: var(--flow-ui-text);
            box-shadow: none;
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            transition: border-color .15s ease, background .15s ease, transform .15s ease;
        }
        .task-run-control:hover:not(:disabled) {
            border-color: color-mix(in srgb, var(--flow-ui-accent) 45%, var(--flow-ui-border));
            background: color-mix(in srgb, var(--flow-ui-accent-muted) 55%, var(--flow-ui-surface));
            transform: translateY(-1px);
        }
        .task-run-control:disabled {
            opacity: .72;
            cursor: default;
            transform: none;
        }
        .task-run-control__ring {
            position: absolute;
            inset: 5px;
            border-radius: 50%;
            border: 2px solid color-mix(in srgb, var(--flow-ui-accent) 22%, transparent);
            border-top-color: var(--flow-ui-accent);
            animation: flow-ui-spin .75s linear infinite;
        }
        .task-run-control__stop {
            position: relative;
            z-index: 1;
            width: 10px;
            height: 10px;
            border-radius: 2.5px;
            background: var(--flow-ui-heading, var(--flow-ui-text));
        }

        .suggestions { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 0 8px; }
        .suggestions button {
            min-height: 34px; padding: 7px 14px; border-radius: 999px;
            background: var(--flow-ui-surface); border: 1px solid var(--flow-ui-border);
            color: var(--flow-ui-text); font-weight: 550; font-size: 13px;
        }
        .suggestions button:hover { background: var(--flow-ui-accent-muted); }

        .task-feed { display: grid; gap: 14px; padding: 4px 0 12px; }
        .task { display: grid; gap: 9px; }
        .task-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; font-size: .78rem; color: var(--flow-ui-muted); }
        .task-state { padding: 3px 8px; border-radius: 999px; background: color-mix(in srgb, var(--success, #52c495) 12%, transparent); color: var(--success, #79dfb3); }

        .message-row {
            display: flex; gap: 10px; align-items: flex-end; max-width: min(100%, 720px);
        }
        .message-row.user { margin-left: auto; flex-direction: row-reverse; }
        .message-row.assistant { margin-right: auto; }
        .message-row .msg-actions {
            display: inline-flex;
            gap: 2px;
            align-self: center;
            opacity: 0;
            transition: opacity .15s ease;
        }
        .message-row:hover .msg-actions,
        .message-row:focus-within .msg-actions { opacity: 1; }
        .msg-action-btn {
            min-height: 26px;
            width: 26px;
            padding: 0;
            border: 0;
            border-radius: 8px;
            background: transparent;
            color: var(--flow-ui-muted);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transform: none;
            filter: none;
        }
        .msg-action-btn:hover {
            background: var(--flow-ui-surface-hover);
            color: var(--flow-ui-text);
            transform: none;
            filter: none;
        }
        .bubble-files { display: flex; flex-wrap: wrap; gap: 6px; }
        .bubble-files:not(:first-child) { margin-top: 8px; }
        .bubble-file-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            max-width: 100%;
            min-height: 0;
            padding: 4px 10px;
            border-radius: 999px;
            background: var(--flow-ui-surface);
            border: 1px solid var(--flow-ui-border);
            font-size: 12px;
            font-weight: 500;
            line-height: 1.3;
            color: inherit;
            cursor: pointer;
            transform: none;
            filter: none;
        }
        .bubble-file-chip:hover {
            border-color: color-mix(in srgb, var(--flow-ui-accent) 45%, var(--flow-ui-border));
            background: var(--flow-ui-surface-hover, var(--flow-ui-surface));
            transform: none;
            filter: none;
        }
        .bubble-file-chip .bubble-file-name {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 220px;
        }
        .typing-indicator { display: inline-flex; align-items: center; gap: 4px; padding: 3px 0; }
        .typing-indicator .dot-pulse {
            width: 7px; height: 7px; border-radius: 50%;
            background: var(--flow-ui-muted);
            animation: flow-ui-typing 1.2s ease-in-out infinite;
        }
        .typing-indicator .dot-pulse:nth-child(2) { animation-delay: .15s; }
        .typing-indicator .dot-pulse:nth-child(3) { animation-delay: .3s; }
        @keyframes flow-ui-typing {
            0%, 60%, 100% { opacity: .35; transform: translateY(0); }
            30% { opacity: 1; transform: translateY(-3px); }
        }
        .streaming-caret {
            display: inline-block;
            width: 7px;
            height: 1em;
            margin-left: 2px;
            vertical-align: text-bottom;
            border-radius: 2px;
            background: var(--flow-ui-accent);
            animation: flow-ui-caret 1s steps(2, start) infinite;
        }
        @keyframes flow-ui-caret { 50% { opacity: 0; } }
        .scroll-to-bottom-rail {
            position: sticky;
            bottom: 12px;
            display: flex;
            justify-content: flex-end;
            align-items: center;
            width: 100%;
            min-width: 0;
            pointer-events: none;
            z-index: 3;
        }
        button.scroll-to-bottom {
            pointer-events: auto;
            flex: 0 0 36px;
            align-self: flex-end;
            width: 36px;
            max-width: 36px;
            min-width: 36px;
            height: 36px;
            min-height: 36px;
            max-height: 36px;
            margin: 0 4px 0 0;
            padding: 0;
            gap: 0;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid var(--flow-ui-border-strong);
            background: var(--flow-ui-panel-strong, var(--flow-ui-panel));
            color: var(--flow-ui-text);
            box-shadow: var(--flow-ui-panel-shadow);
            transform: none;
        }
        button.scroll-to-bottom:hover {
            filter: brightness(1.08);
            transform: none;
        }
        .composer-spinner {
            width: 16px;
            height: 16px;
            border-radius: 50%;
            border: 2px solid color-mix(in srgb, var(--flow-ui-on-accent, #fff) 35%, transparent);
            border-top-color: var(--flow-ui-on-accent, #fff);
            animation: flow-ui-spin .7s linear infinite;
        }
        @keyframes flow-ui-spin { to { transform: rotate(360deg); } }
        .composer-stop-square {
            width: 12px;
            height: 12px;
            border-radius: 3px;
            background: currentColor;
        }
        @media (prefers-reduced-motion: reduce) {
            .typing-indicator .dot-pulse { animation: none; opacity: .6; }
            .streaming-caret { animation: none; }
            .composer-spinner,
            .button-spinner { animation-duration: 1.6s; }
            .task-run-control__ring { animation-duration: 1.6s; }
            .composer-attach-spinner,
            .file-upload-spinner { animation-duration: 1.6s; }
        }
        .bubble {
            border: 1px solid var(--flow-ui-border);
            background: var(--flow-ui-surface);
            color: var(--flow-ui-text);
            border-radius: var(--flow-ui-radius, 25px);
            padding: 12px 16px;
            max-width: 100%;
            overflow-wrap: anywhere;
            line-height: 1.55;
        }
        .message-row.user .bubble {
            background: var(--flow-ui-accent-muted);
            border-color: transparent;
            border-bottom-right-radius: 8px;
        }
        .message-row.assistant .bubble {
            background: var(--flow-ui-panel-strong, var(--flow-ui-panel));
            border-bottom-left-radius: 8px;
        }
        .bubble .part-text { white-space: pre-wrap; }

        .turn-activity {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 6px;
            margin: 2px 0 2px 40px;
            max-width: min(720px, 100%);
        }
        .turn-activity-chip {
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            padding: 0;
            border-radius: 10px;
            border: 1px solid var(--flow-ui-border);
            background: var(--flow-ui-chip, var(--flow-ui-surface-subtle));
            color: var(--flow-ui-muted);
            box-sizing: border-box;
        }
        .turn-activity-chip .flow-ui-glyph {
            opacity: 0.88;
        }
        .turn-activity-chip[data-kind="skill"] {
            color: var(--flow-ui-text);
            border-color: color-mix(in srgb, var(--flow-ui-accent) 35%, var(--flow-ui-border));
        }
        .turn-activity-chip[data-kind="error"] {
            color: var(--error, #ff8da3);
            border-color: color-mix(in srgb, var(--error, #ff8da3) 40%, var(--flow-ui-border));
            background: color-mix(in srgb, var(--error, #ff8da3) 10%, transparent);
        }
        button.turn-activity-chip {
            appearance: none;
            cursor: default;
            font: inherit;
        }
        .turn-activity-chip.is-interactive {
            cursor: pointer;
            color: var(--flow-ui-accent);
            border-color: color-mix(in srgb, var(--flow-ui-accent) 55%, var(--flow-ui-border));
            background: color-mix(in srgb, var(--flow-ui-accent) 14%, var(--flow-ui-panel, var(--flow-ui-surface-subtle)));
            box-shadow:
                0 0 0 1px color-mix(in srgb, var(--flow-ui-accent) 28%, transparent),
                0 0 12px color-mix(in srgb, var(--flow-ui-accent) 34%, transparent);
            animation: flow-ui-chip-glow 1.8s ease-in-out infinite;
        }
        .turn-activity-chip.is-interactive:hover {
            box-shadow:
                0 0 0 2px color-mix(in srgb, var(--flow-ui-accent) 40%, transparent),
                0 0 18px color-mix(in srgb, var(--flow-ui-accent) 48%, transparent);
        }
        .turn-activity-chip.is-interactive:focus-visible {
            outline: 2px solid var(--flow-ui-accent);
            outline-offset: 2px;
        }
        .turn-activity-pulse {
            position: absolute;
            top: 3px;
            right: 3px;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--flow-ui-accent);
            box-shadow: 0 0 0 2px color-mix(in srgb, var(--flow-ui-accent) 22%, transparent);
            animation: flow-ui-pulse 1.1s ease-in-out infinite;
        }
        @keyframes flow-ui-pulse {
            50% { opacity: 0.45; }
        }
        @keyframes flow-ui-chip-glow {
            0%, 100% {
                box-shadow:
                    0 0 0 1px color-mix(in srgb, var(--flow-ui-accent) 24%, transparent),
                    0 0 10px color-mix(in srgb, var(--flow-ui-accent) 28%, transparent);
            }
            50% {
                box-shadow:
                    0 0 0 2px color-mix(in srgb, var(--flow-ui-accent) 42%, transparent),
                    0 0 16px color-mix(in srgb, var(--flow-ui-accent) 46%, transparent);
            }
        }

        .artifact-card { display: grid; gap: 10px; overflow: hidden; }
        .artifact-title { font-weight: 700; color: var(--flow-ui-heading); }
        .part-text { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.65; }
        pre { margin: 0; overflow: auto; padding: 12px; border-radius: 11px; background: var(--flow-ui-surface-subtle); font: 12px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; }
        .file { display: flex; align-items: center; gap: 10px; padding: 10px; border-radius: 11px; background: var(--flow-ui-surface-subtle); }

        .composer-shell {
            display: grid;
            gap: 8px;
            padding: 10px 10px 10px 12px;
        }
        .composer-row {
            display: grid;
            grid-template-columns: auto minmax(0, 1fr) auto;
            gap: 8px;
            align-items: end;
        }
        .composer-files {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            padding: 0 2px;
        }
        .composer-file-chip {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            max-width: 100%;
            padding: 3px 6px 3px 4px;
            border-radius: 999px;
            background: var(--flow-ui-surface);
            border: 1px solid var(--flow-ui-border);
            font-size: 12px;
            color: var(--flow-ui-text);
            line-height: 1.2;
        }
        .composer-file-open {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            min-height: 0;
            min-width: 0;
            padding: 2px 6px;
            border: 0;
            border-radius: 999px;
            background: transparent;
            color: inherit;
            font: inherit;
            font-weight: 500;
            cursor: pointer;
            transform: none;
            filter: none;
        }
        .composer-file-open:hover {
            color: var(--flow-ui-heading, var(--flow-ui-text));
            transform: none;
            filter: none;
        }
        .composer-file-name {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 180px;
        }
        .composer-file-remove {
            width: 20px;
            height: 20px;
            min-height: 20px;
            padding: 0;
            border: 0;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: transparent;
            color: var(--flow-ui-muted);
            cursor: pointer;
            transform: none;
            filter: none;
        }
        .composer-file-remove:hover:not(:disabled) {
            background: var(--flow-ui-surface-hover);
            color: var(--flow-ui-text);
            transform: none;
            filter: none;
        }
        .composer-body textarea {
            border: 0;
            background: transparent;
            padding: 8px 2px;
            min-height: 24px;
            max-height: 160px;
            resize: none;
            border-radius: 0;
            box-shadow: none;
            line-height: 1.45;
            overflow-y: auto;
        }
        .composer-body textarea:focus {
            outline: none;
        }
        .composer-toolbar-start,
        .composer-toolbar-end {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding-bottom: 2px;
        }
        .composer-attach {
            position: relative;
            display: inline-flex;
            align-items: center;
        }
        .composer-attach input[type='file'],
        .file-upload-input {
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            white-space: nowrap;
            border: 0;
            opacity: 0;
            pointer-events: none;
        }
        .composer-attach-btn {
            color: var(--flow-ui-muted);
        }
        .composer-attach-btn:hover:not(:disabled) {
            color: var(--flow-ui-accent);
        }
        .composer-attach-spinner {
            width: 16px;
            height: 16px;
            border-radius: 50%;
            border: 2px solid color-mix(in srgb, var(--flow-ui-accent) 28%, transparent);
            border-top-color: var(--flow-ui-accent);
            animation: flow-ui-spin .7s linear infinite;
        }

        .file-upload {
            display: grid;
            gap: 10px;
            min-width: 0;
        }
        .file-upload-dropzone {
            position: relative;
            display: grid;
            grid-template-columns: auto minmax(0, 1fr) auto;
            align-items: center;
            gap: 14px;
            width: 100%;
            min-height: 88px;
            padding: 16px 18px;
            border-radius: 18px;
            border: 1px dashed color-mix(in srgb, var(--flow-ui-accent) 35%, var(--flow-ui-border));
            background:
                linear-gradient(
                    145deg,
                    color-mix(in srgb, var(--flow-ui-accent) 10%, transparent),
                    color-mix(in srgb, var(--flow-ui-surface) 88%, transparent)
                );
            color: var(--flow-ui-text);
            text-align: left;
            box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 6%, transparent);
            transform: none;
            filter: none;
            transition:
                border-color .16s ease,
                background .16s ease,
                box-shadow .16s ease,
                transform .16s ease;
        }
        .file-upload-dropzone:hover:not(:disabled),
        .file-upload-dropzone[data-drag='true'] {
            border-style: solid;
            border-color: color-mix(in srgb, var(--flow-ui-accent) 65%, var(--flow-ui-border));
            background:
                linear-gradient(
                    145deg,
                    color-mix(in srgb, var(--flow-ui-accent) 18%, transparent),
                    color-mix(in srgb, var(--flow-ui-surface) 82%, transparent)
                );
            box-shadow:
                0 0 0 3px color-mix(in srgb, var(--flow-ui-accent) 16%, transparent),
                inset 0 1px 0 color-mix(in srgb, #fff 8%, transparent);
            transform: translateY(-1px);
            filter: none;
        }
        .file-upload-dropzone:disabled {
            opacity: .62;
            cursor: not-allowed;
            transform: none;
        }
        .file-upload-icon {
            width: 44px;
            height: 44px;
            border-radius: 14px;
            display: grid;
            place-items: center;
            background: color-mix(in srgb, var(--flow-ui-accent) 16%, var(--flow-ui-surface));
            border: 1px solid color-mix(in srgb, var(--flow-ui-accent) 28%, transparent);
            color: var(--flow-ui-accent);
            flex-shrink: 0;
        }
        .file-upload-copy {
            display: grid;
            gap: 4px;
            min-width: 0;
        }
        .file-upload-title {
            font-size: 14px;
            font-weight: 650;
            color: var(--flow-ui-heading, var(--flow-ui-text));
            letter-spacing: -0.01em;
        }
        .file-upload-hint {
            font-size: 12.5px;
            color: var(--flow-ui-muted);
            line-height: 1.35;
        }
        .file-upload-cta {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 34px;
            padding: 0 14px;
            border-radius: 999px;
            border: 1px solid color-mix(in srgb, var(--flow-ui-accent) 40%, var(--flow-ui-border));
            background: color-mix(in srgb, var(--flow-ui-accent) 14%, transparent);
            color: var(--flow-ui-heading, var(--flow-ui-text));
            font-size: 12.5px;
            font-weight: 600;
            white-space: nowrap;
        }
        .file-upload-spinner {
            width: 18px;
            height: 18px;
            border-radius: 50%;
            border: 2px solid color-mix(in srgb, var(--flow-ui-accent) 28%, transparent);
            border-top-color: var(--flow-ui-accent);
            animation: flow-ui-spin .7s linear infinite;
        }
        .file-upload-list {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .upload-error {
            color: var(--danger, #ff7b72);
            font-size: 12.5px;
        }

        .circle-btn {
            width: 36px;
            height: 36px;
            min-height: 36px;
            padding: 0;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 0;
            background: transparent;
            color: var(--flow-ui-muted);
            cursor: pointer;
            transform: none;
            filter: none;
        }
        .circle-btn:hover:not(:disabled) {
            background: var(--flow-ui-surface-hover);
            color: var(--flow-ui-text);
            transform: none;
            filter: none;
        }
        .circle-btn.send {
            background: var(--flow-ui-accent);
            color: var(--flow-ui-on-accent, #fff);
        }
        .circle-btn.send:hover:not(:disabled) {
            filter: brightness(1.08);
            background: var(--flow-ui-accent);
            color: var(--flow-ui-on-accent, #fff);
        }
        .circle-btn:disabled { opacity: .45; cursor: not-allowed; }
        .field-group--composer platform-voice-dictation {
            display: inline-flex;
            align-items: center;
        }
        .upload-value { display: grid; gap: 6px; margin-top: 7px; font-size: 12px; color: var(--flow-ui-muted); }
        .upload-error { color: var(--error, #ff8da3); font-size: 11px; }

        .badge { display: inline-flex; width: fit-content; padding: 4px 9px; border-radius: 999px; background: var(--flow-ui-accent-muted); color: var(--flow-ui-text); font-size: .75rem; font-weight: 700; }
        .progress { width: 100%; accent-color: var(--flow-ui-accent); }
        .table-wrap { overflow: auto; border: 1px solid var(--flow-ui-border); border-radius: 13px; }
        .table-wrap.table-live {
            display: flex;
            flex-direction: column;
            min-height: 240px;
        }
        .table-wrap.table-live platform-data-table-host {
            flex: 1;
            min-height: 240px;
        }
        .table-wrap.table-empty {
            padding: 16px;
            color: var(--flow-ui-muted);
            font-size: .85rem;
        }
        table { width: 100%; border-collapse: collapse; font-size: .88rem; }
        th, td { padding: 10px 12px; text-align: start; border-bottom: 1px solid var(--flow-ui-border); }
        th { color: var(--flow-ui-muted); font-weight: 650; }
        img, video { display: block; max-width: 100%; border-radius: 14px; }
        .image-empty {
            display: grid;
            place-items: center;
            min-height: 96px;
            padding: 16px;
            border: 1px dashed var(--flow-ui-border-strong);
            border-radius: 14px;
            color: var(--flow-ui-muted);
            font-size: .85rem;
            text-align: center;
            background: color-mix(in srgb, var(--flow-ui-surface, transparent) 70%, transparent);
        }
        .flow-ui-glyph { display: inline-block; vertical-align: middle; flex-shrink: 0; }
        .composer-attach-btn .flow-ui-glyph,
        .composer-file-chip .flow-ui-glyph,
        .composer-file-open .flow-ui-glyph,
        .composer-file-remove .flow-ui-glyph,
        .circle-btn .flow-ui-glyph {
            filter: brightness(0) saturate(100%) invert(88%) opacity(0.92);
        }
        .file-upload-icon .flow-ui-glyph {
            filter: brightness(0) saturate(100%) invert(72%) sepia(42%) saturate(1200%) hue-rotate(190deg) brightness(1.05);
            opacity: 1;
        }
        .unknown { border: 1px dashed var(--flow-ui-border-strong); border-radius: 13px; padding: 13px; color: var(--flow-ui-muted); }
        .unknown[role="alert"] { border-color: color-mix(in srgb, var(--error, #ff718d) 45%, var(--flow-ui-border-strong)); color: var(--error, #ff8da3); }
        [data-selected="true"] { outline: 2px solid var(--flow-ui-accent); outline-offset: 2px; }
        @media (prefers-reduced-motion: reduce) { button { transition: none; } }
    `;

    constructor() {
        super();
        this.surface = null;
        this.tasks = [];
        this.controller = null;
        this.readonly = false;
        this.locale = 'en';
        this.platformUiOrigin = '';
        this.selectedComponentId = null;
        this.hitlMode = null;
        this.uploadState = {};
        this.feedJump = false;
        this.copiedTaskId = null;
        this._feedScrollEl = null;
        this._feedStick = true;
        this._copiedTimer = null;
        this._onFeedScroll = () => {
            const feed = this._feedScrollEl;
            if (!feed) return;
            const nearBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 48;
            this._feedStick = nearBottom;
            if (this.feedJump === nearBottom) this.feedJump = !nearBottom;
        };
    }

    disconnectedCallback() {
        this._feedScrollEl?.removeEventListener('scroll', this._onFeedScroll);
        this._feedScrollEl = null;
        clearTimeout(this._copiedTimer);
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated(changed);
        const feed = this.renderRoot.querySelector('.flow-node[data-flow-ui-type="ConversationFeed"]');
        if (this._feedScrollEl !== feed) {
            this._feedScrollEl?.removeEventListener('scroll', this._onFeedScroll);
            feed?.addEventListener('scroll', this._onFeedScroll, { passive: true });
            this._feedScrollEl = feed;
        }
        // Smart autoscroll: stick to bottom while the user has not scrolled away.
        if (feed && this._feedStick) feed.scrollTop = feed.scrollHeight;
    }

    _scrollFeedToBottom() {
        const feed = this._feedScrollEl;
        if (!feed) return;
        feed.scrollTop = feed.scrollHeight;
        this._feedStick = true;
        this.feedJump = false;
    }

    async _copyTurnText(taskId, text) {
        if (typeof text !== 'string' || text.length === 0) return;
        try {
            // Clipboard API отсутствует вне secure context — copyTextToClipboard даёт execCommand fallback.
            await copyTextToClipboard(text);
        } catch (error) {
            // Clipboard permission / insecure origin — browser boundary, not a UI bug.
            if (!(error instanceof Error)) throw error;
            return;
        }
        this.copiedTaskId = taskId;
        clearTimeout(this._copiedTimer);
        this._copiedTimer = setTimeout(() => { this.copiedTaskId = null; }, 1600);
    }

    _openBrowserPreview(action) {
        if (!action || typeof action !== 'object' || action.kind !== 'browser_preview') {
            throw new Error('flow-ui: _openBrowserPreview requires browser_preview action');
        }
        const viewerUrl = typeof action.viewerUrl === 'string' ? action.viewerUrl.trim() : '';
        if (viewerUrl === '') {
            throw new Error('flow-ui: browser preview viewerUrl required');
        }
        const event = new CustomEvent('browser-preview-open', {
            bubbles: true,
            composed: true,
            cancelable: true,
            detail: {
                viewerUrl,
                sessionId: typeof action.sessionId === 'string' ? action.sessionId : '',
                currentUrl: typeof action.currentUrl === 'string' ? action.currentUrl : '',
                status: typeof action.status === 'string' ? action.status : '',
            },
        });
        this.dispatchEvent(event);
        if (event.defaultPrevented) return;
        window.open(viewerUrl, '_blank', 'noopener,noreferrer');
    }

    _retryTurn(task) {
        if (this.readonly) return;
        const text = conversationUserText(task);
        if (text === '') return;
        const components = Object.values(this.surface?.components || {});
        const submit = components.find((candidate) => (
            candidate?.actions?.press?.kind === 'event'
            && candidate.actions.press.name === 'platform.ui.submit'
        ));
        const textArea = components.find((candidate) => (
            candidate?.type === 'TextArea' && candidate.bindings?.value
        ));
        if (!submit || !textArea) return;
        this.controller?.setValue(this.surface.surface_id, textArea.bindings.value, text);
        void this._submit(submit, submit.actions.press.context || {});
    }

    _change(component, bindingName, value) {
        const path = component.bindings?.[bindingName];
        if (!path || this.readonly) return;
        if (this.controller) {
            this.controller.locale = resolveFlowUILocale(this.locale);
        }
        this.controller?.setValue(this.surface.surface_id, path, value);
    }

    _focusFieldError(componentId) {
        if (typeof componentId !== 'string' || componentId === '') return;
        const root = this.renderRoot?.querySelector(`[data-flow-ui-component="${CSS.escape(componentId)}"]`);
        if (!(root instanceof HTMLElement)) return;
        const control = root.querySelector('input, textarea, select, button.file-upload-dropzone');
        if (control instanceof HTMLElement) control.focus();
    }

    async _submit(component, actionContext = {}) {
        if (this.controller?.activeContext?.submitting === true) return;
        if (this.controller) {
            this.controller.locale = resolveFlowUILocale(this.locale);
        }
        try {
            const result = await this.controller?.submit(
                this.surface.surface_id,
                component.component_id,
                actionContext,
            );
            if (result?.blocked === true) {
                const firstId = result.fieldErrors
                    ? Object.keys(result.fieldErrors)[0]
                    : undefined;
                if (typeof firstId === 'string') this._focusFieldError(firstId);
            }
            return result;
        } catch (error) {
            if (error && typeof error === 'object' && error.name === 'AbortError') return;
            throw error;
        }
    }

    _action(component, slot, context = {}) {
        const action = component.actions?.[slot] || component.actions?.press;
        if (!action || this.readonly) return;
        if (action.kind === 'event' && action.name === 'platform.ui.submit') {
            if (this.controller?.activeContext?.submitting === true) return;
            void this._submit(component, action.context || {});
        } else if (action.kind === 'local' && action.name === 'values.set') {
            const path = component.bindings?.value;
            if (path) this.controller?.setValue(this.surface.surface_id, path, context.value);
        } else if (action.kind === 'local' && action.name === 'page.navigate') {
            const pageId = context.pageId || action.context?.pageId;
            if (pageId) this.controller?.navigate(pageId);
        }
    }

    _removeUploadedFile(component, fileId) {
        if (this.readonly) return;
        if (typeof fileId !== 'string' || fileId.trim() === '') {
            throw new Error('flow-ui: remove file requires file_id');
        }
        const path = component.bindings?.value;
        if (!path) {
            throw new Error(`flow-ui: FileUpload ${component.component_id} missing value binding`);
        }
        const current = resolveBound(this.surface, component, 'value', this.tasks);
        if (!Array.isArray(current)) {
            throw new Error(`flow-ui: FileUpload ${component.component_id} value must be an array`);
        }
        this.controller?.setValue(
            this.surface.surface_id,
            path,
            current.filter((ref) => ref?.file_id !== fileId),
        );
    }

    async _upload(component, eventOrFiles) {
        const files = Array.isArray(eventOrFiles)
            ? eventOrFiles.filter((item) => item instanceof File)
            : Array.from(eventOrFiles?.target?.files || []);
        const path = component.bindings?.value;
        if (!files.length || !path || this.readonly) return;
        const multiple = component.properties?.multiple !== false;
        this.uploadState = {
            ...this.uploadState,
            [component.component_id]: { busy: true, error: '' },
        };
        try {
            await this.controller?.uploadFiles(
                this.surface.surface_id,
                component.component_id,
                path,
                files,
                { append: multiple },
            );
            this.uploadState = {
                ...this.uploadState,
                [component.component_id]: { busy: false, error: '' },
            };
        } catch (error) {
            this.uploadState = {
                ...this.uploadState,
                [component.component_id]: {
                    busy: false,
                    error: error instanceof Error ? error.message : String(error),
                },
            };
        } finally {
            if (eventOrFiles && typeof eventOrFiles === 'object' && eventOrFiles.target) {
                eventOrFiles.target.value = '';
            }
        }
    }

    _children(component) {
        return (component.children || []).map((id) => this._component(this.surface.components[id])).filter(Boolean);
    }

    _component(component) {
        if (!component) return null;
        try {
            const renderer = flowUIComponentRenderer(component.type);
            if (renderer) return renderer(this, component);
            return unknownExternalComponent(this, component);
        } catch (error) {
            const detail = error instanceof Error ? error.message : String(error);
            return wrapFlowNode(
                this,
                component,
                html`<div class="unknown" role="alert">
                    <strong>${component.type}</strong>
                    <div>${flowUIText(this.locale, 'component_render_failed')}</div>
                    <div>${detail}</div>
                </div>`,
            );
        }
    }

    render() {
        const root = this.surface?.components?.[this.surface?.root_component_id || 'root'];
        return root
            ? this._component(root)
            : html`<div class="unknown">${flowUIText(this.locale, 'surface_no_root')}</div>`;
    }
}

if (!customElements.get('flow-ui-surface')) customElements.define('flow-ui-surface', FlowUISurfaceElement);
