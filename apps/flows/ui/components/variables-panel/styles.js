/**
 * VariablesPanel styles
 * CSS стили для variables panel
 */
import { css } from 'lit';

export const variablesPanelStyles = css`
    :host {
        display: block;
        width: 100%;
    }

    .variables-panel-container {
        background: var(--glass-solid-strong, rgba(40, 40, 64, 0.95));
        border: 1px solid var(--border-default, rgba(255,255,255,0.1));
        border-radius: var(--radius-lg, 12px);
        box-shadow: var(--glass-shadow-strong, 0 16px 48px rgba(0,0,0,0.4));
        overflow: hidden;
        display: flex;
        flex-direction: column;
    }

    .var-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 16px;
        border-bottom: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
    }

    .var-header-title {
        font-size: 14px;
        font-weight: 600;
        color: var(--text-primary, rgba(255,255,255,0.95));
    }

    .var-add-btn {
        width: 28px;
        height: 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.2s ease;
        color: var(--text-secondary, rgba(255,255,255,0.7));
    }

    .var-add-btn:hover {
        background: var(--accent, #6366f1);
        color: #ffffff;
        border-color: var(--accent, #6366f1);
    }

    .var-list {
        padding: 8px;
        display: flex;
        flex-direction: column;
        gap: 6px;
        max-height: 400px;
        overflow-y: auto;
    }

    .var-empty {
        padding: 24px 16px;
        text-align: center;
    }

    .var-empty-text {
        font-size: 13px;
        color: var(--text-tertiary, rgba(255,255,255,0.4));
    }

    .var-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px 12px;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.2s ease;
        gap: 8px;
    }

    .var-item:hover {
        background: rgba(255, 255, 255, 0.06);
        border-color: var(--accent, #6366f1);
    }

    .var-item.inherited {
        background: rgba(255, 255, 255, 0.02);
        border-color: rgba(255, 255, 255, 0.06);
        opacity: 0.7;
    }

    .var-item.inherited:hover {
        background: rgba(255, 255, 255, 0.04);
        border-color: rgba(255, 255, 255, 0.1);
    }

    .var-item-content {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 4px;
    }

    .var-item-header {
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .var-name {
        font-size: 13px;
        font-weight: 600;
        color: var(--text-primary, rgba(255,255,255,0.95));
        font-family: var(--font-mono, 'Monaco', 'Courier New', monospace);
    }

    .var-badge {
        padding: 2px 6px;
        font-size: 10px;
        font-weight: 600;
        color: var(--text-tertiary, rgba(255,255,255,0.5));
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .var-value {
        font-size: 12px;
        color: var(--text-secondary, rgba(255,255,255,0.7));
        font-family: var(--font-mono, 'Monaco', 'Courier New', monospace);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .var-delete {
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: transparent;
        border: none;
        color: var(--text-tertiary, rgba(255,255,255,0.4));
        cursor: pointer;
        border-radius: 4px;
        font-size: 20px;
        line-height: 1;
        transition: all 0.2s ease;
        flex-shrink: 0;
    }

    .var-delete:hover {
        background: rgba(239, 68, 68, 0.2);
        color: #ef4444;
    }
`;


