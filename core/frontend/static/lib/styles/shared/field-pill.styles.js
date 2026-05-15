/**
 * Field pill — единый канон плашки поля и «голых» контролов внутри неё.
 * Токены: --field-pill-* в core/frontend/static/assets/css/tokens.css
 */
import { css } from '../../../assets/js/lit/lit.min.js';

export const fieldPillStyles = css`
    .field-pill,
    .form-group {
        display: flex;
        flex-direction: column;
        gap: var(--field-pill-gap);
        padding: var(--field-pill-padding-y) var(--field-pill-padding-x);
        border-radius: var(--field-pill-radius);
        box-sizing: border-box;
        background: var(--field-pill-bg);
        border: 1px solid var(--field-pill-border);
        min-width: 0;
    }

    .form-group {
        margin-bottom: var(--space-6);
    }

    .form-group:last-child {
        margin-bottom: 0;
    }

    /* Уже внутри .form-group или иной карточки — одна видимая плашка, не две. */
    .field-pill.field-pill--embed {
        background: transparent;
        border: none;
        padding: 0;
        box-shadow: none;
    }

    .field-pill--textarea {
        gap: var(--field-pill-gap-textarea);
    }

    .field-pill--tags {
        gap: var(--field-pill-gap-tags);
    }

    .field-pill--compact {
        --field-pill-padding-y: var(--field-pill-compact-padding-y);
        --field-pill-padding-x: var(--field-pill-compact-padding-x);
        --field-pill-radius: var(--field-pill-compact-radius);
        --field-pill-gap: var(--field-pill-compact-gap);
        --field-pill-input-size: var(--field-pill-compact-input-size);
        --field-pill-input-weight: var(--field-pill-compact-input-weight);
        --field-pill-number-spin-width: 26px;
        --field-pill-number-spin-height: 34px;
    }

    .field-pill--compact .field-pill-select,
    .field-pill--compact .form-select {
        padding-right: var(--field-pill-compact-select-chevron-padding-end);
        background-position: right var(--space-1) center;
    }

    .field-pill.field-pill--compact.field-pill--dense {
        --field-pill-padding-y: var(--field-pill-dense-padding-y);
        --field-pill-padding-x: var(--field-pill-dense-padding-x);
        --field-pill-gap: 2px;
        --field-pill-number-spin-width: 24px;
        --field-pill-number-spin-height: var(--field-pill-dense-spin-height);
    }

    .field-pill--tags .tags-row {
        min-height: var(--field-pill-number-spin-height);
        box-sizing: border-box;
    }

    .field-pill--tags .tag-input {
        flex: 1;
        min-width: var(--field-pill-tag-input-min-width);
        margin: 0;
        padding: 2px 0;
        border: none;
        border-radius: 0;
        background: transparent;
        box-shadow: none;
        font-family: inherit;
        font-size: var(--field-pill-input-size);
        font-weight: var(--field-pill-input-weight);
        color: var(--field-pill-input-color);
    }

    .field-pill--tags .tag-input:focus {
        outline: none;
    }

    .field-pill--tags .tag-input::placeholder {
        color: var(--field-pill-muted-color);
        font-weight: var(--font-normal);
    }

    .field-pill--tags .tag-chip {
        border: none;
        background: var(--field-pill-tag-chip-bg);
    }

    .field-pill-tags-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: var(--space-2);
    }

    .field-pill-label,
    .form-label,
    .form-group > label {
        display: block;
        font-size: var(--field-pill-label-size);
        line-height: var(--field-pill-label-line, 1.1);
        font-weight: var(--field-pill-label-weight);
        text-transform: uppercase;
        letter-spacing: var(--field-pill-label-letter);
        color: var(--field-pill-label-color);
    }

    .field-pill-head {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        min-width: 0;
    }

    .field-pill-head .field-pill-label {
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .field-pill-head platform-help-hint {
        flex-shrink: 0;
    }

    .field-pill-control {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        min-width: 0;
        width: 100%;
        box-sizing: border-box;
        overflow: visible;
    }

    /* Однострочные edit-контролы (enum, string, number+spin и т.д.) — одна высота; токен — --field-pill-number-spin-height. */
    .field-pill[data-mode='edit'] > .field-pill-control {
        min-height: var(--field-pill-number-spin-height);
    }

    .field-pill-control-main {
        flex: 1;
        min-width: 0;
        display: block;
    }

    slot[name='prefix']::slotted(*),
    slot[name='suffix']::slotted(*) {
        flex-shrink: 0;
    }

    .form-group small {
        display: block;
        margin-top: var(--space-1);
        font-size: var(--field-pill-hint-size);
        font-weight: var(--font-normal);
        color: var(--field-pill-hint-color);
        text-transform: none;
        letter-spacing: normal;
        line-height: var(--leading-normal);
    }

    .field-pill-input,
    .field-pill-textarea,
    .field-pill-select,
    .form-input,
    .form-textarea,
    .form-select {
        width: 100%;
        border: none;
        background: transparent;
        box-shadow: none;
        backdrop-filter: none;
        -webkit-backdrop-filter: none;
        outline: none;
        font-family: inherit;
        font-size: var(--field-pill-input-size);
        font-weight: var(--field-pill-input-weight);
        line-height: var(--field-pill-input-line);
        color: var(--field-pill-input-color);
        padding: 0;
        margin: 0;
        border-radius: 0;
        box-sizing: border-box;
    }

    .field-pill-input::placeholder,
    .field-pill-textarea::placeholder,
    .form-input::placeholder,
    .form-textarea::placeholder {
        color: var(--text-disabled);
    }

    .field-pill-textarea,
    .form-textarea {
        resize: vertical;
        min-height: var(--field-pill-textarea-min-height);
        line-height: var(--leading-normal);
        font-weight: var(--font-normal);
    }

    .field-pill-select,
    .form-select {
        appearance: none;
        cursor: pointer;
        padding-right: 28px;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2371717a' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
        background-repeat: no-repeat;
        background-position: right var(--space-2) center;
    }

    .field-pill-readonly-text {
        font-size: var(--field-pill-input-size);
        font-weight: var(--field-pill-input-weight);
        color: var(--field-pill-input-color);
        line-height: var(--field-pill-input-line);
        white-space: pre-wrap;
        word-break: break-word;
        margin: 0;
    }

    .field-pill-readonly-muted {
        font-size: var(--field-pill-readonly-muted-size);
        font-weight: var(--font-normal);
        color: var(--field-pill-muted-color);
        margin: 0;
    }

    .field-pill-readonly-inline {
        display: flex;
        align-items: center;
        min-height: 24px;
    }

    .tag-count-badge {
        flex-shrink: 0;
        min-width: 22px;
        height: 22px;
        padding: 0 6px;
        border-radius: 11px;
        background: var(--field-pill-tag-count-bg);
        color: var(--field-pill-tag-count-color);
        font-size: var(--field-pill-tag-count-size);
        font-weight: var(--font-bold);
        display: inline-flex;
        align-items: center;
        justify-content: center;
    }

    .attr-row {
        display: grid;
        gap: var(--field-attr-row-gap);
        min-width: 0;
    }

    .attr-hint {
        color: var(--field-pill-hint-color);
        font-size: var(--field-pill-hint-size);
    }

    .field-pill-empty {
        font-size: var(--field-pill-readonly-muted-size);
        font-weight: var(--font-normal);
        color: var(--text-disabled);
        font-style: italic;
        margin: 0;
    }

    .field-pill-file-refs-body {
        display: flex;
        flex-direction: column;
        gap: var(--space-1);
        min-width: 0;
        width: 100%;
    }

    .field-pill-file-ref-row {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        padding: var(--space-1) var(--space-2);
        min-height: 36px;
        box-sizing: border-box;
        background: var(--glass-solid-medium);
        border: 1px solid var(--glass-border-subtle);
        border-radius: var(--radius-full);
        min-width: 0;
    }

    .field-pill-file-ref-icon {
        flex-shrink: 0;
        line-height: 0;
    }

    .field-pill-file-ref-info {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: row;
        align-items: center;
        gap: var(--space-1);
        overflow: hidden;
    }

    .field-pill-file-ref-line {
        display: flex;
        align-items: baseline;
        min-width: 0;
        flex: 1;
        overflow: hidden;
        font-size: var(--text-sm);
        line-height: var(--leading-tight);
    }

    .field-pill-file-ref-name {
        flex: 1;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-weight: var(--font-medium);
        color: var(--text-primary);
    }

    .field-pill-file-ref-sep {
        flex-shrink: 0;
        color: var(--text-tertiary);
        font-weight: var(--font-normal);
        user-select: none;
    }

    .field-pill-file-ref-meta {
        flex-shrink: 0;
        font-size: var(--text-xs);
        color: var(--text-tertiary);
        font-weight: var(--font-normal);
        white-space: nowrap;
    }

    .field-pill-file-ref-remove {
        appearance: none;
        -webkit-appearance: none;
        margin: 0;
        background: transparent;
        border: none;
        padding: 6px;
        cursor: pointer;
        color: var(--text-tertiary);
        border-radius: var(--radius-full);
        flex-shrink: 0;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        line-height: 0;
        opacity: 0.75;
        transition:
            color var(--duration-fast) var(--easing-default),
            opacity var(--duration-fast) var(--easing-default),
            background var(--duration-fast) var(--easing-default);
    }

    .field-pill-file-ref-remove:hover {
        opacity: 1;
        color: var(--error);
        background: var(--error-bg);
    }

    .field-pill-file-ref-remove:focus-visible {
        outline: 2px solid var(--accent);
        outline-offset: 1px;
    }

    .field-pill-file-refs-attach {
        display: flex;
        align-items: center;
        gap: var(--space-2);
    }

    .field-pill-file-refs-attach-btn {
        width: 36px;
        height: 36px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: var(--glass-solid-medium);
        border: 1px dashed var(--glass-border-medium);
        border-radius: var(--radius-md);
        color: var(--text-tertiary);
        cursor: pointer;
    }

    .field-pill-file-refs-attach-btn:hover {
        color: var(--accent);
        border-color: var(--accent);
    }

    .form-input:disabled,
    .form-select:disabled,
    .form-textarea:disabled,
    .field-pill-input:disabled,
    .field-pill-textarea:disabled,
    .field-pill-select:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .form-input.readonly {
        color: var(--text-secondary);
        cursor: default;
    }

    .field-pill-input:focus,
    .field-pill-textarea:focus,
    .field-pill-select:focus,
    .form-input:focus,
    .form-select:focus,
    .form-textarea:focus {
        outline: none;
    }

    .field-pill-number {
        display: flex;
        align-items: center;
        gap: var(--field-pill-number-gap);
        width: 100%;
        min-width: 0;
        min-height: var(--field-pill-number-spin-height);
        box-sizing: border-box;
    }

    .field-pill-number-input {
        flex: 1;
        min-width: 0;
    }

    .field-pill-number-input::-webkit-outer-spin-button,
    .field-pill-number-input::-webkit-inner-spin-button {
        -webkit-appearance: none;
        margin: 0;
        appearance: none;
    }

    .field-pill-number-input[type='number'] {
        -moz-appearance: textfield;
        appearance: textfield;
    }

    .field-pill-number-spin {
        display: flex;
        flex-direction: column;
        flex-shrink: 0;
        width: var(--field-pill-number-spin-width);
        height: var(--field-pill-number-spin-height);
        border-radius: var(--field-pill-number-spin-radius);
        overflow: hidden;
        border: 1px solid var(--field-pill-number-spin-border);
        background: var(--field-pill-number-spin-bg);
        box-sizing: border-box;
    }

    .field-pill-number-spin-btn {
        appearance: none;
        -webkit-appearance: none;
        flex: 1 1 50%;
        min-height: 0;
        margin: 0;
        padding: 0;
        border: none;
        border-radius: 0;
        background: transparent;
        box-shadow: none;
        color: var(--field-pill-number-spin-icon-color);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        line-height: 0;
        transition:
            background var(--duration-fast) var(--easing-default),
            color var(--duration-fast) var(--easing-default);
    }

    .field-pill-number-spin-btn:first-of-type {
        border-bottom: 1px solid var(--field-pill-number-spin-divider);
    }

    .field-pill-number-spin-btn:hover:not(:disabled) {
        background: var(--field-pill-number-spin-hover-bg);
        color: var(--text-secondary);
    }

    .field-pill-number-spin-btn:focus-visible {
        outline: 2px solid var(--accent);
        outline-offset: -1px;
        z-index: 1;
    }

    .field-pill-number-spin-btn:disabled {
        opacity: 0.45;
        cursor: not-allowed;
        pointer-events: none;
    }

    .field-pill-number-spin-btn svg {
        display: block;
        flex-shrink: 0;
    }

    /* Enum combobox — inline-поиск, список в стиле glass (редактор platform-field-enum) */

    .field-pill-enum-wrap {
        position: relative;
        display: flex;
        align-items: stretch;
        width: 100%;
        min-width: 0;
        height: var(--field-pill-number-spin-height);
        min-height: var(--field-pill-number-spin-height);
        box-sizing: border-box;
    }

    .field-pill-enum-input {
        flex: 1;
        min-width: 0;
        min-height: 0;
        align-self: stretch;
        padding-right: 28px;
        cursor: text;
    }

    .field-pill--compact .field-pill-enum-input {
        padding-right: 24px;
    }

    .field-pill-enum-chevron {
        position: absolute;
        pointer-events: auto;
        top: 50%;
        transform: translateY(-50%);
        right: var(--space-2);
        width: 12px;
        height: 12px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0;
        border: 0;
        border-radius: var(--radius-sm);
        background-color: transparent;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2371717a' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
        background-repeat: no-repeat;
        background-position: center;
        cursor: pointer;
    }

    .field-pill-enum-chevron:disabled {
        cursor: not-allowed;
        opacity: 0.5;
    }

    .field-pill-enum-chevron:focus-visible {
        outline: 2px solid var(--accent);
        outline-offset: 2px;
    }

    :host-context([data-theme='light']) .field-pill-enum-chevron {
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2352525b' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
    }

    .field-pill-enum-list {
        position: absolute;
        z-index: var(--field-pill-enum-list-z, var(--z-dropdown));
        left: 0;
        right: 0;
        top: calc(100% + 4px);
        margin: 0;
        padding: var(--space-1) 0;
        list-style: none;
        max-height: min(280px, 46vh);
        overflow-x: hidden;
        overflow-y: auto;
        box-sizing: border-box;
        background: var(--glass-solid-medium);
        border: 1px solid var(--glass-border-subtle);
        border-radius: var(--radius-md);
        box-shadow: var(--shadow-md, 0 10px 30px rgba(0, 0, 0, 0.2));
        backdrop-filter: blur(var(--glass-blur-subtle));
        -webkit-backdrop-filter: blur(var(--glass-blur-subtle));
    }

    .field-pill-enum-opt {
        margin: 0;
        padding: var(--space-2) var(--space-3);
        cursor: pointer;
        font-size: var(--field-pill-readonly-muted-size);
        font-weight: var(--font-medium);
        line-height: var(--leading-tight);
        color: var(--text-primary);
        transition: background var(--duration-fast) var(--easing-default);
    }

    .field-pill-enum-opt:hover {
        background: var(--accent-subtle);
    }

    .field-pill-enum-opt:focus {
        outline: none;
        background: var(--accent-subtle);
    }

    .field-pill-enum-opt--selected {
        background: var(--glass-solid-subtle);
        font-weight: var(--font-semibold);
    }

    .field-pill-enum-opt--selected:hover {
        background: var(--accent-subtle);
    }

    .field-pill-enum-empty {
        margin: 0;
        padding: var(--space-2) var(--space-3);
        font-size: var(--field-pill-readonly-muted-size);
        color: var(--text-tertiary);
        list-style: none;
    }
`;
