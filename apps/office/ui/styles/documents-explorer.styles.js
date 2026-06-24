/**
 * Shared explorer layout styles for Documents file manager.
 */
import { css } from 'lit';

export const documentsExplorerStyles = css`
    :host {
        display: flex;
        flex-direction: column;
        min-height: 0;
        flex: 1;
        width: 100%;
        height: 100%;
        position: relative;
    }
    .explorer-banner {
        flex-shrink: 0;
        padding: var(--space-3) var(--space-4) 0;
    }
    .page-body {
        display: flex;
        flex: 1;
        min-height: 0;
        overflow: hidden;
    }
    .main-pane {
        flex: 1;
        min-width: 0;
        min-height: 0;
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }
    .main-toolbar {
        flex-shrink: 0;
        padding: var(--space-3) var(--space-4) 0;
        background: var(--documents-explorer-toolbar-bg, var(--glass-solid-subtle));
        border-bottom: 1px solid var(--documents-explorer-divider, var(--glass-border-subtle));
    }
    .main-content {
        flex: 1;
        min-height: 0;
        display: flex;
        flex-direction: column;
        padding: var(--space-3) var(--space-4) var(--space-4);
        overflow: hidden;
    }
    .content-row {
        display: flex;
        flex: 1;
        min-height: 0;
        gap: 0;
        overflow: hidden;
    }
    .files-area {
        flex: 1;
        min-width: 0;
        min-height: 0;
        overflow: auto;
    }
    .files-area:not(.dropzone-empty) {
        display: flex;
        flex-direction: column;
    }
    .files-area platform-file-table {
        flex: 1;
        min-height: 0;
    }
    .files-area.dropzone-empty {
        display: flex;
        flex-direction: column;
        align-items: stretch;
        justify-content: stretch;
    }
    .dropzone-panel {
        flex: 1;
        min-height: 12rem;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: var(--space-3);
        padding: var(--space-8);
        text-align: center;
        border: 2px dashed var(--documents-empty-border, var(--glass-border-medium));
        border-radius: var(--radius-xl);
        background: var(--documents-empty-bg, var(--glass-tint-subtle));
        color: var(--text-secondary);
    }
    .dropzone-panel.drag-over {
        border-color: var(--accent);
        background: var(--documents-selected-bg, var(--accent-subtle));
    }
    .dropzone-icon {
        color: var(--text-tertiary);
        opacity: 0.5;
    }
    .dropzone-title {
        font-size: var(--text-lg);
        font-weight: 600;
        color: var(--text-primary);
    }
    .dropzone-hint {
        font-size: var(--text-sm);
        color: var(--text-tertiary);
        max-width: 28rem;
    }
    .dropzone-actions {
        display: flex;
        flex-wrap: wrap;
        gap: var(--space-2);
        justify-content: center;
        margin-top: var(--space-2);
    }
    .folder-rows {
        display: flex;
        flex-direction: column;
        gap: var(--space-1);
        margin-bottom: var(--space-3);
    }
    .folder-row {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        width: 100%;
        padding: var(--space-2) var(--space-3);
        border: 1px solid var(--glass-border-subtle);
        border-radius: var(--radius-lg);
        background: var(--glass-solid-subtle);
        color: var(--text-primary);
        font-size: var(--text-sm);
        font-weight: 500;
        text-align: left;
        cursor: pointer;
    }
    .folder-row:hover {
        border-color: var(--accent);
        background: var(--documents-selected-bg, var(--accent-subtle));
    }
    .folder-row.active {
        border-color: var(--documents-selected-stroke, var(--accent));
        color: var(--documents-selected-text, var(--accent));
        font-weight: 600;
    }
    .folder-row-label {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(var(--documents-explorer-grid-min, 11.25rem), 1fr));
        gap: var(--space-3);
    }
    .loading {
        padding: var(--space-6);
        color: var(--text-tertiary);
        text-align: center;
    }
    .drop-overlay {
        position: absolute;
        inset: 0;
        z-index: 20;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(0, 0, 0, 0.45);
        border: 2px dashed var(--accent);
        pointer-events: none;
    }
    :host-context([data-theme="light"]) .drop-overlay {
        background: rgba(255, 255, 255, 0.72);
    }
    .drop-overlay-inner {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: var(--space-2);
        color: var(--text-primary);
        font-weight: 600;
    }
    .upload-jobs {
        display: flex;
        flex-direction: column;
        gap: var(--space-2);
        margin-bottom: var(--space-3);
        flex-shrink: 0;
    }
    .upload-job {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        padding: var(--space-2) var(--space-3);
        border-radius: var(--radius-md);
        background: var(--glass-solid-medium);
        font-size: var(--text-sm);
    }
    .upload-job.failed { color: var(--danger); }
    .upload-job.done { color: var(--success, var(--accent)); }
    .bulk-bar {
        display: flex;
        align-items: center;
        gap: var(--space-3);
        padding: var(--space-2) var(--space-3);
        margin-bottom: var(--space-3);
        border-radius: var(--radius-lg);
        background: var(--documents-selected-bg, var(--accent-subtle));
        border: 1px solid var(--documents-selected-stroke, var(--accent));
        font-size: var(--text-sm);
        flex-shrink: 0;
    }
    .bulk-actions {
        display: flex;
        flex-wrap: wrap;
        gap: var(--space-2);
        margin-left: auto;
    }
    .mobile-catalog-btn {
        display: none;
    }
    @media (max-width: 767px) {
        .explorer-banner { padding: var(--space-2) var(--space-3) 0; }
        .main-toolbar { padding: var(--space-2) var(--space-3) 0; }
        .main-content { padding: var(--space-2) var(--space-3) var(--space-3); }
        .mobile-catalog-btn {
            display: inline-flex;
            margin: var(--space-2) var(--space-3) 0;
        }
    }
`;
