/**
 * GeoFeatureAdminModal — подтверждение админ-действия с карточки карты.
 *
 * openModal('geo.feature_admin', { action, entity, osmId, title, onApply }):
 *   action 'feature-suppress' → geo/features/suppress (тумбстоун объекта);
 *   action 'edge-close' → geo/edges/close (маска режимов по всем рёбрам way).
 * Для edge-close — чипы режимов движения; для suppress — только reason.
 */
import { html, css } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import type { OpControllerOf } from '@platform/lib/base/use-resource.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/events/resources/geo-admin.resource.js';
import type {
    geoEdgeCloseOp,
    geoFeatureSuppressOp,
} from '@platform/lib/events/resources/geo-admin.resource.js';

export type FeatureAdminAction = 'feature-suppress' | 'edge-close';

const ALL_MODES = ['car', 'foot', 'bike', 'scooter'] as const;
type RouteMode = (typeof ALL_MODES)[number];

export class GeoFeatureAdminModal extends PlatformFormModal {
    static modalKind = 'geo.feature_admin';
    static i18nNamespace = 'geo';

    declare action: FeatureAdminAction;
    declare entity: string;
    declare osmId: number;
    declare featureTitle: string;
    declare onApply: (() => void) | null;

    declare _reason: string;
    declare _modes: Set<RouteMode>;

    private _suppressCtl: OpControllerOf<typeof geoFeatureSuppressOp> | null = null;
    private _closeCtl: OpControllerOf<typeof geoEdgeCloseOp> | null = null;

    static override properties: PropertyDeclarations = {
        action: { type: String, attribute: false },
        entity: { type: String, attribute: false },
        osmId: { type: Number, attribute: false },
        featureTitle: { type: String, attribute: false },
        onApply: { attribute: false },
        _reason: { state: true },
        _modes: { state: true },
    };

    constructor() {
        super();
        this.size = 'md';
        this.action = 'feature-suppress';
        this.entity = '';
        this.osmId = 0;
        this.featureTitle = '';
        this.onApply = null;
        this._reason = '';
        this._modes = new Set(ALL_MODES);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._suppressCtl = this.useOp('geo/features_suppress');
        this._closeCtl = this.useOp('geo/edges_close');
        this.title = this.t(
            this.action === 'edge-close'
                ? 'feature_admin.title_close'
                : 'feature_admin.title_hide',
        );
    }

    private _toggleMode(mode: RouteMode): void {
        const next = new Set(this._modes);
        if (next.has(mode)) next.delete(mode);
        else next.add(mode);
        this._modes = next;
        this.isDirty = true;
    }

    override validateForm(): Record<string, string> {
        const errors: Record<string, string> = {};
        if (this.action === 'edge-close' && this._modes.size === 0) {
            errors.modes = this.t('feature_admin.err_modes');
        }
        return errors;
    }

    override async handleSubmit(): Promise<void> {
        const reason = this._reason.trim();
        if (this.action === 'edge-close') {
            await this._closeCtl?.run({
                osm_way_id: this.osmId,
                modes: ALL_MODES.filter((m) => this._modes.has(m)),
                reason,
            });
        } else {
            await this._suppressCtl?.run({
                entity: this.entity,
                osm_id: this.osmId,
                reason,
            });
        }
        this.onApply?.();
        this.closeAfterSave();
    }

    override renderBody(): TemplateResult {
        const entityLabel = this.t(`feature_admin.entity_${this.entity || 'edge'}`);
        return html`
            <form @submit=${this._onSubmit}>
                <div class="target">
                    <span class="target-entity">${entityLabel}</span>
                    <span class="target-name">${this.featureTitle}</span>
                    <span class="target-id">#${this.osmId}</span>
                </div>
                ${this.action === 'edge-close'
                    ? html`
                          <div class="modes">
                              ${ALL_MODES.map(
                                  (mode) => html`
                                      <button
                                          type="button"
                                          class="mode-chip ${this._modes.has(mode) ? 'active' : ''}"
                                          @click=${() => this._toggleMode(mode)}
                                      >
                                          ${this.t(`feature_admin.mode_${mode}`)}
                                      </button>
                                  `,
                              )}
                          </div>
                          ${this.fieldError('modes')
                              ? html`<div class="field-err">${this.fieldError('modes')}</div>`
                              : ''}
                      `
                    : ''}
                <div class="form-group">
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('feature_admin.reason')}
                        .value=${this._reason}
                        @change=${(e: CustomEvent) => {
                            this._reason = String(e.detail?.value ?? '');
                            this.isDirty = true;
                        }}
                    ></platform-field>
                </div>
                <div class="warn">${this.t('feature_admin.persist_hint')}</div>
            </form>
        `;
    }

    override renderFooter(): TemplateResult {
        const canSubmit =
            (this.action !== 'edge-close' || this._modes.size > 0) && !this.loading;
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('feature_admin.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-danger"
                    ?disabled=${!canSubmit}
                    @click=${() => this._performSave()}
                >
                    ${this.loading
                        ? this.t('feature_admin.applying')
                        : this.t(
                              this.action === 'edge-close'
                                  ? 'feature_admin.submit_close'
                                  : 'feature_admin.submit_hide',
                          )}
                </button>
            </div>
        `;
    }

    static override styles = [
        PlatformFormModal.styles,
        css`
            .target {
                display: flex;
                align-items: baseline;
                gap: var(--space-2);
                padding: var(--space-3);
                margin-bottom: var(--space-4);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
            }
            .target-entity {
                font-size: var(--text-xs);
                text-transform: uppercase;
                color: var(--text-tertiary);
                font-weight: var(--font-medium);
            }
            .target-name {
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .target-id { color: var(--text-tertiary); font-size: var(--text-xs); }
            .modes {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-bottom: var(--space-4);
            }
            .mode-chip {
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-full, 999px);
                border: 1px solid var(--glass-border-strong, rgba(255, 255, 255, 0.2));
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: background 0.15s ease, color 0.15s ease;
            }
            .mode-chip.active {
                background: var(--accent);
                border-color: var(--accent);
                color: var(--accent-contrast, #fff);
            }
            .field-err { color: var(--danger, #ef4444); font-size: var(--text-xs); margin-bottom: var(--space-2); }
            .warn { font-size: var(--text-xs); color: var(--text-tertiary); margin-top: var(--space-3); }
        `,
    ];
}

customElements.define('geo-feature-admin-modal', GeoFeatureAdminModal);
registerModalKind(GeoFeatureAdminModal.modalKind, 'geo-feature-admin-modal');

declare global {
    interface HTMLElementTagNameMap {
        'geo-feature-admin-modal': GeoFeatureAdminModal;
    }
}
