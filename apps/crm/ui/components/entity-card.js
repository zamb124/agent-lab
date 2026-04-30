/**
 * CRMEntityCard — единая карточка сущности: просмотр и редактирование (и создание)
 * в одном компоненте и одной схеме секций. Логика форм и связей перенесена с
 * CRMEntityModal.
 *
 * Пропы:
 *   - surface: 'sidebar' | 'page'
 *   - panelMode: 'view' | 'edit' | 'create'
 *   - entity / entityId — для view и edit (create только prefill-поля)
 *   - layoutVariant: 'full' | 'detailSummary' — на странице детали вкладка «Карточка»
 *     в просмотре и редактировании: `full` (двухколоночная схема, связи; вложения — кнопка в шапке
 *     области карточки и popover, как у заметки);
 *     в боковой панели `detailSummary` ограничивает блоки без дубля с другими вкладками.
 *   - compact-stack — принудительно одна колонка (аватар сверху), для узкой панели быстрого просмотра
 *   - cardBundle — опционально { entity, relationships, related_entities, attachments }
 *   - prefillEntityType / prefillNamespace — для create
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';
import './crm-related-entity-cards.js';
import './crm-related-neighbor-rows.js';
import {
    entityDisplayIconName,
    normalizeCatalogIconName,
} from '../utils/related-entity-presenter.js';
import { extractNeighborEdges } from '../utils/neighbor-edges.js';
import { searchScorePercent, relationshipConfidencePercent } from '../utils/search-score-percent.js';

const CREATE_FORM = 'crm/entity_create_form';
const EDIT_FORM = 'crm/entity_edit_form';
const ENTITIES_NAME = 'crm/entities';
const ENTITY_TYPES_NAME = 'crm/entity_types';
const RELATIONSHIPS_NAME = 'crm/relationships';
const RELATIONSHIP_TYPES_NAME = 'crm/relationship_types';

const MODE_CREATE = 'create';
const MODE_EDIT = 'edit';
const MODE_VIEW = 'view';

const ENTITY_STATUS_VALUES = Object.freeze(['active', 'archived', 'draft', 'completed']);

let _entityCardAttachInputSeq = 0;
function _nextEntityCardAttachInputId() {
    _entityCardAttachInputSeq += 1;
    return `entity-card-attach-${_entityCardAttachInputSeq}`;
}

function _entityCardFormatBytes(value) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return '';
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function _entityCardFileExtension(filename) {
    if (typeof filename !== 'string') return '';
    const trimmed = filename.trim().toLowerCase();
    const dotIndex = trimmed.lastIndexOf('.');
    if (dotIndex <= 0 || dotIndex === trimmed.length - 1) return '';
    return trimmed.slice(dotIndex + 1);
}

function _entityCardAttachmentIcon(filename, contentType) {
    const ext = _entityCardFileExtension(filename);
    const mime = typeof contentType === 'string' ? contentType.toLowerCase() : '';
    if (mime.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'heic'].includes(ext)) {
        return 'image';
    }
    if (mime.startsWith('audio/') || ['mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac'].includes(ext)) {
        return 'microphone';
    }
    if (mime.startsWith('video/') || ['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(ext)) {
        return 'play';
    }
    if (['xls', 'xlsx', 'csv'].includes(ext)) {
        return 'chart';
    }
    if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) {
        return 'box';
    }
    if (mime === 'application/pdf' || ext === 'pdf') {
        return 'doc-detail';
    }
    if (['doc', 'docx', 'txt', 'rtf', 'md', 'odt', 'ppt', 'pptx'].includes(ext)) {
        return 'text-fields';
    }
    if (['json', 'xml', 'yaml', 'yml', 'py', 'js', 'ts', 'tsx', 'jsx', 'html', 'css', 'sql'].includes(ext)) {
        return 'code';
    }
    return 'paperclip';
}

export class CRMEntityCard extends PlatformElement {
    static i18nNamespace = 'crm';

    static properties = {
        surface: { type: String },
        panelMode: { type: String, attribute: 'panel-mode' },
        layoutVariant: { type: String, attribute: 'layout-variant' },
        entity: { attribute: false },
        entityId: { type: String, attribute: 'entity-id' },
        cardBundle: { attribute: false },
        prefillEntityType: { type: String, attribute: 'prefill-entity-type' },
        prefillNamespace: { type: String, attribute: 'prefill-namespace' },
        showEntityActions: { type: Boolean, attribute: 'show-entity-actions' },
        /** Вертикальная схема (аватар сверху), как на узкой ширине — для панели быстрого просмотра */
        compactStack: { type: Boolean, attribute: 'compact-stack' },
        /** Тулбар редактирования рендерит родитель (entity-detail-page) */
        hostToolbar: { type: Boolean, attribute: 'host-toolbar' },
        _step: { state: true },
        _tagDraft: { state: true },
        _loadingCard: { state: true },
        _loadError: { state: true },
        _entityData: { state: true },
        _relationshipsData: { state: true },
        _relatedById: { state: true },
        _attachmentsData: { state: true },
        _loadingAttachments: { state: true },
        _addRelOpen: { state: true },
        _addRelType: { state: true },
        _addRelDirection: { state: true },
        _addRelTargetQuery: { state: true },
        _addRelTarget: { state: true },
        _addRelSearchResults: { state: true },
        _addRelSearching: { state: true },
        _addRelBusy: { state: true },
        _uploading: { state: true },
        _grantsExpanded: { state: true },
        _relatedExpanded: { state: true },
        _isDirty: { state: true },
        _attachmentsPopoverOpen: { state: true },
        _attachmentsPopoverMode: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-xl, 16px);
                overflow: hidden;
                box-shadow: 0 1px 0 color-mix(in srgb, var(--text-primary) 6%, transparent);
            }
            :host([surface='page']) {
                border-radius: var(--radius-lg);
                width: 100%;
                max-width: none;
            }
            :host([surface='page'][panel-mode='edit']) {
                border: none;
                box-shadow: none;
                background: transparent;
                max-width: none;
            }

            .edit-page-sheet {
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                width: 100%;
                padding-bottom: var(--space-6);
            }
            .edit-page-toolbar {
                display: flex;
                flex-direction: row;
                flex-wrap: wrap;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
            }
            .edit-page-title {
                margin: 0;
                font-size: 1.375rem;
                font-weight: 700;
                color: var(--text-primary);
                line-height: 1.2;
            }
            .edit-page-toolbar-right {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
            }
            .edit-template-box {
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 140px;
                padding: 10px 16px;
                background: var(--crm-surface-tint-strong);
                border-radius: 16px;
                border: 1px solid var(--crm-stroke);
            }
            .edit-template-label {
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.03em;
                color: var(--text-tertiary);
            }
            .edit-template-value {
                font-size: 15px;
                font-weight: 600;
                color: var(--text-primary);
            }
            .btn-circle-danger {
                width: 44px;
                height: 44px;
                border: none;
                border-radius: 14px;
                background: var(--crm-danger-bg);
                color: var(--error);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            .btn-circle-danger:hover {
                background: color-mix(in srgb, var(--error) 28%, transparent);
            }
            .btn-pill-primary {
                min-height: 44px;
                padding: 0 24px;
                border: none;
                border-radius: 22px;
                background: var(--crm-button-primary-bg);
                color: var(--crm-button-primary-text);
                font-size: 15px;
                font-weight: 600;
                cursor: pointer;
            }
            .btn-pill-primary:hover:not(:disabled) {
                background: var(--crm-button-primary-hover);
            }
            .btn-pill-primary:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .btn-pill-ghost {
                min-height: 44px;
                padding: 0 18px;
                border: none;
                border-radius: 22px;
                background: var(--crm-surface-tint-strong);
                color: var(--text-secondary);
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
            }
            .btn-pill-ghost:hover {
                background: var(--glass-tint-strong);
                color: var(--text-primary);
            }

            .entity-card-layout-container {
                container-type: inline-size;
                container-name: entity-card-sheet;
            }

            .edit-two-col {
                display: grid;
                grid-template-columns: minmax(160px, 220px) 1fr;
                gap: var(--space-6);
                align-items: start;
            }
            @container entity-card-sheet (max-width: 480px) {
                .edit-two-col {
                    grid-template-columns: 1fr;
                }
            }
            .entity-card-layout-container--force-stack .edit-two-col {
                grid-template-columns: 1fr;
            }
            .edit-aside {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-2);
            }
            .edit-avatar-wrap {
                width: 100%;
                max-width: 220px;
                aspect-ratio: 1;
                border-radius: 28px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: linear-gradient(
                    145deg,
                    color-mix(in srgb, var(--edit-type-color, var(--accent)) 42%, #fff),
                    color-mix(in srgb, var(--edit-type-color, var(--accent)) 18%, #fce7f3)
                );
                color: color-mix(in srgb, var(--edit-type-color, var(--accent)) 75%, #1e1b4b);
                box-shadow: var(--glass-shadow-subtle);
            }
            .edit-avatar-wrap platform-icon {
                width: min(140px, 64%);
                height: min(140px, 64%);
            }
            .edit-fields {
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                min-width: 0;
            }
            .edit-fields-heading-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) auto;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: 0;
                min-width: 0;
            }
            .edit-fields-heading-row .edit-fields-heading {
                margin: 0;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .edit-fields-heading-actions {
                flex-shrink: 0;
                justify-self: end;
                margin: 0;
                padding: 0;
                display: inline-flex;
                align-items: center;
            }
            .edit-fields-heading-actions .attachments-menu {
                display: inline-flex;
                align-items: center;
                line-height: 0;
            }
            .round-btn--compact {
                width: 28px;
                height: 28px;
                padding: 0;
                margin: 0;
            }
            .round-btn--compact platform-icon {
                display: block;
                line-height: 0;
            }
            .round-btn--compact .attachments-badge {
                min-width: 14px;
                height: 14px;
                font-size: 9px;
                line-height: 14px;
                padding: 0 3px;
                right: -2px;
                top: -2px;
            }
            .edit-fields-heading {
                font-size: 1.05rem;
                font-weight: 700;
                color: var(--text-primary);
            }
            .edit-subheading {
                margin: var(--space-2) 0 0;
                font-size: 13px;
                font-weight: 600;
                color: var(--text-secondary);
            }
            .edit-name-status-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
            }
            @media (max-width: 640px) {
                .edit-name-status-row {
                    grid-template-columns: 1fr;
                }
            }
            .field-pill {
                display: flex;
                flex-direction: column;
                gap: 8px;
                padding: 14px 18px;
                border-radius: 18px;
                box-sizing: border-box;
                background: var(--glass-tint-medium);
                border: 1px solid var(--border-subtle);
            }
            .field-pill--textarea {
                gap: 10px;
            }
            .field-pill--tags {
                gap: 10px;
            }
            .field-pill--tags .tags-row {
                min-height: 28px;
            }
            .field-pill--tags .tag-input {
                flex: 1;
                min-width: 140px;
                margin: 0;
                padding: 2px 0;
                border: none;
                border-radius: 0;
                background: transparent;
                box-shadow: none;
                font-family: inherit;
                font-size: 16px;
                font-weight: 500;
                color: var(--text-primary);
            }
            .field-pill--tags .tag-input:focus {
                outline: none;
            }
            .field-pill--tags .tag-input::placeholder {
                color: var(--text-tertiary);
                font-weight: 400;
            }
            .field-pill--tags .tag-chip {
                border: none;
                background: var(--glass-tint-strong);
            }
            .field-pill-tags-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .field-pill-label {
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-secondary);
            }
            :host-context([data-theme="light"]) .field-pill-label {
                color: var(--text-tertiary);
            }
            .field-pill-input,
            .field-pill-textarea,
            .field-pill-select {
                width: 100%;
                border: none;
                background: transparent;
                font-family: inherit;
                font-size: 16px;
                font-weight: 500;
                color: var(--text-primary);
                padding: 0;
                margin: 0;
            }
            .field-pill-textarea {
                resize: vertical;
                min-height: 120px;
                line-height: 1.5;
                font-weight: 400;
            }
            .field-pill-input:focus,
            .field-pill-textarea:focus,
            .field-pill-select:focus {
                outline: none;
            }
            .field-pill-select {
                cursor: pointer;
            }
            .field-pill-readonly-text {
                font-size: 16px;
                font-weight: 500;
                color: var(--text-primary);
                line-height: 1.45;
                white-space: pre-wrap;
                word-break: break-word;
                margin: 0;
            }
            .field-pill-readonly-muted {
                font-size: 14px;
                font-weight: 400;
                color: var(--text-tertiary);
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
                background: var(--accent-subtle);
                color: var(--accent);
                font-size: 12px;
                font-weight: 700;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            :host-context([data-theme="light"]) .tag-count-badge {
                color: var(--crm-selected-text);
            }
            .edit-attrs-grid .attrs-grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: var(--space-4);
                padding: 0;
                border: none;
                background: transparent;
            }
            .edit-attrs-grid .attr-row {
                display: grid;
                gap: var(--space-2);
                padding: 14px 18px;
                border-radius: 18px;
                box-sizing: border-box;
                background: var(--glass-tint-medium);
                border: 1px solid var(--border-subtle);
            }
            @media (max-width: 720px) {
                .edit-attrs-grid .attrs-grid {
                    grid-template-columns: 1fr;
                }
            }
            .edit-related-block {
                margin-top: var(--space-2);
            }
            .btn-add-rel-pill {
                border-radius: 22px !important;
                background: var(--accent-subtle) !important;
                color: var(--accent) !important;
                border: none !important;
                font-weight: 600 !important;
            }
            .btn-add-rel-pill:hover {
                background: color-mix(in srgb, var(--accent) 28%, transparent) !important;
                color: var(--accent-hover) !important;
            }

            .scroll {
                flex: 1;
                overflow-y: auto;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                min-height: 0;
            }

            .empty {
                display: flex;
                flex: 1;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                color: var(--text-tertiary);
                padding: var(--space-6);
                text-align: center;
            }
            .empty-title { font-size: var(--text-base); color: var(--text-secondary); }
            .empty-subtitle { font-size: var(--text-sm); }

            .sheet-block {
                border-radius: var(--radius-md);
                overflow: hidden;
                border: 1px solid var(--crm-stroke);
            }
            .sheet-cell-head {
                font-size: var(--text-xs);
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-tertiary);
                padding: 10px var(--space-3);
                background: var(--crm-surface-tint);
                border-bottom: 1px solid var(--crm-stroke);
            }
            .sheet-cell-body {
                padding: var(--space-3);
                background: var(--crm-surface);
                border-bottom: 1px solid var(--crm-stroke);
            }
            .sheet-block:last-of-type .sheet-cell-body {
                border-bottom: none;
            }
            .sheet-cell-body .attrs-grid {
                padding: 0;
                border: none;
                background: transparent;
            }
            .sheet-cell-body .attrs-grid.empty-section {
                padding: var(--space-2) 0;
            }
            .sheet-cell-body .description-field[readonly] {
                min-height: 1.5em;
            }

            .form-select {
                width: 100%;
                max-width: 360px;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-primary);
                font-family: inherit;
                font-size: var(--text-sm);
            }

            .hero {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                padding-bottom: var(--space-2);
                border-bottom: 1px solid var(--crm-stroke);
            }
            .type-icon {
                width: 52px;
                height: 52px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                background: color-mix(in srgb, var(--accent) 12%, transparent);
                color: var(--accent);
                flex-shrink: 0;
            }
            .hero-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--space-2); }

            .title-field {
                width: 100%;
                margin: 0;
                font-size: var(--text-xl);
                font-weight: 700;
                color: var(--text-primary);
                line-height: 1.25;
                padding: var(--space-1) 0;
                border: none;
                border-bottom: 1px solid transparent;
                background: transparent;
                font-family: inherit;
            }
            .title-field:not([readonly]):focus {
                outline: none;
                border-bottom-color: var(--accent);
            }
            .title-field[readonly] {
                cursor: default;
            }

            .meta-row {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
                align-items: center;
            }
            .meta-row .dot { opacity: 0.4; }

            .search-score {
                display: flex;
                align-items: center;
                gap: 6px;
                height: 18px;
                position: relative;
                background: var(--crm-surface-tint);
                border-radius: 8px;
                overflow: hidden;
                max-width: 220px;
            }
            .search-score .score-bar {
                position: absolute;
                left: 0;
                top: 0;
                height: 100%;
                background: linear-gradient(90deg, #3b82f6, #8b5cf6);
                opacity: 0.25;
            }
            .search-score .score-label {
                position: relative;
                z-index: 1;
                font-size: 11px;
                font-weight: 600;
                padding-left: 8px;
            }
            .search-score .match-type-badge {
                position: relative;
                z-index: 1;
                font-size: 9px;
                text-transform: uppercase;
                color: var(--text-tertiary);
                margin-left: auto;
                padding-right: 8px;
            }

            .status-badge {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px 8px;
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                font-weight: 500;
                background: var(--crm-surface-tint);
                color: var(--text-secondary);
            }
            .status-badge.active { background: rgba(34, 197, 94, 0.15); color: #16a34a; }
            .status-badge.archived { background: rgba(148, 163, 184, 0.15); color: #64748b; }
            .status-badge.draft { background: rgba(251, 191, 36, 0.2); color: #b45309; }
            .status-badge.completed { background: rgba(59, 130, 246, 0.15); color: #1d4ed8; }

            .form-grid { display: grid; gap: var(--space-4); }
            .form-row { display: grid; gap: var(--space-2); }

            .badge-row {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
                align-items: center;
            }
            .badge {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: 4px var(--space-2);
                border-radius: var(--radius-full);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            .badge.type {
                background: var(--crm-selected-bg);
                color: var(--text-primary);
                font-weight: 600;
            }
            .badge .swatch {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--accent);
            }
            .change-link {
                background: transparent;
                border: none;
                color: var(--accent);
                cursor: pointer;
                font-size: var(--text-xs);
                padding: 0;
            }

            .type-grid {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            }
            .type-card {
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-surface-muted);
                text-align: left;
                cursor: pointer;
                display: grid;
                gap: var(--space-1);
                transition: border-color var(--duration-fast), transform var(--duration-fast);
            }
            .type-card:hover {
                border-color: var(--crm-selected-stroke);
                transform: translateY(-1px);
            }
            .type-card .name {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-primary);
                font-weight: 600;
                font-size: var(--text-sm);
            }
            .type-card .desc {
                color: var(--text-secondary);
                font-size: var(--text-xs);
                line-height: 1.4;
            }
            .type-card .id {
                font-family: var(--font-mono);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .empty-hint {
                padding: var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-md);
            }
            .loading-block {
                padding: var(--space-6);
                display: flex;
                justify-content: center;
            }
            .error-block {
                padding: var(--space-4);
                color: var(--color-danger);
                text-align: center;
            }

            .section {
                display: grid;
                gap: var(--space-3);
            }
            .section-title {
                display: flex;
                align-items: center;
                justify-content: space-between;
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--text-primary);
                padding-top: var(--space-2);
                border-top: 1px solid var(--crm-stroke);
            }
            .section-title.text-only {
                justify-content: flex-start;
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-tertiary);
                border-top: none;
                padding-top: 0;
            }

            .attrs-grid {
                display: grid;
                gap: var(--space-3);
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface-muted);
            }
            .attrs-grid.empty-section {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-align: center;
                padding: var(--space-2) var(--space-3);
            }
            .attr-row {
                display: grid;
                gap: var(--space-1);
            }
            .attr-hint { color: var(--text-tertiary); font-size: var(--text-xs); }

            .tags-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                align-items: center;
            }
            .tag-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: 2px var(--space-2);
                border-radius: var(--radius-full);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                font-size: var(--text-xs);
                color: var(--text-primary);
            }
            .tag-chip button {
                background: transparent; border: none; color: var(--text-tertiary);
                cursor: pointer; padding: 0; line-height: 1;
            }
            .tag-input {
                flex: 1; min-width: 120px;
                padding: var(--space-1) var(--space-2);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-xs);
            }

            .description-field {
                width: 100%;
                min-height: 88px;
                resize: vertical;
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
                color: var(--text-primary);
                font-family: inherit;
                font-size: var(--text-sm);
                line-height: 1.5;
            }
            .description-field[readonly] {
                border-color: transparent;
                background: transparent;
                padding-left: 0;
                padding-right: 0;
            }

            .actions-bar {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
                min-height: 36px;
                padding: 0 var(--space-3);
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-weight: 500;
                cursor: pointer;
            }
            .btn:hover { background: var(--crm-surface); color: var(--text-primary); }
            .btn-primary {
                background: var(--accent);
                color: var(--text-inverse, #fff);
                border-color: transparent;
            }
            .btn-primary:hover { filter: brightness(1.05); }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .actions-bar-lead {
                margin-right: auto;
            }

            .attachments-menu { position: relative; }
            .attachments-badge {
                position: absolute;
                right: -4px;
                top: -4px;
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
            .attachments-popover {
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
            .attachments-popover-row {
                display: grid;
                grid-template-columns: auto minmax(0, 1fr) auto;
                align-items: center;
                gap: var(--space-2);
                padding: 8px;
                border-radius: var(--radius-md);
                background: transparent;
            }
            .attachments-popover-row:hover { background: var(--crm-note-action-bg); }
            .attachments-popover-info { min-width: 0; }
            .attachments-popover-name {
                margin: 0;
                font-size: 14px;
                line-height: 18px;
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .attachments-popover-meta {
                margin: 0;
                font-size: 12px;
                line-height: 16px;
                color: var(--crm-note-text-muted);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .attachments-popover-actions {
                display: inline-flex;
                align-items: center;
                gap: 4px;
            }
            .attachment-action-btn {
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
            .attachment-action-btn:hover {
                background: var(--crm-note-action-bg-hover);
                color: var(--text-primary);
            }
            .attachments-popover-empty {
                padding: 10px 12px;
                color: var(--crm-note-text-muted);
                font-size: 13px;
                line-height: 16px;
            }
            .visually-hidden-file-input {
                position: absolute;
                width: 1px;
                height: 1px;
                padding: 0;
                margin: -1px;
                overflow: hidden;
                clip: rect(0, 0, 0, 0);
                border: 0;
                opacity: 0;
                pointer-events: none;
            }
            .round-btn,
            label.round-btn {
                position: relative;
                width: 44px;
                height: 44px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 0;
                margin: 0;
                box-sizing: border-box;
                background: var(--crm-note-action-bg);
                border: none;
                border-radius: var(--radius-full);
                color: var(--text-primary);
                cursor: pointer;
                transition: background var(--duration-fast);
                -webkit-appearance: none;
                appearance: none;
            }
            .round-btn:hover:not(:disabled),
            label.round-btn:hover:not(:disabled) { background: var(--crm-note-action-bg-hover); }
            .round-btn:disabled,
            label.round-btn:disabled { opacity: 0.4; cursor: not-allowed; }

            .icon-btn {
                background: transparent; border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                padding: var(--space-1);
                border-radius: var(--radius-md);
            }
            .icon-btn:hover { color: var(--color-danger); background: var(--glass-tint-medium); }
            .icon-btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .rel-add {
                display: grid;
                gap: var(--space-2);
                padding: var(--space-3);
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-md);
            }
            .rel-add .row {
                display: grid;
                grid-template-columns: 140px 1fr 1fr;
                gap: var(--space-2);
            }
            @media (max-width: 640px) {
                .rel-add .row { grid-template-columns: 1fr; }
            }
            .search-results {
                display: grid;
                gap: 2px;
                max-height: 180px;
                overflow-y: auto;
            }
            .search-result {
                display: grid;
                gap: 2px;
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-md);
                cursor: pointer;
                background: transparent;
                border: 1px solid transparent;
                text-align: left;
                color: var(--text-primary);
                font-size: var(--text-sm);
            }
            .search-result:hover {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
            }
            .search-result .id {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-family: var(--font-mono);
            }

            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                flex-wrap: wrap;
                padding: var(--space-3) var(--space-4);
                border-top: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
            }

            .empty-soft {
                padding: var(--space-2) var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .collapsible-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                cursor: pointer;
                padding: var(--space-2) 0;
                border-top: 1px solid var(--crm-stroke);
            }

            .collapsible-content { padding-bottom: var(--space-2); }

            .form-error {
                color: var(--color-danger);
                font-size: var(--text-xs);
            }
        `,
    ];

    constructor() {
        super();
        this.surface = 'sidebar';
        this.panelMode = MODE_VIEW;
        this.layoutVariant = 'full';
        this.entity = null;
        this.entityId = '';
        this.cardBundle = null;
        this.prefillEntityType = '';
        this.prefillNamespace = '';
        this.showEntityActions = true;
        this.compactStack = false;
        this.hostToolbar = false;

        this._step = 'form';
        this._tagDraft = '';
        this._loadingCard = false;
        this._loadError = null;
        this._entityData = null;
        this._relationshipsData = [];
        this._relatedById = {};
        this._attachmentsData = [];
        this._loadingAttachments = false;
        this._addRelOpen = false;
        this._addRelType = '';
        this._addRelDirection = 'outgoing';
        this._addRelTargetQuery = '';
        this._addRelTarget = null;
        this._addRelSearchResults = [];
        this._addRelSearching = false;
        this._addRelBusy = false;
        this._uploading = false;
        this._grantsExpanded = false;
        this._relatedExpanded = false;
        this._isDirty = false;
        this._attachmentsPopoverOpen = false;
        this._attachmentsPopoverMode = '';
        this._attachmentsPopoverCloseTimer = null;
        this._entityAttachmentInputId = _nextEntityCardAttachInputId();

        this._createForm = this.useForm(CREATE_FORM);
        this._editForm = this.useForm(EDIT_FORM);
        this._entities = this.useResource(ENTITIES_NAME);
        this._entityTypes = this.useResource(ENTITY_TYPES_NAME);
        this._relationships = this.useResource(RELATIONSHIPS_NAME);
        this._relationshipTypes = this.useResource(RELATIONSHIP_TYPES_NAME);

        this._cardOp = this.useOp('crm/entity_card');
        this._updateOp = this.useOp('crm/entity_update');
        this._attachmentsListOp = this.useOp('crm/attachments_list');
        this._attachmentUploadOp = this.useOp('crm/attachment_upload');
        this._attachmentDeleteOp = this.useOp('crm/attachment_delete');
        this._entitySearchOp = this.useOp('crm/entity_search');

        this._grantsOp = this.useOp('crm/entity_grants_list');
        this._relatedOp = this.useOp('crm/related_entities');

        this._namespaceSel = this.select((s) => {
            const user = s.auth.user;
            if (!user || typeof user.company_id !== 'string') return null;
            const cid = user.company_id;
            const map = s.ui.namespace.selectionByCompany;
            const sel = map[cid];
            if (sel === 'all' || sel === undefined || sel === null) return null;
            return sel;
        });

        this._typesQueryNamespace = '';
        this._searchTimer = null;
        this._cardBundleApplied = false;
    }

    connectedCallback() {
        super.connectedCallback();

        if (this.panelMode !== MODE_CREATE && this.panelMode !== MODE_EDIT && this.panelMode !== MODE_VIEW) {
            throw new Error(`CRMEntityCard: panelMode must be view|edit|create, got '${this.panelMode}'`);
        }
        if (this.panelMode === MODE_EDIT && (typeof this.entityId !== 'string' || this.entityId.length === 0)) {
            const e = this._resolveEntity();
            if (!e || typeof e.entity_id !== 'string') {
                throw new Error('CRMEntityCard: entityId required for panelMode=edit');
            }
            this.entityId = e.entity_id;
        }

        if (this.panelMode === MODE_CREATE) {
            this._initCreateDraft();
            this.useEvent(this._entities.resource.events.CREATED, (event) => this._onCreated(event));
            this.useEvent(this._entities.resource.events.CREATE_FAILED, () => this._onCreateFailed());
            return;
        }

        if (this.panelMode === MODE_EDIT) {
            this._editForm.openForm({
                id: this._effectiveEntityId(),
                entity_type: '',
                entity_subtype: '',
                name: '',
                description: '',
                status: '',
                attributes: {},
                tags: [],
            });
            this.useEvent(this._cardOp.op.events.SUCCEEDED, (event) => this._onCardLoaded(event));
            this.useEvent(this._cardOp.op.events.FAILED, (event) => this._onCardFailed(event));
            this.useEvent(this._updateOp.op.events.SUCCEEDED, () => this._onUpdateSucceeded());
            this.useEvent(this._attachmentsListOp.op.events.SUCCEEDED, (event) => this._onAttachmentsLoaded(event));
            this.useEvent(this._attachmentUploadOp.op.events.SUCCEEDED, () => this._reloadAttachments());
            this.useEvent(this._attachmentDeleteOp.op.events.SUCCEEDED, () => this._reloadAttachments());
            this.useEvent(this._relationships.resource.events.CREATED, () => this._onRelationshipChanged());
            this.useEvent(this._relationships.resource.events.REMOVED, () => this._onRelationshipChanged());
            this.useEvent(this._entitySearchOp.op.events.SUCCEEDED, (event) => this._onSearchResults(event));
            this._relationshipTypes.load(null);
            this._applyCardBundleOrLoad();
            return;
        }

        this.useEvent(this._attachmentsListOp.op.events.SUCCEEDED, (event) => this._onAttachmentsLoaded(event));
        this.useEvent(this._attachmentUploadOp.op.events.SUCCEEDED, () => this._reloadAttachments());
        this.useEvent(this._attachmentDeleteOp.op.events.SUCCEEDED, () => this._reloadAttachments());
        const viewAttachId = this._effectiveEntityId();
        if (typeof viewAttachId === 'string' && viewAttachId.length > 0 && !this.cardBundle) {
            this._reloadAttachments();
        }

        this._relationshipTypes.load(null);
    }

    disconnectedCallback() {
        if (this._searchTimer !== null) {
            clearTimeout(this._searchTimer);
            this._searchTimer = null;
        }
        if (this._attachmentsPopoverCloseTimer !== null) {
            clearTimeout(this._attachmentsPopoverCloseTimer);
            this._attachmentsPopoverCloseTimer = null;
        }
        if (this.panelMode === MODE_CREATE) {
            this._createForm.close();
        } else if (this.panelMode === MODE_EDIT) {
            this._editForm.close();
        }
        super.disconnectedCallback();
    }

    _effectiveEntityId() {
        if (typeof this.entityId === 'string' && this.entityId.length > 0) return this.entityId;
        const data = this._entityData;
        if (data && typeof data.entity_id === 'string' && data.entity_id.length > 0) return data.entity_id;
        const fromProp = this.entity;
        if (fromProp && typeof fromProp.entity_id === 'string' && fromProp.entity_id.length > 0) {
            return fromProp.entity_id;
        }
        return '';
    }

    _applyCardBundleOrLoad() {
        if (this.cardBundle && typeof this.cardBundle === 'object' && this.cardBundle.entity) {
            this._hydrateFromBundle(this.cardBundle);
            return;
        }
        this._loadCard();
    }

    _hydrateFromBundle(bundle) {
        const card = bundle;
        if (!card.entity || typeof card.entity !== 'object') {
            throw new Error('CRMEntityCard: cardBundle.entity required');
        }
        this._loadingCard = false;
        this._loadError = null;
        this._entityData = card.entity;
        this._applyRelatedAttachmentsFromBundle(card);
        this._editForm.openForm({
            id: this._effectiveEntityId(),
            entity_type: typeof this._entityData.entity_type === 'string' ? this._entityData.entity_type : '',
            entity_subtype: typeof this._entityData.entity_subtype === 'string' ? this._entityData.entity_subtype : '',
            name: typeof this._entityData.name === 'string' ? this._entityData.name : '',
            description: typeof this._entityData.description === 'string' ? this._entityData.description : '',
            status: typeof this._entityData.status === 'string' ? this._entityData.status : 'active',
            attributes: this._entityData.attributes && typeof this._entityData.attributes === 'object'
                ? { ...this._entityData.attributes }
                : {},
            tags: Array.isArray(this._entityData.tags) ? [...this._entityData.tags] : [],
        });
        this._isDirty = false;
        this._cardBundleApplied = true;
    }

    _applyRelatedAttachmentsFromBundle(card) {
        if (!card || typeof card !== 'object') {
            throw new Error('CRMEntityCard._applyRelatedAttachmentsFromBundle: card required');
        }
        this._relationshipsData = Array.isArray(card.relationships) ? card.relationships : [];
        const related = Array.isArray(card.related_entities) ? card.related_entities : [];
        const relatedMap = {};
        for (const r of related) {
            if (r && typeof r.entity_id === 'string') relatedMap[r.entity_id] = r;
        }
        this._relatedById = relatedMap;
        this._attachmentsData = Array.isArray(card.attachments) ? card.attachments : [];
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('entityId') && this.panelMode === MODE_VIEW) {
            const id = this._effectiveEntityId();
            if (id && (!this.entity || this.entity.entity_id !== id)) {
                this._entities.get(id);
            }
        }
        if (changed.has('entityId') && this.panelMode === MODE_VIEW && this.layoutVariant === 'full') {
            const attachId = this._effectiveEntityId();
            if (typeof attachId === 'string' && attachId.length > 0 && !this.cardBundle) {
                this._reloadAttachments();
            }
        }
        if (changed.has('cardBundle') && this.panelMode === MODE_EDIT && this.cardBundle) {
            this._hydrateFromBundle(this.cardBundle);
        }
        if (changed.has('cardBundle') && this.panelMode === MODE_VIEW && this.surface === 'page') {
            if (this.cardBundle && typeof this.cardBundle === 'object') {
                this._applyRelatedAttachmentsFromBundle(this.cardBundle);
            } else {
                this._relationshipsData = [];
                this._relatedById = {};
                this._attachmentsData = [];
            }
        }

        this._syncDirty();

        if (this.panelMode === MODE_VIEW) {
            const ent = this._resolveEntity();
            if (ent && typeof ent.namespace === 'string' && ent.namespace.length > 0) {
                if (this._typesQueryNamespace !== ent.namespace) {
                    this._typesQueryNamespace = ent.namespace;
                    this._entityTypes.load({ namespace: ent.namespace });
                }
            }
        } else if (this.panelMode === MODE_EDIT) {
            const ent = this._entityData;
            if (ent && typeof ent.namespace === 'string' && ent.namespace.length > 0) {
                if (this._typesQueryNamespace !== ent.namespace) {
                    this._typesQueryNamespace = ent.namespace;
                    this._entityTypes.load({ namespace: ent.namespace });
                }
            }
        }

        this._syncEditPageTypeColor();
    }

    _syncEditPageTypeColor() {
        if (!((this.panelMode === MODE_EDIT || this.panelMode === MODE_VIEW) && this.surface === 'page')) {
            this.style.removeProperty('--edit-type-color');
            return;
        }
        const type = this._selectedType();
        const c = type && typeof type.color === 'string' && type.color.trim().length > 0 ? type.color.trim() : '';
        if (c.length > 0) {
            this.style.setProperty('--edit-type-color', c);
        } else {
            this.style.removeProperty('--edit-type-color');
        }
    }

    updated(_changed) {
        super.updated(_changed);
        if (!(this.panelMode === MODE_EDIT && this.surface === 'page' && this.hostToolbar)) {
            return;
        }
        const form = this._editForm;
        const draft = form.draft;
        const has_name = typeof draft.name === 'string' && draft.name.trim().length > 0;
        const saveDisabled = this._loadingCard || form.submitting || !has_name;
        this.emit('crm-entity-card-toolbar-state', {
            saveDisabled,
            submitting: form.submitting,
        });
        this.emit('crm-entity-card-storage-type-draft', {
            entity_type: typeof draft.entity_type === 'string' ? draft.entity_type : '',
            entity_subtype: typeof draft.entity_subtype === 'string' ? draft.entity_subtype : '',
        });
    }

    _syncDirty() {
        if (this.panelMode === MODE_CREATE) {
            const draft = this._createForm.draft;
            const dirty = (typeof draft.name === 'string' && draft.name.trim().length > 0)
                || (typeof draft.description === 'string' && draft.description.trim().length > 0)
                || (Object.keys(draft.attributes).length > 0)
                || (Array.isArray(draft.tags) && draft.tags.length > 0);
            this._isDirty = dirty;
            return;
        }
        if (this.panelMode !== MODE_EDIT || !this._entityData) {
            this._isDirty = false;
            return;
        }
        const draft = this._editForm.draft;
        const origDescription = typeof this._entityData.description === 'string' ? this._entityData.description : '';
        const origStatus = typeof this._entityData.status === 'string' && this._entityData.status.length > 0
            ? this._entityData.status
            : 'active';
        const origAttributes = this._entityData.attributes && typeof this._entityData.attributes === 'object'
            ? this._entityData.attributes
            : {};
        const origTags = Array.isArray(this._entityData.tags) ? this._entityData.tags : [];
        const origEt = typeof this._entityData.entity_type === 'string' ? this._entityData.entity_type : '';
        const origSt = typeof this._entityData.entity_subtype === 'string' ? this._entityData.entity_subtype : '';
        const draftDescription = typeof draft.description === 'string' ? draft.description : '';
        const draftStatus = typeof draft.status === 'string' && draft.status.length > 0 ? draft.status : 'active';
        const draftEt = typeof draft.entity_type === 'string' ? draft.entity_type : '';
        const draftSt = typeof draft.entity_subtype === 'string' ? draft.entity_subtype : '';
        this._isDirty = (draft.name !== this._entityData.name)
            || (draftDescription !== origDescription)
            || (draftStatus !== origStatus)
            || (draftEt !== origEt)
            || (draftSt !== origSt)
            || (JSON.stringify(draft.attributes) !== JSON.stringify(origAttributes))
            || (JSON.stringify(draft.tags) !== JSON.stringify(origTags));
    }

    _activeForm() {
        return this.panelMode === MODE_CREATE ? this._createForm : this._editForm;
    }

    _fieldUiMode() {
        if (this.panelMode === MODE_VIEW) return 'view';
        return 'edit';
    }

    _isReadOnlyShell() {
        return this.panelMode === MODE_VIEW;
    }

    _initCreateDraft() {
        const ns = typeof this.prefillNamespace === 'string' && this.prefillNamespace.length > 0
            ? this.prefillNamespace
            : (this._namespaceSel.value || 'default');
        const type = typeof this.prefillEntityType === 'string' ? this.prefillEntityType : '';
        this._createForm.openForm({
            entity_type: type,
            namespace: ns,
            name: '',
            description: '',
            attributes: {},
            tags: [],
        });
        this._step = type.length > 0 ? 'form' : 'type';
        this._loadTypes(ns);
    }

    _loadTypes(ns) {
        if (typeof ns !== 'string' || ns.length === 0) {
            throw new Error('CRMEntityCard._loadTypes: namespace required');
        }
        if (this._typesQueryNamespace === ns) return;
        this._typesQueryNamespace = ns;
        this._entityTypes.load({ namespace: ns });
    }

    _onTypePick(typeId) {
        if (typeof typeId !== 'string' || typeId.length === 0) {
            throw new Error('CRMEntityCard._onTypePick: typeId required');
        }
        this._createForm.setField('entity_type', typeId);
        this._createForm.setField('attributes', {});
        this._step = 'form';
    }

    _onChangeType() {
        this._createForm.setField('entity_type', '');
        this._createForm.setField('attributes', {});
        this._step = 'type';
    }

    _onCreated(event) {
        const payload = event && event.payload ? event.payload : null;
        if (!payload || !payload.item || typeof payload.item.entity_id !== 'string') {
            throw new Error('CRMEntityCard._onCreated: created entity missing entity_id');
        }
        this.emit('entity-created', { entity_id: payload.item.entity_id });
    }

    _onCreateFailed() {
        this._createForm.openForm(this._createForm.draft);
    }

    _onUpdateSucceeded() {
        this.emit('entity-saved', { entity_id: this._effectiveEntityId() });
        if (this.surface === 'page') {
            this._loadCard();
        }
    }

    _loadCard() {
        const id = this._effectiveEntityId();
        if (typeof id !== 'string' || id.length === 0) return;
        this._loadingCard = true;
        this._loadError = null;
        this._cardOp.run({ entity_id: id });
    }

    _reloadAttachments() {
        const id = this._effectiveEntityId();
        if (typeof id !== 'string' || id.length === 0) return;
        this._loadingAttachments = true;
        this._attachmentsListOp.run({ entity_id: id });
    }

    _onRelationshipChanged() {
        const id = this._effectiveEntityId();
        if (typeof id === 'string' && id.length > 0) {
            this._cardOp.run({ entity_id: id });
        }
    }

    _onCardLoaded(event) {
        this._loadingCard = false;
        const card = event && event.payload && event.payload.result;
        if (!card || typeof card !== 'object' || !card.entity) {
            throw new Error('CRMEntityCard: invalid card response (missing entity)');
        }
        this._entityData = card.entity;
        const relationships = Array.isArray(card.relationships) ? card.relationships : [];
        const related = Array.isArray(card.related_entities) ? card.related_entities : [];
        const relatedMap = {};
        for (const r of related) {
            if (r && typeof r.entity_id === 'string') relatedMap[r.entity_id] = r;
        }
        this._relationshipsData = relationships;
        this._relatedById = relatedMap;
        this._attachmentsData = Array.isArray(card.attachments) ? card.attachments : [];
        this._editForm.openForm({
            id: this._effectiveEntityId(),
            entity_type: typeof this._entityData.entity_type === 'string' ? this._entityData.entity_type : '',
            entity_subtype: typeof this._entityData.entity_subtype === 'string' ? this._entityData.entity_subtype : '',
            name: typeof this._entityData.name === 'string' ? this._entityData.name : '',
            description: typeof this._entityData.description === 'string' ? this._entityData.description : '',
            status: typeof this._entityData.status === 'string' ? this._entityData.status : 'active',
            attributes: this._entityData.attributes && typeof this._entityData.attributes === 'object'
                ? { ...this._entityData.attributes }
                : {},
            tags: Array.isArray(this._entityData.tags) ? [...this._entityData.tags] : [],
        });
        this._isDirty = false;
    }

    _onCardFailed(event) {
        this._loadingCard = false;
        const message = event && event.payload && typeof event.payload.message === 'string'
            ? event.payload.message
            : this.t('entity_modal.load_failed');
        this._loadError = message;
    }

    _onAttachmentsLoaded(event) {
        this._loadingAttachments = false;
        const result = event && event.payload && event.payload.result;
        if (!Array.isArray(result)) {
            throw new Error('CRMEntityCard._onAttachmentsLoaded: result must be array');
        }
        this._attachmentsData = result;
    }

    _onSearchResults(event) {
        const result = event && event.payload && event.payload.result;
        const items = result && Array.isArray(result.items) ? result.items : [];
        this._addRelSearching = false;
        const myId = this._effectiveEntityId();
        this._addRelSearchResults = items.filter((item) => item.entity_id !== myId);
    }

    _selectedType() {
        const items = this._entityTypes.items;
        if (this.panelMode === MODE_CREATE) {
            const draft = this._createForm.draft;
            if (typeof draft.entity_type !== 'string' || draft.entity_type.length === 0) return null;
            for (const item of items) {
                if (item.type_id === draft.entity_type) return item;
            }
            return null;
        }
        let storageType = '';
        let storageSubtypeNorm = null;
        if (this.panelMode === MODE_EDIT) {
            const draft = this._editForm.draft;
            storageType = typeof draft.entity_type === 'string' ? draft.entity_type : '';
            const ds = typeof draft.entity_subtype === 'string' && draft.entity_subtype.length > 0
                ? draft.entity_subtype
                : '';
            storageSubtypeNorm = ds.length > 0 ? ds : null;
        } else {
            const ent = this._resolveEntity();
            if (!ent) return null;
            storageType = typeof ent.entity_type === 'string' ? ent.entity_type : '';
            const ds = typeof ent.entity_subtype === 'string' && ent.entity_subtype.length > 0
                ? ent.entity_subtype
                : '';
            storageSubtypeNorm = ds.length > 0 ? ds : null;
        }
        if (storageType.length === 0) return null;
        for (const t of items) {
            const rowSt = t.list_entity_subtype === undefined || t.list_entity_subtype === null || t.list_entity_subtype === ''
                ? null
                : t.list_entity_subtype;
            if (t.list_entity_type === storageType && rowSt === storageSubtypeNorm) return t;
        }
        if (this.panelMode !== MODE_EDIT) {
            const ent = this._resolveEntity();
            if (!ent) return null;
            const typeId = storageSubtypeNorm !== null ? storageSubtypeNorm : storageType;
            for (const t of items) {
                if (t.type_id === typeId) return t;
            }
            for (const t of items) {
                if (t.type_id === ent.entity_type) return t;
            }
        }
        return null;
    }

    _onNameInput(event) { this._activeForm().setField('name', event.target.value); }
    _onDescriptionInput(event) { this._activeForm().setField('description', event.target.value); }
    _onStatusInput(event) { this._editForm.setField('status', event.target.value); }

    _onAttrChange(fieldKey, event) {
        if (fieldKey === 'external_refs') return;
        const value = event && event.detail ? event.detail.value : null;
        const form = this._activeForm();
        const draft = form.draft;
        const next = { ...draft.attributes };
        if (value === null || value === undefined || (typeof value === 'string' && value.trim().length === 0)) {
            delete next[fieldKey];
        } else {
            next[fieldKey] = value;
        }
        form.setField('attributes', next);
    }

    _onTagInput(event) { this._tagDraft = event.target.value; }
    _onTagKey(event) {
        if (event.key !== 'Enter' && event.key !== ',') return;
        event.preventDefault();
        const value = this._tagDraft.trim();
        if (value.length === 0) return;
        const form = this._activeForm();
        const draft = form.draft;
        if (Array.isArray(draft.tags) && draft.tags.includes(value)) {
            this._tagDraft = '';
            return;
        }
        const next = Array.isArray(draft.tags) ? [...draft.tags, value] : [value];
        form.setField('tags', next);
        this._tagDraft = '';
    }
    _onTagRemove(tag) {
        const form = this._activeForm();
        const draft = form.draft;
        if (!Array.isArray(draft.tags)) return;
        const next = draft.tags.filter((item) => item !== tag);
        form.setField('tags', next);
    }

    _performSave() {
        this._activeForm().submit();
    }

    triggerSave() {
        if (this.panelMode !== MODE_EDIT) {
            throw new Error('CRMEntityCard.triggerSave: panelMode must be edit');
        }
        this._performSave();
    }

    triggerEditCancel() {
        if (this.panelMode !== MODE_EDIT) {
            throw new Error('CRMEntityCard.triggerEditCancel: panelMode must be edit');
        }
        this._onFooterCancel();
    }

    setEditTemplateFromListRow(item) {
        if (this.panelMode !== MODE_EDIT) {
            throw new Error('CRMEntityCard.setEditTemplateFromListRow: panelMode must be edit');
        }
        if (!item || typeof item !== 'object') {
            throw new Error('CRMEntityCard.setEditTemplateFromListRow: item required');
        }
        const listEt = item.list_entity_type;
        if (typeof listEt !== 'string' || listEt.length === 0) {
            throw new Error('CRMEntityCard.setEditTemplateFromListRow: list_entity_type required');
        }
        const rawSub = item.list_entity_subtype;
        let subStr = '';
        if (typeof rawSub === 'string' && rawSub.length > 0) {
            subStr = rawSub;
        }
        this._editForm.setField('entity_type', listEt);
        this._editForm.setField('entity_subtype', subStr);
        this.requestUpdate();
    }

    _renderFieldError(field) {
        const error_key = this._activeForm().errors[field];
        if (!error_key) return null;
        return html`<div class="form-error">${this.t(error_key)}</div>`;
    }

    _attributesSchema(type) {
        const required = type && type.required_fields && typeof type.required_fields === 'object' ? type.required_fields : {};
        const optional = type && type.optional_fields && typeof type.optional_fields === 'object' ? type.optional_fields : {};
        const out = [];
        for (const [key, def] of Object.entries(required)) out.push({ key, def, required: true });
        for (const [key, def] of Object.entries(optional)) {
            if (key in required) continue;
            out.push({ key, def, required: false });
        }
        return out;
    }

    _fieldType(def, key) {
        if (typeof key === 'string' && key === 'external_refs') return 'external_refs';
        if (!def || typeof def !== 'object') return 'string';
        const t = typeof def.type === 'string' ? def.type.trim() : '';
        return t.length === 0 ? 'string' : t;
    }

    _inferAttrFieldType(key, value) {
        if (typeof key === 'string' && key === 'external_refs') return 'external_refs';
        if (value !== null && Array.isArray(value)) return 'array';
        if (value !== null && typeof value === 'object') return 'object';
        return 'string';
    }
    _fieldLabel(key, def) {
        if (def && typeof def.label === 'string' && def.label.length > 0) return def.label;
        return key;
    }
    _fieldConfig(def) {
        if (!def || typeof def !== 'object') return {};
        if (Array.isArray(def.values)) return { values: def.values };
        return {};
    }

    _renderAttributesSection() {
        const type = this._selectedType();
        const schema = this._attributesSchema(type);
        const draft = this.panelMode === MODE_VIEW
            ? null
            : this._activeForm().draft;
        const viewEnt = this.panelMode === MODE_VIEW ? this._resolveEntity() : null;
        const attributes = this.panelMode === MODE_VIEW
            ? (viewEnt && viewEnt.attributes && typeof viewEnt.attributes === 'object'
                ? viewEnt.attributes
                : {})
            : draft.attributes;
        const uiMode = this._fieldUiMode();

        if (schema.length === 0) {
            if (this.panelMode !== MODE_CREATE && Object.keys(attributes).length > 0) {
                return html`
                    <div class="attrs-grid">
                        ${Object.entries(attributes).map(([key, value]) => {
                            const inferred = this._inferAttrFieldType(key, value);
                            const readOnlyExternal = key === 'external_refs';
                            const editable = uiMode === 'edit' && !readOnlyExternal;
                            return html`
                            <div class="attr-row">
                                <platform-field
                                    .type=${inferred}
                                    .value=${value}
                                    mode=${uiMode}
                                    .label=${key}
                                    ?flat=${editable}
                                    ?disabled=${readOnlyExternal}
                                    @change=${editable ? (event) => this._onAttrChange(key, event) : undefined}
                                ></platform-field>
                            </div>
                        `;
                        })}
                    </div>
                `;
            }
            return html`<div class="attrs-grid empty-section">${this.t('entity_modal.attrs_empty')}</div>`;
        }
        return html`
            <div class="attrs-grid">
                ${schema.map(({ key, def, required }) => {
                    const fieldType = this._fieldType(def, key);
                    const value = attributes[key];
                    const readOnlyExternal = key === 'external_refs';
                    const editable = uiMode === 'edit' && !readOnlyExternal;
                    return html`
                        <div class="attr-row">
                            <platform-field
                                .type=${fieldType}
                                .value=${value === undefined ? null : value}
                                mode=${uiMode}
                                .label=${this._fieldLabel(key, def) + (required ? ' *' : '')}
                                .config=${this._fieldConfig(def)}
                                ?flat=${editable}
                                ?disabled=${readOnlyExternal}
                                @change=${editable ? (event) => this._onAttrChange(key, event) : undefined}
                            ></platform-field>
                            ${def && typeof def.description === 'string' && def.description.length > 0
                                ? html`<div class="attr-hint">${def.description}</div>`
                                : nothing}
                        </div>
                    `;
                })}
            </div>
        `;
    }

    _renderTagsSection(options = {}) {
        const omitLabel = options.omitLabel === true;
        const pill = options.pill === true;
        const draft = this.panelMode === MODE_VIEW
            ? null
            : this._activeForm().draft;
        const viewEnt = this.panelMode === MODE_VIEW ? this._resolveEntity() : null;
        const tags = this.panelMode === MODE_VIEW
            ? (viewEnt && Array.isArray(viewEnt.tags) ? viewEnt.tags : [])
            : (Array.isArray(draft.tags) ? draft.tags : []);
        const uiMode = this._fieldUiMode();

        if (uiMode === 'view' && pill) {
            const tagCount = tags.length;
            const inner = tags.length > 0
                ? html`
                    <div class="tags-row">
                        ${tags.map((tag) => html`<span class="tag-chip">${tag}</span>`)}
                    </div>
                `
                : html`<span class="field-pill-readonly-muted">${this.t('entity_card.view_tags_empty')}</span>`;
            return html`
                <div class="field-pill field-pill--tags">
                    <div class="field-pill-tags-head">
                        <span class="field-pill-label">${this.t('entity_modal.label_tags')}</span>
                        <span class="tag-count-badge">${tagCount}</span>
                    </div>
                    ${inner}
                </div>
            `;
        }
        if (uiMode === 'view') {
            if (tags.length === 0) return nothing;
            if (omitLabel) {
                return html`
                    <div class="tags-row">
                        ${tags.map((tag) => html`<span class="tag-chip">${tag}</span>`)}
                    </div>
                `;
            }
            return html`
                <div class="form-row">
                    <span class="section-title text-only">${this.t('entity_modal.label_tags')}</span>
                    <div class="tags-row">
                        ${tags.map((tag) => html`<span class="tag-chip">${tag}</span>`)}
                    </div>
                </div>
            `;
        }
        const tagsRowEdit = html`
                <div class="tags-row">
                    ${tags.map((tag) => html`
                        <span class="tag-chip">
                            ${tag}
                            <button type="button" @click=${() => this._onTagRemove(tag)}>
                                <platform-icon name="close" size="12"></platform-icon>
                            </button>
                        </span>
                    `)}
                    <input
                        type="text"
                        class="tag-input"
                        .value=${this._tagDraft}
                        placeholder=${this.t('entity_modal.tag_placeholder')}
                        @input=${this._onTagInput}
                        @keydown=${this._onTagKey}
                    />
                </div>
        `;
        const tagHintCreate = this.panelMode === MODE_CREATE
            ? html`<div class="attr-hint">${this.t('entity_modal.tag_hint')}</div>`
            : nothing;
        if (pill) {
            const tagCount = tags.length;
            return html`
                <div class="field-pill field-pill--tags">
                    <div class="field-pill-tags-head">
                        <span class="field-pill-label">${this.t('entity_modal.label_tags')}</span>
                        <span class="tag-count-badge">${tagCount}</span>
                    </div>
                    ${tagsRowEdit}
                </div>
                ${tagHintCreate}
            `;
        }
        const tagBody = html`
                ${tagsRowEdit}
                ${tagHintCreate}
        `;
        if (omitLabel) {
            return tagBody;
        }
        return html`
            <div class="form-row">
                <label class="form-label">${this.t('entity_modal.label_tags')}</label>
                ${tagBody}
            </div>
        `;
    }

    _renderTypeStep() {
        const items = this._entityTypes.items;
        if (this._entityTypes.loading && items.length === 0) {
            return html`<div class="empty-hint">${this.t('entity_modal.types_loading')}</div>`;
        }
        if (items.length === 0) {
            return html`<div class="empty-hint">${this.t('entity_modal.types_empty')}</div>`;
        }
        return html`
            <div class="form-row">
                <label class="form-label">${this.t('entity_modal.label_type')}</label>
                <div class="type-grid">
                    ${items.map((typ) => html`
                        <button
                            type="button"
                            class="type-card"
                            @click=${() => this._onTypePick(typ.type_id)}
                        >
                            <span class="name">
                                <span class="swatch" style=${`background: ${typeof typ.color === 'string' && typ.color.length > 0 ? typ.color : 'var(--accent)'}`}></span>
                                <platform-icon name=${typeof typ.icon === 'string' && typ.icon.length > 0 ? typ.icon : 'circle'} size="14"></platform-icon>
                                ${typ.name}
                            </span>
                            <span class="desc">${typeof typ.description === 'string' && typ.description.length > 0 ? typ.description : this.t('entity_modal.type_no_description')}</span>
                            <span class="id">${typ.type_id}</span>
                        </button>
                    `)}
                </div>
            </div>
        `;
    }

    _renderTypeBadge() {
        const type = this._selectedType();
        if (this.panelMode === MODE_CREATE) {
            if (!type) return nothing;
            const swatch_color = typeof type.color === 'string' && type.color.length > 0 ? type.color : 'var(--accent)';
            const draft = this._createForm.draft;
            return html`
                <div class="badge-row">
                    <span class="badge type">
                        <span class="swatch" style=${`background: ${swatch_color}`}></span>
                        <platform-icon name=${typeof type.icon === 'string' && type.icon.length > 0 ? type.icon : 'circle'} size="12"></platform-icon>
                        ${type.name}
                    </span>
                    <span class="badge">
                        <platform-icon name="folder" size="12"></platform-icon>
                        ${draft.namespace}
                    </span>
                    <button type="button" class="change-link" @click=${this._onChangeType}>
                        ${this.t('entity_modal.change_type')}
                    </button>
                </div>
            `;
        }
        const ent = this._resolveEntityForBadge();
        if (!ent) return nothing;
        const typeName = type ? type.name : ent.entity_type;
        const typeColor = type && typeof type.color === 'string' && type.color.length > 0 ? type.color : 'var(--accent)';
        const typeIcon = type && typeof type.icon === 'string' && type.icon.length > 0 ? type.icon : 'circle';
        return html`
            <div class="badge-row">
                <span class="badge type">
                    <span class="swatch" style=${`background: ${typeColor}`}></span>
                    <platform-icon name=${typeIcon} size="12"></platform-icon>
                    ${typeName}
                </span>
                <span class="badge">
                    <platform-icon name="folder" size="12"></platform-icon>
                    ${ent.namespace}
                </span>
                <span class="badge">
                    <platform-icon name="tag" size="12"></platform-icon>
                    ${ent.entity_id}
                </span>
            </div>
        `;
    }

    _resolveEntityForBadge() {
        if (this.panelMode === MODE_EDIT || this.panelMode === MODE_VIEW) {
            if (this._entityData) return this._entityData;
        }
        return this._resolveEntity();
    }

    _resolveEntity() {
        const fromProp = this.entity;
        if (fromProp && typeof fromProp === 'object') return fromProp;
        const id = this._effectiveEntityId();
        if (!id) return null;
        const byId = this._entities.byId;
        if (byId && byId[id]) return byId[id];
        return null;
    }

    _entityTypesCatalogRows() {
        const ctrl = this._entityTypes;
        if (!ctrl || ctrl.items === undefined || !Array.isArray(ctrl.items)) {
            return [];
        }
        return ctrl.items;
    }

    _heroIconName(entity) {
        const currentId = this._effectiveEntityId();
        const catalogRows = this._entityTypesCatalogRows();
        if (
            entity
            && typeof entity.entity_id === 'string'
            && entity.entity_id.length > 0
            && typeof currentId === 'string'
            && currentId.length > 0
            && entity.entity_id === currentId
        ) {
            const type = this._selectedType();
            if (type && typeof type.icon === 'string' && type.icon.length > 0) {
                return normalizeCatalogIconName(type.icon.trim());
            }
        }
        if (entity && typeof entity.entity_type === 'string' && entity.entity_type.length > 0) {
            return entityDisplayIconName(entity, catalogRows);
        }
        return 'folder';
    }

    _entityStatusLabelKey(statusRaw) {
        const v = typeof statusRaw === 'string' ? statusRaw.trim() : '';
        if (!ENTITY_STATUS_VALUES.includes(v)) {
            throw new Error(`CRMEntityCard: unsupported entity status '${statusRaw}'`);
        }
        return `entities.status.${v}`;
    }

    _renderHero(entity, nameValue, descriptionValue) {
        const readonly = this._isReadOnlyShell();
        const pct = searchScorePercent(entity);
        const statusRaw = entity && entity.status;
        const statusNorm = typeof statusRaw === 'string' ? statusRaw.trim() : '';
        const showStatusRow = Boolean(
            readonly
            && statusNorm.length > 0
            && ENTITY_STATUS_VALUES.includes(statusNorm),
        );
        return html`
            <div class="hero">
                <div class="type-icon">
                    <platform-icon name=${this._heroIconName(entity)} size="22"></platform-icon>
                </div>
                <div class="hero-main">
                    <input
                        type="text"
                        class="title-field"
                        ?readonly=${readonly}
                        autocomplete="off"
                        spellcheck="false"
                        placeholder=${this.t('entity_modal.name_placeholder')}
                        .value=${nameValue}
                        @input=${readonly ? undefined : this._onNameInput}
                    />
                    ${this._renderFieldError('name')}
                    <div class="meta-row">
                        ${entity && entity.entity_type
                            ? html`<span>${entity.entity_type}</span>`
                            : nothing}
                        ${entity && entity.entity_subtype
                            ? html`<span class="dot">/</span><span>${entity.entity_subtype}</span>`
                            : nothing}
                    </div>
                    ${pct !== null && entity
                        ? html`
                            <div class="search-score" title="score">
                                <div class="score-bar" style="width: ${Math.round(pct)}%"></div>
                                <span class="score-label">${pct.toFixed(0)}%</span>
                            </div>
                        `
                        : nothing}
                </div>
            </div>
            <div class="sheet-block">
                <div class="sheet-cell-head">${this.t('entity_modal.label_description')}</div>
                <div class="sheet-cell-body">
                    <textarea
                        class="description-field"
                        ?readonly=${readonly}
                        rows="4"
                        placeholder=${this.t('entity_modal.description_placeholder')}
                        .value=${descriptionValue}
                        @input=${readonly ? undefined : this._onDescriptionInput}
                    ></textarea>
                    ${this._renderFieldError('description')}
                </div>
            </div>
            ${showStatusRow
                ? html`
                    <div class="sheet-block">
                        <div class="sheet-cell-head">${this.t('entity_modal.label_status')}</div>
                        <div class="sheet-cell-body">
                            <span class="status-badge ${statusNorm}">${this.t(this._entityStatusLabelKey(statusNorm))}</span>
                        </div>
                    </div>
                `
                : nothing}
        `;
    }

    _onRemoveRelationship(rel) {
        if (!rel || typeof rel.relationship_id !== 'string') return;
        this._relationships.remove(rel.relationship_id);
    }

    _renderRelationshipsSection(options = {}) {
        const readOnly = options.readOnly === true;
        const titleKey = this.surface === 'page'
            ? 'entity_card.related_objects_section'
            : 'entity_modal.section_relationships';
        const addBtnClass = this.surface === 'page' ? 'btn btn-add-rel-pill' : 'btn';
        return html`
            <div class="section-title">
                <span>${this.t(titleKey)}</span>
                ${readOnly ? nothing : html`
                <button
                    type="button"
                    class=${addBtnClass}
                    @click=${() => this._toggleAddRelationship()}
                >
                    ${this._addRelOpen
                        ? this.t('entity_modal.action_cancel_add_relationship')
                        : this.t('entity_modal.action_add_relationship')}
                </button>
                `}
            </div>
            ${this._renderRelationshipsList({ readOnly })}
            ${!readOnly && this._addRelOpen ? this._renderAddRelationship() : nothing}
        `;
    }

    _relationshipTypeLabel(typeId) {
        const items = this._relationshipTypes.items;
        if (!Array.isArray(items)) {
            return typeId;
        }
        const found = items.find((rt) => rt && rt.type_id === typeId);
        if (!found) return typeId;
        return typeof found.name === 'string' && found.name.length > 0 ? found.name : typeId;
    }

    _neighborRowsFromLocalState() {
        const myId = this._effectiveEntityId();
        if (typeof myId !== 'string' || myId.length === 0) {
            return [];
        }
        const card = {
            relationships: this._relationshipsData,
            related_entities: Object.values(this._relatedById),
        };
        const edges = extractNeighborEdges(card, myId, { skipTaskNeighbors: true });
        return edges.map(({ rel, otherId, otherEntity, isOutgoing }) => {
            const isBusy = this._relationships.isBusy(rel.relationship_id);
            return {
                relationshipId: rel.relationship_id,
                otherId,
                otherEntity,
                relationshipTypeLabel: this._relationshipTypeLabel(rel.relationship_type),
                directionText: isOutgoing
                    ? this.t('neighbor_row.outgoing_from_object')
                    : this.t('neighbor_row.incoming_to_object'),
                weight: typeof rel.weight === 'number' && Number.isFinite(rel.weight) ? rel.weight : null,
                confidencePercent: relationshipConfidencePercent(rel),
                scorePercent: searchScorePercent(otherEntity),
                removeDisabled: isBusy,
            };
        });
    }

    _renderRelationshipsList(options = {}) {
        const readOnly = options.readOnly === true;
        if (this._relationshipsData.length === 0) {
            return html`<div class="empty-soft">${this.t('entity_modal.relationships_empty')}</div>`;
        }
        const rows = this._neighborRowsFromLocalState();
        return html`
            <crm-related-neighbor-rows
                .rows=${rows}
                .entityTypeRows=${this._entityTypesCatalogRows()}
                .emptyText=${this.t('entity_modal.relationships_empty')}
                .showRemove=${!readOnly}
                @entity-open=${(e) => this._onOpenRelated(e.detail.entityId)}
                @relationship-remove=${(e) => this._onRemoveRelationship({ relationship_id: e.detail.relationshipId })}
            ></crm-related-neighbor-rows>
        `;
    }

    _toggleAddRelationship() {
        this._addRelOpen = !this._addRelOpen;
        if (!this._addRelOpen) {
            this._addRelType = '';
            this._addRelDirection = 'outgoing';
            this._addRelTargetQuery = '';
            this._addRelTarget = null;
            this._addRelSearchResults = [];
            this._addRelSearching = false;
        }
    }

    _onAddRelTypeChange(event) { this._addRelType = event.target.value; }
    _onAddRelDirectionChange(event) { this._addRelDirection = event.target.value; }

    _onAddRelTargetQueryInput(event) {
        const value = event.target.value;
        this._addRelTargetQuery = value;
        this._addRelTarget = null;
        if (this._searchTimer !== null) clearTimeout(this._searchTimer);
        if (value.trim().length < 2) {
            this._addRelSearchResults = [];
            this._addRelSearching = false;
            return;
        }
        this._addRelSearching = true;
        this._searchTimer = setTimeout(() => {
            this._searchTimer = null;
            const nsEntity = this._entityData;
            const namespace = nsEntity ? nsEntity.namespace : null;
            const payload = { q: value.trim(), limit: 20 };
            if (typeof namespace === 'string' && namespace.length > 0) payload.namespace = namespace;
            this._entitySearchOp.run(payload);
        }, 250);
    }

    _onPickRelTarget(item) {
        this._addRelTarget = item;
        this._addRelSearchResults = [];
        this._addRelTargetQuery = item.name;
    }

    _canSubmitRelationship() {
        if (this._addRelBusy) return false;
        if (typeof this._addRelType !== 'string' || this._addRelType.length === 0) return false;
        if (!this._addRelTarget || typeof this._addRelTarget.entity_id !== 'string') return false;
        if (this._addRelTarget.entity_id === this._effectiveEntityId()) return false;
        return true;
    }

    _onSubmitRelationship() {
        if (!this._canSubmitRelationship()) return;
        if (!this._entityData) {
            throw new Error('CRMEntityCard._onSubmitRelationship: entity not loaded');
        }
        const myId = this._effectiveEntityId();
        const isOutgoing = this._addRelDirection === 'outgoing';
        const sourceId = isOutgoing ? myId : this._addRelTarget.entity_id;
        const targetId = isOutgoing ? this._addRelTarget.entity_id : myId;
        this._addRelBusy = true;
        this._relationships.create({
            source_entity_id: sourceId,
            target_entity_id: targetId,
            relationship_type: this._addRelType,
            namespace: this._entityData.namespace,
        });
        this._toggleAddRelationship();
        this._addRelBusy = false;
    }

    _renderAddRelationship() {
        const types = this._relationshipTypes.items;
        return html`
            <div class="rel-add">
                <div class="row">
                    <select class="form-select" .value=${this._addRelDirection} @change=${this._onAddRelDirectionChange}>
                        <option value="outgoing">${this.t('entity_modal.direction_outgoing')}</option>
                        <option value="incoming">${this.t('entity_modal.direction_incoming')}</option>
                    </select>
                    <select class="form-select" .value=${this._addRelType} @change=${this._onAddRelTypeChange}>
                        <option value="" disabled>${this.t('entity_modal.type_pick_placeholder')}</option>
                        ${types.map((rt) => html`
                            <option value=${rt.type_id}>${rt.name}</option>
                        `)}
                    </select>
                    <input
                        type="text"
                        class="form-input"
                        .value=${this._addRelTargetQuery}
                        placeholder=${this.t('entity_modal.target_search_placeholder')}
                        @input=${this._onAddRelTargetQueryInput}
                    />
                </div>
                ${this._addRelSearching
                    ? html`<div class="empty-soft">${this.t('entity_modal.searching')}</div>`
                    : nothing}
                ${this._addRelSearchResults.length > 0
                    ? html`
                        <div class="search-results">
                            ${this._addRelSearchResults.map((item) => html`
                                <button type="button" class="search-result" @click=${() => this._onPickRelTarget(item)}>
                                    <span>${item.name}</span>
                                    <span class="id">${item.entity_id}</span>
                                </button>
                            `)}
                        </div>
                    `
                    : nothing}
                <div class="footer-actions" style="border: none; padding: 0; background: transparent;">
                    <button
                        type="button"
                        class="btn btn-primary"
                        ?disabled=${!this._canSubmitRelationship()}
                        @click=${() => this._onSubmitRelationship()}
                    >
                        ${this.t('entity_modal.action_save_relationship')}
                    </button>
                </div>
            </div>
        `;
    }

    _onAttachmentInput(event) {
        const files = Array.from(event.target.files);
        const id = this._effectiveEntityId();
        for (const file of files) this._uploadAttachment(file, id);
        event.target.value = '';
    }

    _uploadAttachment(file, entityId) {
        if (!(file instanceof File)) return;
        if (typeof entityId !== 'string' || entityId.length === 0) return;
        this._uploading = true;
        this._attachmentUploadOp.run({ entity_id: entityId, file });
    }

    _onRemoveAttachment(att) {
        const id = this._effectiveEntityId();
        if (!att || typeof att.document_id !== 'string') return;
        this._attachmentDeleteOp.run({ entity_id: id, attachment_id: att.document_id });
    }

    _shouldShowAttachmentsChrome() {
        if (this.layoutVariant !== 'full') return false;
        if (this.panelMode === MODE_CREATE) return false;
        const id = this._effectiveEntityId();
        return typeof id === 'string' && id.length > 0;
    }

    _mapEntityCardAttachmentItems() {
        return this._attachmentsData.map((item) => {
            const attachmentId = typeof item.document_id === 'string' ? item.document_id : '';
            const filename = typeof item.filename === 'string' && item.filename.length > 0
                ? item.filename
                : attachmentId;
            const metadata = item && typeof item.metadata === 'object' && item.metadata !== null
                ? item.metadata
                : {};
            const contentType = typeof metadata.content_type === 'string' ? metadata.content_type : '';
            const sizeBytes = typeof item.size_bytes === 'number'
                ? item.size_bytes
                : (typeof metadata.size_bytes === 'number'
                    ? metadata.size_bytes
                    : (typeof metadata.file_size === 'number' ? metadata.file_size : 0));
            const downloadUrl = typeof item.download_url === 'string' && item.download_url.length > 0
                ? item.download_url
                : (typeof item.url === 'string' ? item.url : '');
            return {
                id: attachmentId,
                filename,
                sizeBytes,
                status: typeof item.status === 'string' ? item.status : '',
                downloadUrl,
                contentType,
            };
        });
    }

    _entityAttachmentMode() {
        return this.panelMode === MODE_EDIT ? 'edit' : 'view';
    }

    _openEntityAttachmentsPopover(mode) {
        this._cancelEntityAttachmentsPopoverClose();
        this._attachmentsPopoverMode = mode;
        this._attachmentsPopoverOpen = true;
    }

    _closeEntityAttachmentsPopover() {
        this._cancelEntityAttachmentsPopoverClose();
        this._attachmentsPopoverOpen = false;
        this._attachmentsPopoverMode = '';
    }

    _scheduleEntityAttachmentsPopoverClose() {
        this._cancelEntityAttachmentsPopoverClose();
        this._attachmentsPopoverCloseTimer = setTimeout(() => {
            this._attachmentsPopoverCloseTimer = null;
            this._closeEntityAttachmentsPopover();
        }, 140);
    }

    _cancelEntityAttachmentsPopoverClose() {
        if (this._attachmentsPopoverCloseTimer === null) return;
        clearTimeout(this._attachmentsPopoverCloseTimer);
        this._attachmentsPopoverCloseTimer = null;
    }

    _onEntityAttachmentsFocusOut(event) {
        const next = event.relatedTarget;
        if (next instanceof Node && event.currentTarget.contains(next)) return;
        this._closeEntityAttachmentsPopover();
    }

    _onEntityAttachmentTriggerKeydown(event) {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        this._triggerEntityAttachmentFileInput();
    }

    _triggerEntityAttachmentFileInput() {
        const root = this.renderRoot;
        const input = root.querySelector('[data-role="entity-card-attachment-input"]');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('CRMEntityCard: attachment file input missing');
        }
        input.click();
    }

    _onEntityAttachmentHeaderClick(mode, isOpen) {
        this._triggerEntityAttachmentFileInput();
        if (isOpen) {
            this._closeEntityAttachmentsPopover();
            return;
        }
        this._openEntityAttachmentsPopover(mode);
    }

    _onRemoveAttachmentById(attachmentId) {
        if (typeof attachmentId !== 'string' || attachmentId.length === 0) return;
        this._onRemoveAttachment({ document_id: attachmentId });
    }

    _renderEntityAttachmentsPopover(mode) {
        const mapped = this._mapEntityCardAttachmentItems();
        const editMode = mode === 'edit';
        return html`
            <div
                class="attachments-popover"
                role="menu"
                @mouseenter=${() => this._cancelEntityAttachmentsPopoverClose()}
                @mouseleave=${() => this._scheduleEntityAttachmentsPopoverClose()}
            >
                ${mapped.length === 0
                    ? html`<div class="attachments-popover-empty">${this.t('note_view.attachments_empty_popover')}</div>`
                    : mapped.map((item) => {
                        const metaParts = [];
                        const bytes = _entityCardFormatBytes(item.sizeBytes);
                        if (bytes.length > 0) metaParts.push(bytes);
                        if (item.status.length > 0) metaParts.push(item.status);
                        const metaText = metaParts.join(' · ');
                        const iconName = _entityCardAttachmentIcon(item.filename, item.contentType);
                        return html`
                            <div class="attachments-popover-row">
                                <platform-icon name=${iconName} size="16"></platform-icon>
                                <div class="attachments-popover-info">
                                    <p class="attachments-popover-name">${item.filename}</p>
                                    <p class="attachments-popover-meta">${metaText}</p>
                                </div>
                                <div class="attachments-popover-actions">
                                    ${item.downloadUrl.length > 0 ? html`
                                        <a
                                            class="attachment-action-btn"
                                            href=${item.downloadUrl}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            download=${item.filename}
                                            title=${this.t('note_view.download')}
                                        >
                                            <platform-icon name="import" size="14"></platform-icon>
                                        </a>
                                    ` : nothing}
                                    ${item.id.length > 0 ? html`
                                        <button
                                            type="button"
                                            class="attachment-action-btn"
                                            title=${editMode
                                                ? this.t('note_edit.attachment_remove')
                                                : this.t('note_view.attachment_remove')}
                                            @click=${() => this._onRemoveAttachmentById(item.id)}
                                        >
                                            <platform-icon name="trash" size="14"></platform-icon>
                                        </button>
                                    ` : nothing}
                                </div>
                            </div>
                        `;
                    })}
            </div>
        `;
    }

    _renderEntityAttachmentsHeader(opts = undefined) {
        const compact = opts && opts.compact === true;
        const mode = this._entityAttachmentMode();
        const editMode = mode === 'edit';
        const isOpen = this._attachmentsPopoverOpen && this._attachmentsPopoverMode === mode;
        const count = this._mapEntityCardAttachmentItems().length;
        const buttonTitle = editMode ? this.t('note_edit.attachment_add') : this.t('note_view.action_attachments');
        const onClick = () => this._onEntityAttachmentHeaderClick(mode, isOpen);
        const btnClass = compact ? 'round-btn round-btn--compact' : 'round-btn';
        const clipSize = compact ? '16' : '20';
        return html`
            <input
                type="file"
                multiple
                class="visually-hidden-file-input"
                data-role="entity-card-attachment-input"
                id=${this._entityAttachmentInputId}
                @change=${this._onAttachmentInput}
            />
            <div
                class="attachments-menu"
                @mouseenter=${() => this._openEntityAttachmentsPopover(mode)}
                @mouseleave=${() => this._scheduleEntityAttachmentsPopoverClose()}
                @focusin=${() => this._openEntityAttachmentsPopover(mode)}
                @focusout=${this._onEntityAttachmentsFocusOut}
            >
                ${editMode
                    ? html`
                        <label
                            class=${btnClass}
                            title=${buttonTitle}
                            for=${this._entityAttachmentInputId}
                            tabindex="0"
                            @click=${onClick}
                            @keydown=${this._onEntityAttachmentTriggerKeydown}
                        >
                            <platform-icon name="paperclip" size=${clipSize}></platform-icon>
                            <span class="attachments-badge">${count}</span>
                        </label>
                    `
                    : html`
                        <button
                            type="button"
                            class=${btnClass}
                            title=${buttonTitle}
                            aria-haspopup="menu"
                            aria-expanded=${String(isOpen)}
                            @click=${onClick}
                        >
                            <platform-icon name="paperclip" size=${clipSize}></platform-icon>
                            <span class="attachments-badge">${count}</span>
                        </button>
                    `}
                ${isOpen ? this._renderEntityAttachmentsPopover(mode) : nothing}
            </div>
        `;
    }

    _onEditNavigate(entity) {
        this.navigate('entity', { itemId: entity.entity_id }, { search: '?edit=1' });
    }

    _onShare(entity) {
        this.openModal('crm.share', { entityId: entity.entity_id });
    }

    _onAccessRequest(entity) {
        this.openModal('crm.access_request', { entityId: entity.entity_id });
    }

    _onToggleGrants(entityId) {
        this._grantsExpanded = !this._grantsExpanded;
        if (this._grantsExpanded) {
            this._grantsOp.run({ entity_id: entityId });
        }
    }

    _onToggleRelated(entityId) {
        this._relatedExpanded = !this._relatedExpanded;
        if (this._relatedExpanded) {
            this._relatedOp.run({ entity_id: entityId });
        }
    }

    _onOpenRelated(relatedId) {
        this.dispatch('crm/entity_card/related_selected', { entity_id: relatedId }, { source: 'local' });
    }

    _renderRelated() {
        if (this._relatedOp.busy) {
            return html`<div class="empty-soft"><glass-spinner size="sm"></glass-spinner></div>`;
        }
        const result = this._relatedOp.lastResult;
        const items = result && Array.isArray(result.items) ? result.items : [];
        return html`
            <crm-related-entity-cards
                .entities=${items}
                .entityTypeRows=${this._entityTypesCatalogRows()}
                .emptyText=${this.t('entity_card.requests_empty')}
                @entity-open=${(e) => this._onOpenRelated(e.detail.entityId)}
            ></crm-related-entity-cards>
        `;
    }

    _renderViewBodyPage(entity) {
        const type = this._selectedType();
        const typeIcon = type && typeof type.icon === 'string' && type.icon.length > 0 ? type.icon : 'folder';
        const nameValue = typeof entity.name === 'string' ? entity.name : '';
        const descRaw = typeof entity.description === 'string' ? entity.description : '';
        const descTrimmed = descRaw.trim();
        const statusRaw = entity.status;
        const statusNorm = typeof statusRaw === 'string' ? statusRaw.trim() : '';
        const showStatusPill = statusNorm.length > 0 && ENTITY_STATUS_VALUES.includes(statusNorm);
        const showRelAtt = this.layoutVariant === 'full';

        return html`
            <div class="scroll">
                <div class="edit-page-sheet">
                    <div class="entity-card-layout-container ${this.compactStack ? 'entity-card-layout-container--force-stack' : ''}">
                    <div class="edit-two-col">
                        <aside class="edit-aside">
                            <div class="edit-avatar-wrap">
                                <platform-icon name=${typeIcon} size="140"></platform-icon>
                            </div>
                        </aside>
                        <div class="edit-fields">
                            <div class="edit-fields-heading-row">
                                <h2 class="edit-fields-heading">${this.t('entity_card.object_data_section')}</h2>
                                ${this._shouldShowAttachmentsChrome()
                                    ? html`<div class="edit-fields-heading-actions">${this._renderEntityAttachmentsHeader({ compact: true })}</div>`
                                    : nothing}
                            </div>
                            <div class="edit-name-status-row">
                                <div class="field-pill">
                                    <span class="field-pill-label">${this.t('entity_modal.label_name')}</span>
                                    <div class="field-pill-readonly-text">${nameValue}</div>
                                </div>
                                <div class="field-pill">
                                    <span class="field-pill-label">${this.t('entity_modal.label_status')}</span>
                                    <div class="field-pill-readonly-inline">
                                        ${showStatusPill
                                            ? html`<span class="status-badge ${statusNorm}">${this.t(this._entityStatusLabelKey(statusNorm))}</span>`
                                            : html`<span class="field-pill-readonly-muted">${this.t('entity_card.view_status_empty')}</span>`}
                                    </div>
                                </div>
                            </div>
                            <div class="field-pill field-pill--textarea">
                                <span class="field-pill-label">${this.t('entity_modal.label_description')}</span>
                                ${descTrimmed.length > 0
                                    ? html`<div class="field-pill-readonly-text">${descRaw}</div>`
                                    : html`<p class="field-pill-readonly-muted">${this.t('entity_detail_page.empty_description')}</p>`}
                            </div>
                            ${this._renderTagsSection({ pill: true })}
                            <div class="edit-attrs-block">
                                <h3 class="edit-subheading">${this.t('entity_modal.label_attributes')}</h3>
                                <div class="edit-attrs-grid">${this._renderAttributesSection()}</div>
                            </div>
                            ${showRelAtt
                                ? html`
                                    <div class="edit-related-block section">
                                        ${this._renderRelationshipsSection({ readOnly: true })}
                                    </div>
                                `
                                : nothing}
                        </div>
                    </div>
                    </div>
                </div>
            </div>
        `;
    }

    _renderViewBody() {
        const entity = this._resolveEntity();
        if (!entity) {
            if (this.entityId && this._entities.loading) {
                return html`<div class="loading-block"><glass-spinner></glass-spinner></div>`;
            }
            return html`
                <div class="empty">
                    <platform-icon name="folder" size="48"></platform-icon>
                    <div class="empty-title">${this.t('entity_card.empty_pick_title')}</div>
                    <div class="empty-subtitle">${this.t('entity_card.empty_pick_subtitle')}</div>
                </div>
            `;
        }

        if (this.surface === 'page') {
            return this._renderViewBodyPage(entity);
        }

        const nameValue = typeof entity.name === 'string' ? entity.name : '';
        const descValue = typeof entity.description === 'string' ? entity.description : '';

        const showCollapsibles = this.layoutVariant === 'full' && this.surface === 'sidebar';

        const tags = Array.isArray(entity.tags) ? entity.tags : [];

        return html`
            <div class="scroll">
                ${this._renderTypeBadge()}
                ${this._renderHero(entity, nameValue, descValue)}
                <div class="sheet-block">
                    <div class="sheet-cell-head">${this.t('entity_modal.label_attributes')}</div>
                    <div class="sheet-cell-body">${this._renderAttributesSection()}</div>
                </div>
                ${tags.length > 0
                    ? html`
                        <div class="sheet-block">
                            <div class="sheet-cell-head">${this.t('entity_modal.label_tags')}</div>
                            <div class="sheet-cell-body">${this._renderTagsSection({ omitLabel: true })}</div>
                        </div>
                    `
                    : nothing}
                ${this.showEntityActions ? html`
                <div class="actions-bar">
                    ${this._shouldShowAttachmentsChrome()
                        ? html`<div class="actions-bar-lead">${this._renderEntityAttachmentsHeader()}</div>`
                        : nothing}
                    <button class="btn btn-primary" type="button" @click=${() => this._onEditNavigate(entity)}>
                        <platform-icon name="edit" size="14"></platform-icon>
                        ${this.t('edit', {}, 'common')}
                    </button>
                    <button class="btn" type="button" @click=${() => this._onShare(entity)}>
                        <platform-icon name="share" size="14"></platform-icon>
                        ${this.t('grants.share_user')}
                    </button>
                    <button class="btn" type="button" @click=${() => this._onAccessRequest(entity)}>
                        <platform-icon name="lock" size="14"></platform-icon>
                        ${this.t('entity_card.request_access_tooltip')}
                    </button>
                </div>
                ` : nothing}
                ${showCollapsibles ? html`
                    <div class="collapsible-header" @click=${() => this._onToggleRelated(entity.entity_id)}>
                        <span class="section-title text-only" style="border: none;">${this.t('entity_card.related_entities')}</span>
                        <platform-icon name=${this._relatedExpanded ? 'chevron-up' : 'chevron-down'} size="14"></platform-icon>
                    </div>
                    ${this._relatedExpanded ? html`<div class="collapsible-content">${this._renderRelated()}</div>` : nothing}
                    <div class="collapsible-header" @click=${() => this._onToggleGrants(entity.entity_id)}>
                        <span class="section-title text-only" style="border: none;">${this.t('grants.section_title')}</span>
                        <platform-icon name=${this._grantsExpanded ? 'chevron-up' : 'chevron-down'} size="14"></platform-icon>
                    </div>
                    ${this._grantsExpanded
                        ? html`
                            <div class="collapsible-content">
                                ${this._grantsOp.busy
                                    ? html`<div class="empty-soft"><glass-spinner size="sm"></glass-spinner></div>`
                                    : html`<div class="empty-soft">${this.t('grants.loading')}</div>`}
                            </div>
                        `
                        : nothing}
                ` : nothing}
            </div>
        `;
    }

    _renderCreateBody() {
        if (this._step === 'type') {
            return html`<div class="scroll">${this._renderTypeStep()}</div>`;
        }
        const type = this._selectedType();
        if (!type) {
            return html`<div class="scroll"><div class="empty-hint">${this.t('entity_modal.type_missing')}</div></div>`;
        }
        const draft = this._createForm.draft;
        const syntheticEntity = {
            entity_type: draft.entity_type,
            entity_subtype: '',
            namespace: draft.namespace,
            status: '',
        };
        return html`
            <form class="scroll form-grid" @submit=${(e) => { e.preventDefault(); this._performSave(); }}>
                ${this._renderTypeBadge()}
                ${this._renderHero(syntheticEntity, draft.name, draft.description)}
                <div class="sheet-block">
                    <div class="sheet-cell-head">${this.t('entity_modal.label_attributes')}</div>
                    <div class="sheet-cell-body">${this._renderAttributesSection()}</div>
                </div>
                <div class="sheet-block">
                    <div class="sheet-cell-head">${this.t('entity_modal.label_tags')}</div>
                    <div class="sheet-cell-body">${this._renderTagsSection({ omitLabel: true })}</div>
                </div>
            </form>
        `;
    }

    _renderEditBodyPage(draft, showRelAtt) {
        const entity = this._entityData;
        const type = this._selectedType();
        const templateName = type && typeof type.name === 'string' && type.name.length > 0
            ? type.name
            : entity.entity_type;
        const typeIcon = type && typeof type.icon === 'string' && type.icon.length > 0 ? type.icon : 'folder';
        const form = this._editForm;
        const has_name = typeof draft.name === 'string' && draft.name.trim().length > 0;
        const disabled = this._loadingCard || form.submitting || !has_name;
        return html`
            <form class="scroll" @submit=${(e) => { e.preventDefault(); this._performSave(); }}>
                <div class="edit-page-sheet">
                    ${this.hostToolbar
                        ? nothing
                        : html`
                        <div class="edit-page-toolbar">
                            <h1 class="edit-page-title">${this.t('entity_card.edit_object_title')}</h1>
                            <div class="edit-page-toolbar-right">
                                <div class="edit-template-box">
                                    <span class="edit-template-label">${this.t('entity_card.object_template_label')}</span>
                                    <span class="edit-template-value">${templateName}</span>
                                </div>
                                <button
                                    type="button"
                                    class="btn-circle-danger"
                                    title=${this.t('entity_card.delete_object_tooltip')}
                                    @click=${() => this._onEditDelete()}
                                >
                                    <platform-icon name="trash" size="18"></platform-icon>
                                </button>
                                <button type="button" class="btn-pill-ghost" @click=${() => this._onFooterCancel()}>
                                    ${this.t('entity_modal.action_cancel')}
                                </button>
                                <button type="submit" class="btn-pill-primary" ?disabled=${disabled}>
                                    ${form.submitting
                                        ? this.t('entity_modal.action_saving')
                                        : this.t('entity_modal.action_save')}
                                </button>
                            </div>
                        </div>
                    `}
                    <div class="entity-card-layout-container ${this.compactStack ? 'entity-card-layout-container--force-stack' : ''}">
                    <div class="edit-two-col">
                        <aside class="edit-aside">
                            <div class="edit-avatar-wrap">
                                <platform-icon name=${typeIcon} size="140"></platform-icon>
                            </div>
                        </aside>
                        <div class="edit-fields">
                            <div class="edit-fields-heading-row">
                                <h2 class="edit-fields-heading">${this.t('entity_card.object_data_section')}</h2>
                                ${this._shouldShowAttachmentsChrome()
                                    ? html`<div class="edit-fields-heading-actions">${this._renderEntityAttachmentsHeader({ compact: true })}</div>`
                                    : nothing}
                            </div>
                            <div class="edit-name-status-row">
                                <label class="field-pill">
                                    <span class="field-pill-label">${this.t('entity_modal.label_name')}</span>
                                    <input
                                        type="text"
                                        class="field-pill-input"
                                        autocomplete="off"
                                        spellcheck="false"
                                        placeholder=${this.t('entity_modal.name_placeholder')}
                                        .value=${draft.name}
                                        @input=${this._onNameInput}
                                    />
                                    ${this._renderFieldError('name')}
                                </label>
                                <label class="field-pill">
                                    <span class="field-pill-label">${this.t('entity_modal.label_status')}</span>
                                    <select class="field-pill-select" .value=${draft.status} @change=${this._onStatusInput}>
                                        ${ENTITY_STATUS_VALUES.map((value) => html`
                                            <option value=${value}>${this.t(`entities.status.${value}`)}</option>
                                        `)}
                                    </select>
                                </label>
                            </div>
                            <label class="field-pill field-pill--textarea">
                                <span class="field-pill-label">${this.t('entity_modal.label_description')}</span>
                                <textarea
                                    class="field-pill-textarea"
                                    rows="5"
                                    placeholder=${this.t('entity_modal.description_placeholder')}
                                    .value=${draft.description}
                                    @input=${this._onDescriptionInput}
                                ></textarea>
                                ${this._renderFieldError('description')}
                            </label>
                            ${this._renderTagsSection({ pill: true })}
                            <div class="edit-attrs-block">
                                <h3 class="edit-subheading">${this.t('entity_modal.label_attributes')}</h3>
                                <div class="edit-attrs-grid">${this._renderAttributesSection()}</div>
                            </div>
                            ${showRelAtt
                                ? html`
                                    <div class="edit-related-block section">
                                        ${this._renderRelationshipsSection()}
                                    </div>
                                `
                                : nothing}
                        </div>
                    </div>
                    </div>
                </div>
            </form>
        `;
    }

    _renderEditBody() {
        if (this._loadingCard && !this._entityData) {
            return html`<div class="loading-block"><glass-spinner></glass-spinner></div>`;
        }
        if (this._loadError && !this._entityData) {
            return html`<div class="error-block">${this._loadError}</div>`;
        }
        if (!this._entityData) {
            return html`<div class="loading-block"><glass-spinner></glass-spinner></div>`;
        }
        const draft = this._editForm.draft;
        const showRelAtt = this.layoutVariant === 'full';
        if (this.surface === 'page') {
            return this._renderEditBodyPage(draft, showRelAtt);
        }
        return html`
            <form class="scroll form-grid" @submit=${(e) => { e.preventDefault(); this._performSave(); }}>
                ${this._renderTypeBadge()}
                ${this._renderHero(this._entityData, draft.name, draft.description)}
                <div class="sheet-block">
                    <div class="sheet-cell-head">${this.t('entity_modal.label_status')}</div>
                    <div class="sheet-cell-body">
                        <select class="form-select" .value=${draft.status} @change=${this._onStatusInput}>
                            ${ENTITY_STATUS_VALUES.map((value) => html`
                                <option value=${value}>${this.t(`entities.status.${value}`)}</option>
                            `)}
                        </select>
                    </div>
                </div>
                <div class="sheet-block">
                    <div class="sheet-cell-head">${this.t('entity_modal.label_attributes')}</div>
                    <div class="sheet-cell-body">${this._renderAttributesSection()}</div>
                </div>
                <div class="sheet-block">
                    <div class="sheet-cell-head">${this.t('entity_modal.label_tags')}</div>
                    <div class="sheet-cell-body">${this._renderTagsSection({ omitLabel: true })}</div>
                </div>
                ${showRelAtt ? html`
                    <div class="section">${this._renderRelationshipsSection()}</div>
                ` : nothing}
            </form>
        `;
    }

    _renderFooter() {
        if (this.panelMode === MODE_VIEW) return nothing;
        if (this.panelMode === MODE_EDIT && this.surface === 'page') {
            return nothing;
        }
        if (this.panelMode === MODE_CREATE && this._step === 'type') {
            return html`
                <div class="footer-actions">
                    <button type="button" class="btn" @click=${() => this.emit('create-cancelled', {})}>
                        ${this.t('entity_modal.action_cancel')}
                    </button>
                </div>
            `;
        }
        const form = this._activeForm();
        const draft = form.draft;
        const has_name = typeof draft.name === 'string' && draft.name.trim().length > 0;
        const disabled = (this.panelMode === MODE_CREATE ? false : this._loadingCard) || form.submitting || !has_name;
        const submitting = form.submitting;
        return html`
            <div class="footer-actions">
                <button type="button" class="btn" @click=${() => this._onFooterCancel()}>
                    ${this.t('entity_modal.action_cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${disabled}
                    @click=${() => this._performSave()}
                >
                    ${submitting
                        ? this.t('entity_modal.action_saving')
                        : this.panelMode === MODE_CREATE
                            ? this.t('entity_modal.action_create')
                            : this.t('entity_modal.action_save')}
                </button>
            </div>
        `;
    }

    _onEditDelete() {
        if (!this._entityData || typeof this._entityData.entity_id !== 'string') {
            throw new Error('CRMEntityCard._onEditDelete: entity not loaded');
        }
        this.openModal('crm.entity_delete', {
            entityId: this._entityData.entity_id,
            redirectRoute: 'entities',
        });
    }

    _onFooterCancel() {
        if (this.panelMode === MODE_CREATE) {
            this.emit('create-cancelled', {});
            return;
        }
        this.emit('edit-cancelled', {});
    }

    render() {
        if (this.panelMode === MODE_VIEW) {
            return html`${this._renderViewBody()}`;
        }
        if (this.panelMode === MODE_CREATE) {
            return html`
                ${this._renderCreateBody()}
                ${this._renderFooter()}
            `;
        }
        return html`
            ${this._renderEditBody()}
            ${this._renderFooter()}
        `;
    }
}

customElements.define('crm-entity-card', CRMEntityCard);
