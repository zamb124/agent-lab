/**
 * ExecutionPanel styles
 * CSS стили для execution panel
 */
import { css } from 'lit';

export const executionPanelStyles = css`
    :host {
        display: block;
        width: 360px;
        max-height: min(85vh, 720px);
    }

    .execution-panel-container {
        background: var(--glass-solid-strong, rgba(40, 40, 64, 0.95));
        border: 1px solid var(--border-default, rgba(255,255,255,0.1));
        border-radius: 20px;
        box-shadow: var(--glass-shadow-strong, 0 16px 48px rgba(0,0,0,0.4));
        overflow-x: hidden;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        max-height: inherit;
        min-height: 0;
    }

    .execution-panel-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 16px;
        border-bottom: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
    }

    .execution-panel-title {
        font-size: 14px;
        font-weight: 600;
        color: var(--text-primary, rgba(255,255,255,0.95));
    }

    .execution-panel-actions {
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .action-btn {
        padding: 4px 10px;
        font-size: 12px;
        font-weight: 500;
        color: var(--text-secondary, rgba(255,255,255,0.7));
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .action-btn:hover:not(:disabled) {
        background: rgba(255, 255, 255, 0.1);
        color: var(--text-primary, rgba(255,255,255,0.95));
        border-color: var(--accent, #6366f1);
    }

    .action-btn:disabled {
        opacity: 0.4;
        cursor: not-allowed;
    }

    .close-btn {
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-left: 4px;
        font-size: 20px;
        font-weight: 400;
        line-height: 1;
        color: var(--text-tertiary, rgba(255,255,255,0.4));
        background: transparent;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .close-btn:hover {
        background: rgba(239, 68, 68, 0.2);
        color: #ef4444;
    }

    .execution-panel-body {
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        flex-shrink: 0;
        min-width: 0;
    }

    .input-row {
        display: flex;
        flex-direction: row;
        align-items: flex-start;
        gap: 10px;
        min-width: 0;
    }

    .input-tools-column {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 10px;
        flex-shrink: 0;
        padding-top: 2px;
    }

    .input-row .input-text {
        flex: 1;
        min-width: 0;
    }

    .btn-run-icon {
        flex-shrink: 0;
        width: 36px;
        height: 36px;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        cursor: pointer;
        transition: all 0.2s ease;
        color: var(--text-secondary, rgba(255, 255, 255, 0.7));
    }

    .btn-run-icon:hover:not(:disabled) {
        background: rgba(255, 255, 255, 0.1);
        color: var(--text-primary, rgba(255, 255, 255, 0.95));
        border-color: var(--accent, #6366f1);
    }

    .btn-run-icon:active:not(:disabled) {
        transform: scale(0.96);
    }

    .btn-run-icon:disabled {
        opacity: 0.45;
        cursor: not-allowed;
    }

    .btn-run-icon.btn-retry-icon:hover:not(:disabled) {
        border-color: var(--warning, #f59e0b);
    }

    .btn-run-icon platform-icon {
        color: inherit;
    }

    .input-question {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        padding: 12px;
        background: rgba(99, 102, 241, 0.1);
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: 8px;
        color: var(--text-primary, rgba(255,255,255,0.95));
        font-size: 14px;
        line-height: 1.5;
    }

    .input-question platform-icon {
        flex-shrink: 0;
        margin-top: 2px;
        color: var(--accent, #6366f1);
    }

    .input-question span {
        flex: 1;
    }

    .file-attach-btn {
        width: 36px;
        height: 36px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        cursor: pointer;
        transition: all 0.2s ease;
        color: var(--text-secondary, rgba(255,255,255,0.7));
        flex-shrink: 0;
    }

    .file-attach-btn:hover {
        background: rgba(255, 255, 255, 0.1);
        color: var(--text-primary, rgba(255,255,255,0.95));
        border-color: var(--accent, #6366f1);
    }

    .input-text {
        flex: 1;
        padding: 10px 12px;
        font-size: 14px;
        font-family: var(--font-sans);
        color: var(--text-primary, rgba(255,255,255,0.95));
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        outline: none;
        resize: vertical;
        transition: background 0.15s ease, border-color 0.15s ease;
    }

    .input-text:focus,
    .input-text:focus-visible {
        background: rgba(255, 255, 255, 0.045);
        border-color: rgba(255, 255, 255, 0.14);
        outline: none;
        box-shadow: none;
    }

    .input-text:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .input-text::placeholder {
        color: var(--text-tertiary, rgba(255,255,255,0.4));
    }

    .file-list {
        display: flex;
        flex-direction: column;
        gap: 6px;
    }

    .file-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 12px;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 6px;
        font-size: 12px;
    }

    .file-name {
        color: var(--text-secondary, rgba(255,255,255,0.7));
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .file-remove {
        width: 20px;
        height: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: transparent;
        border: none;
        color: var(--text-tertiary, rgba(255,255,255,0.4));
        cursor: pointer;
        border-radius: 4px;
        font-size: 18px;
        line-height: 1;
        transition: all 0.2s ease;
        flex-shrink: 0;
        margin-left: 8px;
    }

    .file-remove:hover {
        background: rgba(239, 68, 68, 0.2);
        color: #ef4444;
    }

    .execution-panel-footer {
        padding: 12px 16px;
        border-top: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
        flex-shrink: 0;
        min-width: 0;
    }

    .execution-panel-footer:empty {
        display: none;
        padding: 0;
        border-top: none;
    }

    .btn {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        padding: 10px 16px;
        font-size: 14px;
        font-weight: 600;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .btn-run {
        background: var(--accent, #6366f1);
        color: #ffffff;
    }

    .btn-run:hover:not(:disabled) {
        background: var(--accent-hover, #5558e3);
        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
    }

    .btn-run:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .btn-retry {
        background: var(--warning, #f59e0b);
    }

    .btn-retry:hover:not(:disabled) {
        background: #d97706;
        box-shadow: 0 4px 12px rgba(245, 158, 11, 0.4);
    }

    .btn-stop {
        background: #ef4444;
        color: #ffffff;
    }

    .btn-stop:hover {
        background: #dc2626;
        box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4);
    }

    .btn-resume {
        background: #10b981;
        color: #ffffff;
    }

    .btn-resume:hover {
        background: #059669;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4);
    }

    .result-section {
        border-top: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
    }

    .result-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 16px;
        font-size: 12px;
        font-weight: 600;
        color: var(--text-secondary, rgba(255,255,255,0.7));
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .result-clear {
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
    }

    .result-clear:hover {
        background: rgba(239, 68, 68, 0.2);
        color: #ef4444;
    }

    .result-content {
        padding: 12px 16px;
        font-size: 14px;
        color: var(--text-primary, rgba(255,255,255,0.95));
        line-height: 1.6;
        max-height: 200px;
        overflow-y: auto;
    }

    .mocks-section {
        border-top: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
        flex-shrink: 0;
        min-width: 0;
    }

    .mocks-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 16px;
        font-size: 12px;
        font-weight: 600;
        color: var(--text-secondary, rgba(255,255,255,0.7));
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .mocks-close {
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
    }

    .mocks-close:hover {
        background: rgba(255, 255, 255, 0.1);
        color: var(--text-primary, rgba(255,255,255,0.95));
    }

    .mocks-body {
        padding: 12px 16px;
        min-width: 0;
        overflow-x: hidden;
    }

    .error-section {
        border-top: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
        background: rgba(239, 68, 68, 0.05);
    }

    .error-header {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px 16px;
        font-size: 12px;
        font-weight: 600;
        color: var(--error, #ef4444);
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .error-header span {
        flex: 1;
    }

    .error-clear {
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
    }

    .error-clear:hover {
        background: rgba(239, 68, 68, 0.2);
        color: #ef4444;
    }

    .error-content {
        padding: 12px 16px;
        font-size: 13px;
        color: var(--text-primary, rgba(255,255,255,0.95));
        line-height: 1.6;
        max-height: 200px;
        overflow-y: auto;
        word-break: break-word;
        font-family: var(--font-mono, 'Courier New', monospace);
        background: rgba(239, 68, 68, 0.08);
        border-radius: 6px;
        margin: 0 16px 12px;
    }

    .error-actions {
        padding: 0 16px 12px;
        display: flex;
        justify-content: flex-end;
    }

    .error-copy-btn {
        padding: 6px 12px;
        font-size: 12px;
        font-weight: 500;
        color: var(--error, #ef4444);
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.3);
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .error-copy-btn:hover {
        background: rgba(239, 68, 68, 0.2);
        border-color: rgba(239, 68, 68, 0.5);
    }
`;

