/**
 * Shared styles for @var: / @state: / brace decorations and hover tooltips
 * in CodeMirror editors (markdown + variable-input).
 */
import { css } from '../../../assets/js/lit/lit.min.js';

export const variableRefsStyles = css`
    .cm-variable-required {
        color: #a78bfa;
        font-weight: 500;
    }

    .cm-variable-optional {
        color: #22d3ee;
        font-weight: 500;
    }

    .cm-variable-default {
        color: var(--accent);
    }

    /* Same tint as Logic canvas dataflow chip kind=interface */
    .cm-variable-interface {
        color: var(--info);
        font-weight: 500;
    }

    .cm-for-keyword {
        color: #f59e0b;
        font-weight: 600;
    }

    .cm-ref-var {
        color: #f472b6;
        font-weight: 500;
    }

    .cm-ref-state {
        color: #fbbf24;
        font-weight: 500;
    }

    .cm-variable-undefined {
        color: #ef4444;
        text-decoration: wavy underline;
        text-underline-offset: 3px;
    }

    .cm-loop-var {
        color: #a78bfa;
        font-style: italic;
    }

    .cm-tooltip {
        background: var(--glass-solid-strong) !important;
        border: 1px solid var(--border-default) !important;
        border-radius: var(--radius-md) !important;
        box-shadow: var(--glass-shadow-medium) !important;
        padding: var(--space-2) var(--space-3) !important;
        font-family: var(--font-sans) !important;
        font-size: var(--text-sm) !important;
        color: var(--text-primary) !important;
        max-width: 300px !important;
    }

    .variable-tooltip {
        display: flex;
        flex-direction: column;
        gap: var(--space-1);
    }

    .variable-tooltip-name {
        font-weight: var(--font-semibold);
        color: var(--accent);
    }

    .variable-tooltip-value {
        font-family: var(--font-mono);
        font-size: var(--text-xs);
        color: var(--text-secondary);
        word-break: break-all;
    }

    .variable-tooltip-undefined {
        color: var(--error);
        font-style: italic;
    }

    :host-context([data-theme="light"]) .cm-variable-required {
        color: #7c3aed;
    }

    :host-context([data-theme="light"]) .cm-variable-optional {
        color: #0891b2;
    }

    :host-context([data-theme="light"]) .cm-variable-default {
        color: #7c8af4;
    }

    :host-context([data-theme="light"]) .cm-variable-interface {
        color: var(--info);
    }

    :host-context([data-theme="light"]) .cm-for-keyword {
        color: #d97706;
    }

    :host-context([data-theme="light"]) .cm-ref-var {
        color: #db2777;
    }

    :host-context([data-theme="light"]) .cm-ref-state {
        color: #ca8a04;
    }

    :host-context([data-theme="light"]) .cm-variable-undefined {
        color: #dc2626;
    }

    :host-context([data-theme="light"]) .cm-loop-var {
        color: #7c3aed;
    }
`;
