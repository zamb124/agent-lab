/**
 * Стили тулбара заметки, портированного в slot actions у page-header (тенит crm-note-page).
 * DOM рендерится через lit render() из CRMNoteCardView, поэтому стили карточки на этот узел не действуют.
 */
import { css } from 'lit';

export const crmNotePageMobileToolbarHostStyles = css`
    .crm-note-page-header-actions-row {
        display: inline-flex;
        align-items: center;
        gap: var(--space-2);
        flex-shrink: 0;
        max-width: 100%;
        min-width: 0;
    }

    .crm-note-page-card-toolbar-host {
        display: inline-flex;
        align-items: center;
        flex-shrink: 0;
        min-width: 0;
    }

    .crm-note-page-card-toolbar-host .header-actions {
        display: inline-flex;
        gap: var(--space-2);
        flex-shrink: 0;
        align-items: center;
    }

    .crm-note-page-card-toolbar-host .attachments-menu {
        position: relative;
    }

    .crm-note-page-card-toolbar-host .attachments-badge {
        position: absolute;
        right: -2px;
        top: -2px;
        min-width: 18px;
        height: 18px;
        border-radius: 999px;
        background: var(--accent);
        color: #fff;
        font-size: 11px;
        line-height: 18px;
        text-align: center;
        padding: 0 5px;
        box-sizing: border-box;
        border: 1px solid var(--crm-surface-elevated, var(--glass-solid-strong));
        font-weight: 600;
    }

    .crm-note-page-card-toolbar-host .attachments-popover {
        position: absolute;
        top: calc(100% + 8px);
        right: 0;
        width: min(420px, 80vw);
        max-height: 360px;
        overflow: auto;
        z-index: 40;
        background: var(--crm-surface-elevated, var(--glass-solid-strong));
        border: 1px solid var(--crm-stroke);
        border-radius: var(--radius-lg);
        box-shadow: var(--glass-shadow-medium);
        padding: var(--space-2);
        display: flex;
        flex-direction: column;
        gap: var(--space-1);
    }

    .crm-note-page-card-toolbar-host .attachments-popover-row {
        display: grid;
        grid-template-columns: auto minmax(0, 1fr) auto;
        align-items: center;
        gap: var(--space-2);
        padding: 8px;
        border-radius: var(--radius-md);
        background: transparent;
    }

    .crm-note-page-card-toolbar-host .attachments-popover-row:hover {
        background: var(--crm-note-action-bg);
    }

    .crm-note-page-card-toolbar-host .attachments-popover-info {
        min-width: 0;
    }

    .crm-note-page-card-toolbar-host .attachments-popover-name {
        margin: 0;
        font-size: 14px;
        line-height: 18px;
        color: var(--text-primary);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .crm-note-page-card-toolbar-host .attachments-popover-meta {
        margin: 0;
        font-size: 12px;
        line-height: 16px;
        color: var(--crm-note-text-muted);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .crm-note-page-card-toolbar-host .attachments-popover-actions {
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }

    .crm-note-page-card-toolbar-host .attachment-action-btn {
        width: 28px;
        height: 28px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border: none;
        border-radius: var(--radius-full);
        background: transparent;
        color: var(--crm-note-text-muted);
        cursor: pointer;
        text-decoration: none;
    }

    .crm-note-page-card-toolbar-host .attachment-action-btn:hover {
        background: var(--crm-note-action-bg-hover);
        color: var(--text-primary);
    }

    .crm-note-page-card-toolbar-host .attachments-popover-empty {
        padding: 10px 12px;
        color: var(--crm-note-text-muted);
        font-size: 13px;
        line-height: 16px;
    }

    .crm-note-page-card-toolbar-host .round-btn {
        width: 40px;
        height: 40px;
        flex: 0 0 40px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: var(--crm-note-action-bg);
        border: none;
        border-radius: var(--radius-full);
        color: var(--text-primary);
        cursor: pointer;
        transition: background var(--duration-fast);
    }

    .crm-note-page-card-toolbar-host .round-btn:hover:not(:disabled) {
        background: var(--crm-note-action-bg-hover);
    }

    .crm-note-page-card-toolbar-host .round-btn.danger {
        background: var(--crm-note-action-orange-bg);
        color: var(--crm-note-action-orange-color);
    }

    .crm-note-page-card-toolbar-host .round-btn.danger:hover:not(:disabled) {
        background: var(--crm-note-action-orange-bg);
        filter: brightness(1.1);
    }

    .crm-note-page-card-toolbar-host .round-btn:disabled {
        opacity: 0.4;
        cursor: not-allowed;
    }

    .crm-note-page-card-toolbar-host .pill-btn {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 14px;
        min-height: 40px;
        height: auto;
        box-sizing: border-box;
        background: var(--accent);
        color: #ffffff;
        border: none;
        border-radius: var(--radius-full);
        font-size: var(--text-sm);
        line-height: 1.2;
        font-weight: 500;
        cursor: pointer;
        transition: filter var(--duration-fast), background var(--duration-fast);
        white-space: nowrap;
        max-width: 46vw;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .crm-note-page-card-toolbar-host .pill-btn:hover:not(:disabled) {
        filter: brightness(1.05);
    }

    .crm-note-page-card-toolbar-host .pill-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    @media (max-width: 767px) {
        .crm-note-page-card-toolbar-host .attachments-popover {
            position: fixed;
            left: var(--space-3);
            right: var(--space-3);
            top: auto;
            width: auto;
            max-height: min(360px, calc(100vh - 160px));
        }
    }
`;
