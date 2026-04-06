/**
 * Стили контента CRM glass-modal для импорта знаний: при открытии модалка порталится в document.body,
 * слот не находится в shadow namespace-imports-page — без этих правил сетка карточек и блоки мастера не оформлены.
 */
export const CRM_IMPORT_PORTAL_STYLE_ELEMENT_ID = 'crm-knowledge-import-portal-styles';

export function ensureKnowledgeImportPortalStyles() {
    if (typeof document === 'undefined') {
        return;
    }
    let el = document.getElementById(CRM_IMPORT_PORTAL_STYLE_ELEMENT_ID);
    if (!el) {
        el = document.createElement('style');
        el.id = CRM_IMPORT_PORTAL_STYLE_ELEMENT_ID;
        document.head.appendChild(el);
    }
    el.textContent = CRM_IMPORT_PORTAL_CSS;
}

const CRM_IMPORT_PORTAL_CSS = `
[slot="actions"].crm-import-glass-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2, 8px);
    flex-wrap: wrap;
    width: 100%;
    box-sizing: border-box;
}

.crm-import-glass-content {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 12px);
    min-height: 200px;
    box-sizing: border-box;
}

.crm-import-glass-content.import-wizard {
    gap: var(--space-4, 16px);
}

.crm-import-glass-content .ki-step1-settings-row {
    display: flex;
    flex-direction: row;
    flex-wrap: nowrap;
    align-items: center;
    gap: var(--space-2, 8px);
    min-width: 0;
}

.crm-import-glass-content .ki-step1-settings-link {
    color: var(--crm-button-primary-bg);
    font-size: var(--text-sm, 14px);
    font-weight: 600;
    text-decoration: none;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.crm-import-glass-content .ki-step1-settings-link:hover {
    text-decoration: underline;
}

.crm-import-glass-content .ki-step1-settings-row platform-help-hint {
    flex-shrink: 0;
}

.crm-import-glass-content.import-wizard .type-card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(124px, 1fr));
    gap: var(--space-4, 16px);
    justify-items: center;
    width: 100%;
    max-width: 100%;
    box-sizing: border-box;
}

.crm-import-glass-content.import-wizard .type-card {
    position: relative;
    aspect-ratio: 1;
    width: 100%;
    max-width: 136px;
    margin: 0;
    box-sizing: border-box;
    border: 2px solid var(--crm-stroke);
    border-radius: var(--radius-xl, 16px);
    background: var(--crm-surface-elevated);
    color: var(--text-primary);
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-2, 8px);
    padding: var(--space-3, 12px) var(--space-2, 8px);
    text-align: center;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
    transition:
        border-color 0.15s ease,
        background 0.15s ease,
        box-shadow 0.15s ease,
        transform 0.15s ease;
}

.crm-import-glass-content.import-wizard .type-card:hover {
    border-color: var(--crm-selected-stroke);
    background: var(--crm-surface-muted);
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(153, 166, 249, 0.14);
}

.crm-import-glass-content.import-wizard .type-card:focus-visible {
    outline: 2px solid var(--crm-button-primary-bg);
    outline-offset: 2px;
}

.crm-import-glass-content.import-wizard .type-card.selected {
    border-color: var(--crm-button-primary-bg);
    background: var(--crm-selected-bg);
    box-shadow: 0 4px 20px rgba(153, 166, 249, 0.22);
}

.crm-import-glass-content.import-wizard .type-card-icon-wrap {
    width: 48px;
    height: 48px;
    border-radius: var(--radius-lg, 12px);
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--crm-surface);
    border: 1px solid var(--crm-stroke);
    color: var(--text-secondary);
}

.crm-import-glass-content.import-wizard .type-card.selected .type-card-icon-wrap {
    border-color: var(--crm-button-primary-bg);
    color: var(--crm-button-primary-bg);
    background: var(--crm-surface-elevated);
}

.crm-import-glass-content.import-wizard .type-card-title {
    font-size: var(--text-xs, 12px);
    font-weight: 600;
    line-height: 1.25;
    word-break: break-word;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.crm-import-glass-content.import-wizard .type-card-check {
    position: absolute;
    top: var(--space-1, 4px);
    right: var(--space-1, 4px);
    width: 24px;
    height: 24px;
    border-radius: var(--radius-full, 999px);
    background: var(--crm-button-primary-bg);
    color: var(--crm-button-primary-text);
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transform: scale(0.85);
    transition: opacity 0.15s ease, transform 0.15s ease;
}

.crm-import-glass-content.import-wizard .type-card.selected .type-card-check {
    opacity: 1;
    transform: scale(1);
}

.crm-import-glass-content .detail-meta {
    color: var(--text-secondary);
    font-size: var(--text-sm, 14px);
    display: flex;
    flex-direction: column;
    gap: var(--space-2, 8px);
}

.crm-import-glass-content .import-detail-entities-heading {
    margin: var(--space-2, 8px) 0 0 0;
    font-size: var(--text-lg, 18px);
    font-weight: 700;
    color: var(--text-primary);
}

.crm-import-glass-content .import-detail-entities-scroll {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 12px);
    max-height: min(55vh, 520px);
    overflow-y: auto;
    overflow-x: hidden;
    min-width: 0;
    padding-right: var(--space-1, 4px);
}

.crm-import-glass-content .import-detail-entity-card {
    border-radius: var(--radius-xl, 16px);
    padding: 12px;
    display: flex;
    align-items: flex-start;
    gap: var(--space-2, 8px);
    border: none;
    min-width: 0;
    max-width: 100%;
    box-sizing: border-box;
}

.crm-import-glass-content .import-detail-entity-card.blue {
    background: rgba(153, 166, 249, 0.3);
}

.crm-import-glass-content .import-detail-entity-card.yellow {
    background: rgba(250, 209, 122, 0.34);
}

.crm-import-glass-content .import-detail-entity-card.orange {
    background: rgba(255, 154, 118, 0.28);
}

.crm-import-glass-content .import-detail-entity-avatar {
    width: 64px;
    height: 64px;
    border-radius: var(--radius-md, 10px);
    background: var(--crm-surface-elevated);
    border: none;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
    flex-shrink: 0;
}

.crm-import-glass-content .import-detail-entity-main {
    flex: 1;
    min-width: 0;
}

.crm-import-glass-content .import-detail-entity-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-2, 8px);
    min-width: 0;
    flex-wrap: wrap;
}

.crm-import-glass-content .import-detail-entity-titles {
    min-width: 0;
    flex: 1;
}

.crm-import-glass-content .import-detail-entity-name {
    display: inline-block;
    max-width: 100%;
    box-sizing: border-box;
    font-weight: 600;
    font-size: var(--text-base, 16px);
    color: var(--text-primary);
    background: var(--crm-surface-elevated);
    border-radius: 12px;
    padding: 4px 12px;
    line-height: 1.35;
    overflow-wrap: anywhere;
    word-break: break-word;
}

.crm-import-glass-content .import-detail-entity-sub {
    color: var(--text-tertiary);
    font-size: var(--text-xs, 12px);
    margin-top: 6px;
    line-height: 1.35;
}

.crm-import-glass-content .import-detail-entity-meta {
    display: flex;
    align-items: center;
    gap: var(--space-2, 8px);
    flex-shrink: 0;
    margin-left: auto;
}

.crm-import-glass-content .import-detail-entity-badge {
    font-size: var(--text-xs, 12px);
    border-radius: var(--radius-full, 999px);
    padding: 3px 10px;
    color: var(--text-primary);
    font-weight: 600;
    white-space: nowrap;
}

.crm-import-glass-content .import-detail-entity-badge.blue {
    background: #8e9bf7;
    color: #fff;
}

.crm-import-glass-content .import-detail-entity-badge.yellow {
    background: #f0c35f;
    color: #3d2f00;
}

.crm-import-glass-content .import-detail-entity-badge.orange {
    background: #f78d61;
    color: #fff;
}

.crm-import-glass-content .import-detail-entity-score-track {
    height: 16px;
    border-radius: var(--radius-full, 999px);
    background: var(--glass-tint-strong, rgba(255, 255, 255, 0.12));
    margin-top: var(--space-2, 8px);
    position: relative;
    overflow: hidden;
}

.crm-import-glass-content .import-detail-entity-score-fill {
    height: 100%;
    border-radius: inherit;
}

.crm-import-glass-content .import-detail-entity-score-fill.blue {
    background: #8e9bf7;
}

.crm-import-glass-content .import-detail-entity-score-fill.yellow {
    background: #f0c35f;
}

.crm-import-glass-content .import-detail-entity-score-fill.orange {
    background: #f78d61;
}

.crm-import-glass-content .import-detail-entity-score-label {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: var(--text-xs, 12px);
    color: var(--text-inverse);
}

.crm-import-glass-content .import-detail-entity-open {
    margin-top: var(--space-2, 8px);
    border: none;
    background: var(--crm-surface-elevated);
    color: var(--crm-selected-text);
    border-radius: var(--radius-full, 999px);
    padding: 6px 14px;
    font-size: var(--text-sm, 14px);
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
}

.crm-import-glass-content .import-detail-entity-open:hover {
    background: var(--crm-selected-bg);
    color: var(--crm-button-primary-bg);
}

.crm-import-glass-content .form-label {
    color: var(--text-secondary);
    font-size: var(--text-sm, 14px);
}

.crm-import-glass-content .mono {
    font-family: ui-monospace, monospace;
    font-size: var(--text-xs, 12px);
}

.crm-import-glass-content .nw-block {
    border: 1px solid var(--crm-stroke);
    border-radius: var(--radius-xl, 16px);
    background: var(--crm-surface-muted);
    padding: var(--space-4, 16px);
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 12px);
    min-width: 0;
}

.crm-import-glass-content .nw-block-title {
    margin: 0;
    font-size: var(--text-sm, 14px);
    font-weight: 700;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.crm-import-glass-content .ki-step3-files-heading-row {
    display: flex;
    flex-direction: row;
    justify-content: flex-start;
    align-items: center;
    gap: var(--space-2, 8px);
    flex-wrap: wrap;
    min-width: 0;
}

.crm-import-glass-content .ki-step3-files-title {
    text-align: left;
    flex-shrink: 0;
    min-width: 0;
}

.crm-import-glass-content .ki-step3-files-heading-row platform-help-hint {
    flex-shrink: 0;
}

.crm-import-glass-content .nw-switch-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4, 16px);
    flex-wrap: wrap;
}

.crm-import-glass-content .nw-switch-text {
    display: flex;
    flex-direction: column;
    gap: var(--space-1, 4px);
    min-width: 0;
    flex: 1;
}

.crm-import-glass-content .nw-switch-head {
    font-size: var(--text-base, 16px);
    font-weight: 600;
    color: var(--text-primary);
}

.crm-import-glass-content .nw-switch-sub {
    font-size: var(--text-sm, 14px);
    color: var(--text-secondary);
    line-height: 1.45;
}

.crm-import-glass-content .nw-textarea {
    min-height: 140px;
    width: 100%;
    box-sizing: border-box;
    border: 1px solid var(--crm-stroke);
    border-radius: var(--radius-xl, 16px);
    background: var(--crm-surface-elevated);
    color: var(--text-primary);
    padding: var(--space-3, 12px);
    font-family: inherit;
    font-size: var(--text-sm, 14px);
    line-height: 1.5;
    resize: vertical;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.crm-import-glass-content .nw-textarea:focus {
    outline: none;
    border-color: rgba(153, 166, 249, 0.65);
    box-shadow: 0 0 0 3px rgba(153, 166, 249, 0.2);
}

.crm-import-glass-content .nw-input-number {
    width: 100%;
    max-width: 220px;
    box-sizing: border-box;
    border: 1px solid var(--crm-stroke);
    border-radius: var(--radius-xl, 16px);
    background: var(--crm-surface-elevated);
    color: var(--text-primary);
    padding: var(--space-3, 12px);
    font-size: var(--text-sm, 14px);
    font-variant-numeric: tabular-nums;
}

.crm-import-glass-content .nw-input-number:focus {
    outline: none;
    border-color: rgba(153, 166, 249, 0.65);
    box-shadow: 0 0 0 3px rgba(153, 166, 249, 0.2);
}

.crm-import-glass-content .dropzone {
    position: relative;
    border: 2px dashed var(--crm-stroke);
    border-radius: var(--radius-xl, 16px);
    background: var(--crm-surface-elevated);
    padding: var(--space-5, 20px);
    text-align: center;
    cursor: pointer;
    transition:
        border-color 0.15s ease,
        background 0.15s ease,
        box-shadow 0.15s ease;
}

.crm-import-glass-content .dropzone:hover,
.crm-import-glass-content .dropzone.dropzone--active {
    border-color: rgba(153, 166, 249, 0.75);
    background: var(--crm-selected-bg);
    box-shadow: 0 0 0 1px rgba(153, 166, 249, 0.25);
}

.crm-import-glass-content .dropzone:focus-visible {
    outline: none;
    border-color: rgba(153, 166, 249, 0.75);
    box-shadow: 0 0 0 3px rgba(153, 166, 249, 0.2);
}

.crm-import-glass-content .dropzone-input {
    position: absolute;
    width: 0;
    height: 0;
    opacity: 0;
    pointer-events: none;
}

.crm-import-glass-content .dropzone-title {
    font-size: var(--text-base, 16px);
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 var(--space-1, 4px) 0;
}

.crm-import-glass-content .dropzone-sub {
    margin: 0;
    font-size: var(--text-sm, 14px);
    color: var(--text-secondary);
}

.crm-import-glass-content .file-chips {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-3, 12px);
    width: 100%;
    box-sizing: border-box;
}

.crm-import-glass-content .file-chip {
    display: flex;
    align-items: center;
    gap: var(--space-2, 8px);
    min-width: 0;
    max-width: 100%;
    padding: var(--space-2, 8px) var(--space-3, 12px);
    border-radius: var(--radius-lg, 12px);
    border: 1px solid var(--crm-stroke);
    background: var(--crm-surface);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.crm-import-glass-content .file-chip-icon {
    flex-shrink: 0;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-md, 10px);
    background: var(--crm-surface-muted);
}

.crm-import-glass-content .file-chip-meta {
    min-width: 0;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.crm-import-glass-content .file-chip-name {
    font-size: var(--text-sm, 14px);
    font-weight: 600;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.crm-import-glass-content .file-chip-id {
    font-size: var(--text-xs, 12px);
    font-family: ui-monospace, monospace;
    color: var(--text-tertiary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.crm-import-glass-content .file-chip-remove {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border: none;
    background: none;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0;
    border-radius: var(--radius-md, 10px);
}

.crm-import-glass-content .file-chip-remove:hover {
    color: var(--error, #f43f5e);
    background: rgba(244, 63, 94, 0.08);
}

.crm-import-glass-content .file-chip-remove platform-icon {
    pointer-events: none;
}

.crm-import-glass-content .ki-step4-intro {
    margin: 0;
    font-size: var(--text-sm, 14px);
    color: var(--text-secondary);
}

.crm-import-glass-content .ki-step4-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: var(--space-3, 12px);
    width: 100%;
    box-sizing: border-box;
}

.crm-import-glass-content .ki-step4-card {
    border: 1px solid var(--crm-stroke);
    border-radius: var(--radius-xl, 16px);
    background: var(--crm-surface-elevated);
    padding: var(--space-3, 12px);
    display: flex;
    flex-direction: column;
    gap: var(--space-2, 8px);
    min-height: 88px;
    box-sizing: border-box;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.crm-import-glass-content .ki-step4-card--wide {
    grid-column: 1 / -1;
    min-height: 0;
}

.crm-import-glass-content .ki-step4-card-label {
    font-size: var(--text-xs, 12px);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    color: var(--text-tertiary);
}

.crm-import-glass-content .ki-step4-card-value {
    font-size: var(--text-sm, 14px);
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.4;
    word-break: break-word;
}

.crm-import-glass-content .ki-step4-sources-body {
    display: flex;
    flex-direction: column;
    gap: var(--space-2, 8px);
}

.crm-import-glass-content .ki-step4-file-strip {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 8px);
    align-items: center;
}

.crm-import-glass-content .ki-step4-file-mini {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border-radius: var(--radius-lg, 12px);
    border: 1px solid var(--crm-stroke);
    background: var(--crm-surface-muted);
    box-sizing: border-box;
}

.crm-import-glass-content .ki-step4-file-mini-icon {
    flex-shrink: 0;
}

.crm-import-glass-content .ki-step4-text-badge {
    display: inline-block;
    align-self: flex-start;
    font-size: var(--text-xs, 12px);
    font-weight: 600;
    color: var(--text-secondary);
    padding: var(--space-1, 4px) var(--space-2, 8px);
    border-radius: var(--radius-md, 10px);
    background: var(--crm-selected-bg);
    border: 1px solid var(--crm-stroke);
}
`;
