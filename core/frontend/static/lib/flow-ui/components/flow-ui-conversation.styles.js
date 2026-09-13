/**
 * Лента и композер блока ``conversation``. Колонка чтения по центру; ответ без коробки,
 * реплика пользователя — нейтральный пузырь справа. Токены ``--flow-ui-*`` только.
 */

import { css } from '../../lit-shim.js';

export const conversationStyles = css`
    :host { display: flex; flex-direction: column; min-height: 0; height: 100%; }
    :host([editing]) { height: auto; min-height: 280px; }
    .task-feed {
        flex: 1 1 0; min-height: 0; overflow: auto; scroll-behavior: smooth;
        display: flex; flex-direction: column; gap: 22px;
        padding: 20px max(16px, calc((100% - var(--flow-ui-feed-width, 760px)) / 2)) 12px;
        scrollbar-gutter: stable;
    }
    :host([editing]) .task-feed {
        flex: 1 1 auto; min-height: 160px; overflow: visible; scrollbar-gutter: auto;
    }
    .greeting {
        display: grid; justify-items: center; text-align: center; gap: 14px;
        margin: auto 0; padding: 28px 12px 36px; color: var(--flow-ui-text);
    }
    :host([editing]) .greeting { margin: 12px 0 20px; }
    .greeting-mark {
        width: var(--flow-ui-hero-mark, 64px); height: var(--flow-ui-hero-mark, 64px);
        border-radius: 50%; object-fit: contain; display: block;
        background: var(--flow-ui-logo-disc-bg, #0c0c0f);
        border: 1px solid var(--flow-ui-logo-disc-border, rgba(255, 255, 255, 0.14));
        box-shadow: var(--flow-ui-logo-disc-shadow);
        padding: 10px; box-sizing: border-box;
    }
    .greeting-title {
        margin: 0; font-size: var(--flow-ui-font-size-hero, 22px); font-weight: 650;
        letter-spacing: -.02em; line-height: var(--flow-ui-line-height-tight, 1.3);
        color: var(--flow-ui-heading);
    }
    .greeting p {
        margin: 0; max-width: 36em; font-size: var(--flow-ui-font-size-body, 15px);
        line-height: var(--flow-ui-line-height, 1.6); color: var(--flow-ui-text-secondary);
    }
    .task { display: flex; flex-direction: column; gap: 10px; width: 100%; }
    .bubble { max-width: min(78%, 620px); padding: 10px 16px; line-height: var(--flow-ui-line-height, 1.6); overflow-wrap: anywhere; }
    .bubble.user {
        align-self: flex-end; white-space: pre-wrap;
        background: var(--flow-ui-user-bubble); color: var(--flow-ui-user-bubble-text);
        border-radius: 20px 20px 6px 20px;
    }
    .bubble.assistant {
        align-self: stretch; max-width: 100%; padding: 2px 0 0;
        background: transparent; border: 0; color: var(--flow-ui-text);
        border-radius: 0;
    }
    .bubble.operator {
        align-self: flex-start; max-width: min(78%, 620px);
        padding: 10px 16px; border-radius: 20px 20px 20px 6px;
        background: var(--flow-ui-card); color: var(--flow-ui-text);
        border: 1px solid color-mix(in srgb, var(--flow-ui-accent) 35%, var(--flow-ui-border));
    }
    .bubble.error {
        align-self: flex-start; max-width: min(78%, 620px);
        padding: 10px 14px; border-radius: var(--flow-ui-radius-lg, 16px);
        background: color-mix(in srgb, var(--flow-ui-danger) 10%, transparent);
        color: var(--flow-ui-danger);
        border: 1px solid color-mix(in srgb, var(--flow-ui-danger) 32%, transparent);
    }
    .interrupt-card {
        align-self: flex-start; max-width: min(78%, 620px);
        display: grid; gap: 10px; padding: 14px 16px;
        border-radius: var(--flow-ui-radius-lg, 16px);
        border: 1px solid color-mix(in srgb, var(--flow-ui-accent) 35%, var(--flow-ui-border));
        background: var(--flow-ui-interrupt-bg);
        color: var(--flow-ui-text); font-size: var(--flow-ui-font-size-body, 15px);
        line-height: var(--flow-ui-line-height, 1.6);
    }
    .author { font-size: var(--flow-ui-font-size-xs, 12px); font-weight: 600; color: var(--flow-ui-muted); margin-bottom: 6px; }
    .assistant-response { color: inherit; }
    .streaming::after {
        content: ''; display: inline-block; width: 2px; height: 1em; margin-left: 2px;
        vertical-align: text-bottom; background: currentColor; border-radius: 1px;
        animation: fu-blink 1s steps(2) infinite;
    }
    @keyframes fu-blink { to { opacity: 0; } }
    .cards { display: grid; gap: 12px; max-width: min(100%, 720px); }
    .files { display: flex; flex-wrap: wrap; gap: 6px; }
    .files.user { align-self: flex-end; justify-content: flex-end; }
    .composer-file-chip {
        display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px;
        border-radius: var(--flow-ui-radius-full, 9999px); font-size: var(--flow-ui-font-size-xs, 12px);
        background: var(--flow-ui-card); color: var(--flow-ui-text); border: 1px solid var(--flow-ui-border);
    }
    .composer-file-chip button {
        border: 0; background: transparent; color: inherit; cursor: pointer; padding: 0;
        display: inline-grid; place-items: center;
    }
    details.reasoning {
        align-self: flex-start; max-width: min(78%, 620px);
        font-size: var(--flow-ui-font-size-sm, 13px); color: var(--flow-ui-muted);
    }
    details.reasoning summary {
        cursor: pointer; list-style: none; display: inline-flex; align-items: center; gap: 6px;
        padding: 4px 10px; border-radius: var(--flow-ui-radius-full, 9999px);
        background: var(--flow-ui-card); border: 1px solid var(--flow-ui-border);
        color: var(--flow-ui-text-secondary); font-weight: 550;
    }
    details.reasoning summary::-webkit-details-marker { display: none; }
    details.reasoning[open] summary { margin-bottom: 8px; }
    details.reasoning pre {
        white-space: pre-wrap; margin: 0; font: inherit; line-height: 1.5;
        padding: 10px 12px; border-radius: var(--flow-ui-radius-md, 12px);
        background: var(--flow-ui-code-bg); color: var(--flow-ui-text-secondary);
    }
    .bubble-observability-actions {
        display: flex; align-items: center; flex-wrap: wrap; gap: 2px;
        margin-top: 4px; margin-left: -6px;
        opacity: 1; transition: opacity 160ms ease;
    }
    @media (hover: hover) and (pointer: fine) {
        .bubble.assistant .bubble-observability-actions { opacity: 0; }
        .bubble.assistant:hover .bubble-observability-actions,
        .bubble.assistant:focus-within .bubble-observability-actions { opacity: 1; }
    }
    .msg-action {
        width: 32px; height: 32px; padding: 0; margin: 0; border: 0; flex: none;
        border-radius: 8px; background: transparent; color: var(--flow-ui-muted);
        display: inline-grid; place-items: center; cursor: pointer;
        transition: background-color 120ms ease, color 120ms ease;
    }
    .msg-action:hover {
        color: var(--flow-ui-text); background: color-mix(in srgb, var(--flow-ui-text) 8%, transparent);
    }
    .msg-action:active {
        background: color-mix(in srgb, var(--flow-ui-text) 12%, transparent);
    }
    .msg-action:focus-visible { outline: none; box-shadow: var(--flow-ui-focus-ring); }
    .msg-action .fu-glyph { display: block; }
    .copy-btn[data-copied] { color: var(--flow-ui-success); }
    .typing {
        align-self: flex-start; display: inline-flex; align-items: center; gap: 5px;
        padding: 8px 14px; border-radius: var(--flow-ui-radius-full, 9999px);
        background: var(--flow-ui-card); border: 1px solid var(--flow-ui-border);
    }
    .typing i {
        width: 5px; height: 5px; border-radius: 50%; background: var(--flow-ui-muted);
        animation: fu-pulse 1.2s ease-in-out infinite;
    }
    .typing i:nth-child(2) { animation-delay: .2s; } .typing i:nth-child(3) { animation-delay: .4s; }
    @keyframes fu-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .28; } }
    .composer {
        flex: 0 0 auto; width: min(100% - 24px, var(--flow-ui-feed-width, 760px));
        box-sizing: border-box; margin: 4px auto 16px; padding: 10px 12px 10px 16px;
        display: flex; flex-direction: column; gap: 6px;
        border-radius: var(--flow-ui-radius-2xl, 24px);
        border: 1px solid var(--flow-ui-border);
        background: var(--flow-ui-composer-bg);
        box-shadow: var(--flow-ui-composer-shadow);
        transition: var(--flow-ui-transition);
    }
    .composer:focus-within {
        border-color: color-mix(in srgb, var(--flow-ui-accent) 50%, var(--flow-ui-border));
        box-shadow: var(--flow-ui-composer-shadow), var(--flow-ui-focus-ring);
    }
    .composer textarea {
        width: 100%; min-height: 24px; max-height: 200px; resize: none; border: 0;
        background: transparent; color: var(--flow-ui-text); font: inherit;
        line-height: 1.5; outline: none; padding: 4px 0 2px; box-sizing: border-box;
    }
    .composer textarea::placeholder { color: var(--flow-ui-muted); }
    .composer .files { width: 100%; }
    .composer .actions { display: flex; align-items: center; gap: 2px; }
    .composer .actions .spacer { flex: 1 1 auto; min-width: 8px; }
    .icon-btn {
        width: 34px; height: 34px; border-radius: 50%; border: 0; flex: none;
        display: inline-grid; place-items: center; cursor: pointer;
        background: transparent; color: var(--flow-ui-text); transition: var(--flow-ui-transition);
    }
    .icon-btn:hover:not(:disabled) { background: var(--flow-ui-surface-hover); }
    .icon-btn:focus-visible { outline: none; box-shadow: var(--flow-ui-focus-ring); }
    .icon-btn:disabled { opacity: .4; cursor: default; }
    .icon-btn .fu-glyph { filter: var(--flow-ui-glyph-filter); }
    .icon-btn.send { background: var(--flow-ui-accent); color: var(--flow-ui-on-accent); }
    .icon-btn.send:not(:disabled):hover { background: var(--flow-ui-accent-hover); }
    .icon-btn.send:disabled { opacity: .45; }
    .icon-btn.send .fu-glyph { filter: var(--flow-ui-glyph-on-accent-filter); }
    .icon-btn.stop { background: var(--flow-ui-text); color: var(--flow-ui-page-background); }
    .icon-btn.stop .fu-glyph { filter: var(--flow-ui-glyph-on-accent-filter); }
    .icon-btn[aria-pressed='true'] { background: var(--flow-ui-accent-muted); color: var(--flow-ui-accent); }
    @media (prefers-reduced-motion: reduce) {
        .task-feed { scroll-behavior: auto; }
        .streaming::after, .typing i { animation: none; }
        .composer, .icon-btn, .msg-action, .bubble-observability-actions { transition: none; }
    }
`;
