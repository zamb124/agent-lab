/**
 * WorktrackerDetailContent — title, description, resolution, state header.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { worktrackerDetailContentStyles } from '../styles/worktracker-detail.styles.js';
import { truncateWorkItemId } from '../utils/work-item-detail-shared.js';
import { buildWorkItemFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import './worktracker-state-pill.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/prompt-editor.js';
import '@platform/lib/components/platform-file-attachments.js';

export class WorktrackerDetailContent extends PlatformElement {
    static i18nNamespace = 'worktracker';

    static properties = {
        layout: { type: String },
        state: { type: String },
        stateLabel: { type: String, attribute: 'state-label' },
        titleDraft: { type: String, attribute: 'title-draft' },
        descriptionDraft: { type: String, attribute: 'description-draft' },
        resolutionText: { type: String, attribute: 'resolution-text' },
        resolutionFiles: { type: Array, attribute: false },
        attachments: { type: Array, attribute: false },
        descriptionVariables: { type: Object, attribute: false },
        workItemId: { type: String, attribute: 'work-item-id' },
        loading: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        worktrackerDetailContentStyles,
        css`
            :host {
                display: block;
                min-width: 0;
                height: auto;
            }
        `,
    ];

    constructor() {
        super();
        this.layout = 'page';
        this.state = 'open';
        this.stateLabel = '';
        this.titleDraft = '';
        this.descriptionDraft = '';
        this.resolutionText = '';
        this.resolutionFiles = [];
        this.attachments = [];
        this.descriptionVariables = {};
        this.workItemId = '';
        this.loading = false;
    }

    _emitTitleChange(event) {
        const value = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this.emit('wt-title-change', { value });
    }

    _emitDescriptionChange(event) {
        const value = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this.emit('wt-description-change', { value });
    }

    _descriptionMinHeight() {
        return this.layout === 'page' ? 160 : 120;
    }

    _shortId() {
        if (typeof this.workItemId !== 'string' || this.workItemId.length === 0) {
            return '';
        }
        return truncateWorkItemId(this.workItemId);
    }

    _copyId() {
        if (typeof this.workItemId !== 'string' || this.workItemId.length === 0) {
            return;
        }
        this.copyToClipboard(this.workItemId, {
            success_i18n_key: 'detail_page.id_copied',
            error_i18n_key: 'detail_page.id_copy_failed',
        });
    }

    _uploadSpecJson() {
        return buildWorkItemFileCreateSpecJson({ workItemId: this.workItemId });
    }

    render() {
        const titlePlaceholder = this.t('detail_panel.label_title');
        const descPlaceholder = this.layout === 'page'
            ? this.t('detail_page.description_placeholder')
            : this.t('detail_panel.label_description');
        const state = typeof this.state === 'string' && this.state.length > 0 ? this.state : 'open';
        const pillLabel = typeof this.stateLabel === 'string' && this.stateLabel.length > 0
            ? this.stateLabel
            : '';

        const mainClass = this.layout === 'page' ? 'wt-detail-main layout-page' : 'wt-detail-main layout-panel';

        return html`
            <div class=${mainClass}>
                ${this.loading ? html`<div class="wt-loading">${this.t('detail_panel.loading')}</div>` : nothing}
                ${this.layout === 'panel' ? html`
                    <div class="wt-state-header">
                        <worktracker-state-pill
                            .state=${state}
                            .label=${pillLabel}
                        ></worktracker-state-pill>
                    </div>
                ` : nothing}
                <div class="wt-title-block">
                    <platform-field
                        class="wt-title-field"
                        type="string"
                        mode="edit"
                        pill-embed
                        pill-density=${this.layout === 'page' ? 'default' : 'dense'}
                        .label=${''}
                        .placeholder=${titlePlaceholder}
                        .value=${this.titleDraft}
                        @change=${(e) => this._emitTitleChange(e)}
                        @blur=${() => this.emit('wt-title-blur', null)}
                    ></platform-field>
                    ${this.layout === 'page' ? html`
                        <button
                            type="button"
                            class="wt-id-chip"
                            title=${this.workItemId}
                            @click=${() => this._copyId()}
                        >
                            ${this._shortId()}
                        </button>
                    ` : nothing}
                </div>
                <prompt-editor
                    class="wt-desc-editor"
                    variant="embed"
                    .value=${this.descriptionDraft}
                    .variables=${this.descriptionVariables}
                    .label=${this.t('detail_panel.label_description')}
                    .placeholder=${descPlaceholder}
                    ?show-header=${false}
                    ?show-hint=${false}
                    min-height=${this._descriptionMinHeight()}
                    @change=${(e) => this._emitDescriptionChange(e)}
                    @blur=${() => this.emit('wt-description-blur', null)}
                ></prompt-editor>
                <section class="wt-attachments-section">
                    <h4 class="wt-section-label">${this.t('detail_page.section_attachments')}</h4>
                    <platform-file-attachments
                        .files=${Array.isArray(this.attachments) ? this.attachments : []}
                        .uploadSpec=${this._uploadSpecJson()}
                        open-source="worktracker_task_attachments"
                        @files-change=${(e) => {
                            const files = e.detail && Array.isArray(e.detail.files) ? e.detail.files : [];
                            this.emit('wt-attachments-change', { files });
                        }}
                    ></platform-file-attachments>
                </section>
                ${typeof this.resolutionText === 'string' && this.resolutionText.length > 0 ? html`
                    <section class="wt-resolution">
                        <div class="wt-resolution-label">${this.t('detail_page.resolution')}</div>
                        <div class="wt-resolution-text">${this.resolutionText}</div>
                        ${Array.isArray(this.resolutionFiles) && this.resolutionFiles.length > 0 ? html`
                            <platform-file-attachments
                                readonly
                                .files=${this.resolutionFiles}
                                open-source="worktracker_resolution_files"
                            ></platform-file-attachments>
                        ` : nothing}
                    </section>
                ` : nothing}
            </div>
        `;
    }
}

customElements.define('worktracker-detail-content', WorktrackerDetailContent);
