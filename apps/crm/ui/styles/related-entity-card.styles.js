/**
 * Стили карточки связанной сущности: сайдбар заметки и списки «связанные».
 */

import { css } from 'lit';

export const relatedEntityCardSharedStyles = css`
    .related-list {
        display: flex;
        flex-direction: column;
        gap: var(--space-3);
    }
    .related-card {
        display: flex;
        align-items: flex-start;
        gap: var(--space-3);
        padding: 12px;
        border-radius: var(--radius-lg);
        background: var(--crm-note-related-violet-bg);
        cursor: pointer;
        border: none;
        width: 100%;
        max-width: 100%;
        min-width: 0;
        box-sizing: border-box;
        text-align: left;
        color: var(--text-primary);
        font-family: inherit;
        transition: filter var(--duration-fast);
    }
    .related-card:hover {
        filter: brightness(0.97);
    }
    .related-card.tone-violet {
        background: var(--crm-note-related-violet-bg);
    }
    .related-card.tone-yellow {
        background: var(--crm-note-related-yellow-bg);
    }
    .related-card.tone-orange {
        background: var(--crm-note-related-orange-bg);
    }

    .related-icon {
        width: 64px;
        height: 64px;
        border-radius: var(--radius-md);
        background: var(--crm-note-related-icon-gradient);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        color: #ffffff;
        flex-shrink: 0;
    }

    .related-body {
        display: flex;
        flex-direction: column;
        gap: 4px;
        min-width: 0;
        flex: 1;
    }
    .related-name {
        margin: 0;
        font-size: 16px;
        line-height: 20px;
        font-weight: 600;
        color: var(--text-primary);
        font-family: var(--font-sans);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .related-position {
        margin: 0;
        font-size: 12px;
        line-height: 15px;
        color: var(--crm-note-text-muted);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .related-empty {
        font-size: 16px;
        line-height: 20px;
        color: var(--crm-note-text-muted);
    }

    .neighbor-rows {
        display: flex;
        flex-direction: column;
        gap: var(--space-3);
        width: 100%;
        max-width: 100%;
        min-width: 0;
        box-sizing: border-box;
    }
    .neighbor-line {
        position: relative;
        display: flex;
        flex-direction: row;
        align-items: flex-start;
        gap: var(--space-2);
        width: 100%;
        max-width: 100%;
        min-width: 0;
        box-sizing: border-box;
    }
    .neighbor-line .related-card {
        flex: 1 1 0;
        min-width: 0;
    }
    .neighbor-line .related-card.related-card--with-remove {
        padding-right: 44px;
    }
    .neighbor-line:has(.neighbor-semantic-index):has(.neighbor-remove) .related-card.related-card--with-remove {
        padding-right: 88px;
    }
    .neighbor-line:has(.neighbor-semantic-index):not(:has(.neighbor-remove)) .related-card {
        padding-right: 44px;
    }
    .neighbor-semantic-index {
        position: absolute;
        top: 8px;
        right: 8px;
        z-index: 1;
        box-sizing: border-box;
        width: 36px;
        height: 36px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border: none;
        border-radius: var(--radius-md);
        padding: 0;
        margin: 0;
        background: transparent;
        color: var(--text-tertiary);
        cursor: default;
        pointer-events: auto;
    }
    .neighbor-line:has(.neighbor-remove) .neighbor-semantic-index {
        right: 48px;
    }
    .neighbor-semantic-index--pending_embedding {
        color: color-mix(in srgb, var(--warning, #f59e0b) 90%, var(--text-primary));
    }
    .neighbor-semantic-index--absent {
        opacity: 0.85;
    }
    .neighbor-remove {
        position: absolute;
        top: 8px;
        right: 8px;
        z-index: 1;
        flex-shrink: 0;
        margin-top: 0;
        width: 36px;
        height: 36px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border: none;
        border-radius: var(--radius-md);
        background: transparent;
        color: var(--text-tertiary);
        cursor: pointer;
    }
    .neighbor-remove:hover:not(:disabled) {
        color: var(--text-primary);
        background: rgba(34, 34, 34, 0.06);
    }
    .neighbor-remove:disabled {
        opacity: 0.45;
        cursor: default;
    }
    .relationship-meta {
        margin: 0;
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        min-width: 0;
        max-width: 100%;
        font-size: 12px;
        line-height: 16px;
        color: var(--crm-note-text-muted);
    }
    .relationship-type {
        display: inline-flex;
        align-items: center;
        padding: 2px 8px;
        border-radius: var(--radius-full);
        background: var(--crm-note-action-bg);
        color: var(--text-primary);
        font-size: 11px;
        font-weight: 600;
    }
    .neighbor-strength {
        display: flex;
        flex-direction: column;
        gap: 6px;
        width: 100%;
        max-width: 100%;
        min-width: 0;
        margin-top: 2px;
        box-sizing: border-box;
    }
    .neighbor-strength-label {
        font-size: 12px;
        font-weight: 600;
        color: var(--text-secondary);
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .neighbor-strength-track {
        height: 8px;
        border-radius: 999px;
        background: rgba(34, 34, 34, 0.08);
        overflow: hidden;
        width: 100%;
        max-width: 100%;
        box-sizing: border-box;
    }
    .neighbor-strength-fill {
        height: 100%;
        max-width: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, #7b92ff, #a855f7);
        opacity: 0.85;
        box-sizing: border-box;
    }
    .neighbor-confidence {
        display: flex;
        flex-direction: column;
        gap: 6px;
        width: 100%;
        max-width: 100%;
        min-width: 0;
        margin-top: 2px;
        box-sizing: border-box;
    }
    .neighbor-confidence-label {
        font-size: 12px;
        font-weight: 600;
        color: var(--text-secondary);
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .neighbor-confidence-track {
        height: 8px;
        border-radius: 999px;
        background: rgba(34, 34, 34, 0.08);
        overflow: hidden;
        width: 100%;
        max-width: 100%;
        box-sizing: border-box;
    }
    .neighbor-confidence-fill {
        height: 100%;
        max-width: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, #22c55e, #16a34a);
        opacity: 0.85;
        box-sizing: border-box;
    }

    @media (max-width: 767px) {
        .related-card {
            gap: var(--space-2);
            padding: 10px;
        }
        .related-icon {
            width: 48px;
            height: 48px;
        }
    }
`;
