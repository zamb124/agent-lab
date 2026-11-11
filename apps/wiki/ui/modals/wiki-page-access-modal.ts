/**
 * Доступ к странице: публикация, участники и публичная ссылка.
 *
 * Ограничение доступа задаётся флагом `company_visible` на самой странице:
 * `false` — видят только явные участники (FGA `viewer`/`editor` + `owner`),
 * `true` — видна всей компании. Переключатель «только участники» просто
 * патчит `company_visible`; владелец страницы уже имеет `can_admin` через
 * FGA `owner` relation, добавлять его отдельным участником не нужно.
 *
 * Адрес публичной ссылки в базе лежит хешем, поэтому показать его можно только
 * сразу после выпуска. Позже остаётся перевыпуск с новым адресом.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';

interface WikiAccessState {
    members?: { user_id?: string; relation?: string; [key: string]: unknown }[];
    company_visible?: boolean;
    inherited_from_page_id?: unknown;
    link_enabled?: boolean;
    link_permission?: unknown;
    [key: string]: unknown;
}

interface WikiPageRecord {
    is_published?: boolean;
    [key: string]: unknown;
}

interface TeamSlice {
    members?: { user_id?: unknown; name?: unknown; [key: string]: unknown }[];
    loading?: boolean;
}
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { TEAM_EVENTS } from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/platform-empty-state.js';

function missingAsEmpty(value: unknown): string {
    if (value === undefined || value === null) return '';
    return String(value);
}

function accessState(value: unknown): WikiAccessState | null {
    if (!isPlainRecord(value)) return null;
    const row: WikiAccessState = {};
    for (const [key, field] of Object.entries(value)) row[key] = field;
    return row;
}

function pageRecord(value: unknown): WikiPageRecord | null {
    if (!isPlainRecord(value)) return null;
    const row: WikiPageRecord = {};
    for (const [key, field] of Object.entries(value)) row[key] = field;
    return row;
}

function issuedLinkUrl(value: unknown): string {
    if (!isPlainRecord(value)) return '';
    const url = value.url;
    return typeof url === 'string' ? url : '';
}


const RELATION_VIEWER = 'viewer';
const LINK_PERMISSION_VIEWER = 'viewer';

export class WikiPageAccessModal extends PlatformModal {
    static modalKind = 'wiki.page_access';
    static i18nNamespace = 'wiki';

    declare pageId: string;
    declare _newMemberId: string;
    declare _newRelation: string;
    declare _issuedLinkUrl: string;
    private _access: OpController;
    private _page: OpController;
    private _companyVisible: OpController;
    private _memberAdd: OpController;
    private _memberRemove: OpController;
    private _publicLink: OpController;
    private _properties: OpController;
    private _pages: ResourceController;
    private _teamMembersSel: SelectController<TeamSlice['members']>;
    private _teamLoadingSel: SelectController<boolean | undefined>;

    static override get properties() {
        return {
            ...PlatformModal.properties,
            pageId: { type: String, attribute: 'page-id' },
            _newMemberId: { state: true },
            _newRelation: { state: true },
            /** Адрес известен только в этой сессии — сразу после выпуска ссылки. */
            _issuedLinkUrl: { state: true },
        };
    }

    static override styles = [
        PlatformModal.styles,
        css`
            .grid {
                display: grid;
                gap: var(--space-5);
            }

            .row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
            }

            .section-title {
                margin-bottom: var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                letter-spacing: var(--tracking-wide);
                text-transform: uppercase;
            }

            .member {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) 0;
                border-bottom: 1px solid var(--glass-border-subtle);
            }

            .member-permission {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .hint {
                margin-top: var(--space-1);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .warning {
                margin-top: var(--space-1);
                color: var(--warning);
                font-size: var(--text-xs);
            }

            .muted {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }

            .link-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-top: var(--space-2);
            }

            .link-url {
                flex: 1;
                min-width: 0;
                padding: var(--space-2);
                border-radius: var(--radius-sm);
                background: var(--wiki-surface-muted);
                color: var(--text-secondary);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                overflow-wrap: anywhere;
            }

            .link-icon-actions {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                flex-shrink: 0;
            }

            .add-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) 12rem auto;
                gap: var(--space-2);
                align-items: end;
                margin-top: var(--space-3);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.pageId = '';
        this._newMemberId = '';
        this._newRelation = RELATION_VIEWER;
        this._issuedLinkUrl = '';
        this._access = this.useOp('wiki/access_read');
        this._page = this.useOp('wiki/page_read');
        this._companyVisible = this.useOp('wiki/company_visible');
        this._memberAdd = this.useOp('wiki/member_add');
        this._memberRemove = this.useOp('wiki/member_remove');
        this._publicLink = this.useOp('wiki/public_link');
        this._properties = this.useOp('wiki/page_properties');
        this._pages = this.useResource('wiki/pages');
        this._teamMembersSel = this.select((s) => s.team.members);
        this._teamLoadingSel = this.select((s) => s.team.loading);
    }

    override connectedCallback() {
        super.connectedCallback();
        void this._access.run({ wiki_page_id: this.pageId });
        void this._page.run({ wiki_page_id: this.pageId });
        const members = this._teamMembersSel.value;
        const loading = this._teamLoadingSel.value;
        if ((!Array.isArray(members) || members.length === 0) && !loading) {
            this.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null);
        }
    }

    private _accessState(): WikiAccessState | null {
        return accessState(this._access.lastResult);
    }

    private _members(): NonNullable<WikiAccessState['members']> {
        const access = this._accessState();
        return access && Array.isArray(access.members) ? access.members : [];
    }

    private _isRestricted() {
        const access = this._accessState();
        return access !== null && access.company_visible === false;
    }

    /** Ограничение с предка снимается только на самом предке. */
    private _inheritedFromAncestorId(): string {
        const access = this._accessState();
        if (!access || typeof access.inherited_from_page_id !== 'string') {
            return '';
        }
        return access.inherited_from_page_id === this.pageId ? '' : String(access.inherited_from_page_id);
    }

    private _isPublished() {
        const page = pageRecord(this._page.lastResult);
        return page !== null && page.is_published === true;
    }

    private _linkEnabled() {
        const access = this._accessState();
        return access !== null && access.link_enabled === true;
    }

    private _linkPermission(): string {
        const access = this._accessState();
        return access && typeof access.link_permission === 'string'
            ? access.link_permission
            : LINK_PERMISSION_VIEWER;
    }

    private async _reload(): Promise<void> {
        await this._access.run({ wiki_page_id: this.pageId });
        void this._pages.load();
    }

    // --- публикация ---

    private async _onPublishToggle(event: CustomEvent<{ value?: unknown }>): Promise<void> {
        await this._properties.run({
            wiki_page_id: this.pageId,
            is_published: Boolean(event.detail.value),
        });
        await this._page.run({ wiki_page_id: this.pageId });
        void this._pages.load();
    }

    // --- участники ---

    private async _onRestrictedToggle(event: CustomEvent<{ value?: unknown }>): Promise<void> {
        await this._companyVisible.run({
            wiki_page_id: this.pageId,
            company_visible: !Boolean(event.detail.value),
        });
        await this._reload();
    }

    private async _addMember(): Promise<void> {
        if (this._newMemberId === '') {
            return;
        }
        await this._memberAdd.run({
            wiki_page_id: this.pageId,
            user_id: this._newMemberId,
            relation: this._newRelation,
        });
        this._newMemberId = '';
        await this._reload();
    }

    private async _removeMember(userId: string): Promise<void> {
        await this._memberRemove.run({ wiki_page_id: this.pageId, member_user_id: userId });
        await this._reload();
    }

    // --- публичная ссылка ---

    private async _onLinkToggle(event: CustomEvent<{ value?: unknown }>): Promise<void> {
        const result = await this._publicLink.run({
            wiki_page_id: this.pageId,
            enabled: Boolean(event.detail.value),
            permission: this._linkPermission(),
            origin: location.origin,
        });
        this._issuedLinkUrl = issuedLinkUrl(result);
        await this._reload();
    }

    private async _onLinkPermissionChange(event: CustomEvent<{ value?: unknown }>): Promise<void> {
        const result = await this._publicLink.run({
            wiki_page_id: this.pageId,
            enabled: true,
            permission: event.detail.value,
            origin: location.origin,
        });
        this._issuedLinkUrl = issuedLinkUrl(result);
        await this._reload();
    }

    private async _rotateLink(): Promise<void> {
        const confirmed = await platformConfirm(this.t('access.link_rotate_confirm_body'), {
            title: this.t('access.link_rotate_confirm_title'),
        });
        if (!confirmed) {
            return;
        }
        const result = await this._publicLink.run({
            wiki_page_id: this.pageId,
            enabled: true,
            permission: this._linkPermission(),
            origin: location.origin,
        });
        this._issuedLinkUrl = issuedLinkUrl(result);
        await this._reload();
    }

    /** Сайт открывается отдельной вкладкой: в текущей остаётся редактирование. */
    private _openSite() {
        if (this._issuedLinkUrl === '') {
            return;
        }
        window.open(this._issuedLinkUrl, '_blank', 'noopener');
    }

    private _copyLink() {
        if (this._issuedLinkUrl === '') {
            return;
        }
        this.copyToClipboard(this._issuedLinkUrl, {
            success_i18n_key: 'wiki:access.link_copied',
            error_i18n_key: 'wiki:toast.access.link_failed',
        });
    }

    // --- справочники полей ---

    private _relationConfig() {
        return {
            values: [
                { value: 'viewer', label: this.t('access.relation_viewer') },
                { value: 'editor', label: this.t('access.relation_editor') },
            ],
        };
    }

    private _linkPermissionConfig() {
        return {
            values: [
                { value: 'viewer', label: this.t('access.link_permission_viewer') },
                { value: 'editor', label: this.t('access.link_permission_editor') },
            ],
        };
    }

    private _memberConfig(): { values: { value: string; label: string }[] } {
        const granted = new Set(this._members().map((member) => member.user_id));
        const team = this._teamMembersSel.value;
        if (!Array.isArray(team)) {
            throw new Error('wiki page access: state.team.members must be array');
        }
        const values = team
            .filter((member) => member && typeof member.user_id === 'string' && !granted.has(member.user_id))
            .map((member) => ({
                value: member.user_id as string,
                label: typeof member.name === 'string' && member.name.length > 0
                    ? member.name
                    : member.user_id as string,
            }));
        return { values };
    }

    override renderHeader() {
        return this.t('access.title');
    }

    override renderBody() {
        if (!this._accessState()) {
            return html`<platform-empty-state loading></platform-empty-state>`;
        }
        return html`
            <div class="grid">
                ${this._renderPublish()}
                ${this._renderVisibility()}
                ${this._isRestricted() ? this._renderMembers() : nothing}
                ${this._renderPublicLink()}
            </div>
        `;
    }

    private _renderPublish() {
        return html`
            <div>
                <div class="section-title">${this.t('access.publish_title')}</div>
                <div class="row">
                    <platform-switch
                        data-wiki-publish
                        ?checked=${this._isPublished()}
                        label=${this.t('access.publish_label')}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => this._onPublishToggle(event)}
                    ></platform-switch>
                </div>
                <div class="hint">${this.t('access.publish_hint')}</div>
            </div>
        `;
    }

    private _renderVisibility() {
        const inheritedFrom = this._inheritedFromAncestorId();
        return html`
            <div>
                <div class="section-title">${this.t('access.visibility_label')}</div>
                <div class="row">
                    <platform-switch
                        data-wiki-visibility
                        ?checked=${this._isRestricted()}
                        ?disabled=${inheritedFrom !== ''}
                        label=${this.t('access.visibility_restricted')}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => this._onRestrictedToggle(event)}
                    ></platform-switch>
                </div>
                <div class="hint">
                    ${this._isRestricted()
                        ? this.t('access.visibility_restricted_hint')
                        : this.t('access.visibility_company_hint')}
                </div>
                ${inheritedFrom === ''
                    ? nothing
                    : html`<div class="warning">
                          ${this.t('access.inherited')}
                          <platform-button
                              variant="ghost"
                              size="sm"
                              data-wiki-inherited-open
                              @click=${() => {
                                  void this.close();
                                  this.navigate('wiki_page', { pageId: inheritedFrom });
                              }}
                          >${this.t('access.inherited_open')}</platform-button>
                      </div>`}
            </div>
        `;
    }

    private _renderMembers() {
        const members = this._members();
        return html`
            <div>
                <div class="section-title">${this.t('access.members_title')}</div>
                ${members.length === 0
                    ? html`<div class="muted">${this.t('access.members_empty')}</div>`
                    : members.map((member) => html`
                          <div class="member" data-wiki-member=${member.user_id}>
                              <platform-user-chip user-id=${member.user_id} size="sm"></platform-user-chip>
                              <span class="member-permission">
                                  ${this.t(`access.relation_${member.relation}`)}
                              </span>
                              <platform-button
                                  variant="ghost"
                                  danger
                                  icon-only
                                  density="dense"
                                  title=${this.t('access.member_remove')}
                                  @click=${() => this._removeMember(missingAsEmpty(member.user_id))}
                              ><platform-icon name="x" size="16"></platform-icon></platform-button>
                          </div>
                      `)}
                <div class="add-row">
                    <platform-field
                        type="enum"
                        mode="edit"
                        label=${this.t('access.member_add')}
                        .value=${this._newMemberId}
                        .config=${this._memberConfig()}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => { this._newMemberId = missingAsEmpty(event.detail.value); }}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        label=${this.t('access.relation_label')}
                        .value=${this._newRelation}
                        .config=${this._relationConfig()}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => { this._newRelation = missingAsEmpty(event.detail.value); }}
                    ></platform-field>
                    <platform-button variant="primary" data-wiki-member-add @click=${() => this._addMember()}>
                        <platform-icon name="plus" size="16"></platform-icon>
                    </platform-button>
                </div>
            </div>
        `;
    }

    private _renderPublicLink() {
        const enabled = this._linkEnabled();
        return html`
            <div>
                <div class="section-title">${this.t('access.link_title')}</div>
                <div class="row">
                    <platform-switch
                        data-wiki-public-link
                        ?checked=${enabled}
                        label=${this.t('access.link_enable')}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => this._onLinkToggle(event)}
                    ></platform-switch>
                    ${enabled ? nothing : html`<span class="muted">${this.t('access.link_disabled')}</span>`}
                </div>
                ${enabled ? this._renderLinkDetails() : nothing}
            </div>
        `;
    }

    private _renderLinkDetails() {
        return html`
            <platform-field
                type="enum"
                mode="edit"
                label=${this.t('access.link_permission_label')}
                .value=${this._linkPermission()}
                .config=${this._linkPermissionConfig()}
                @change=${(event: CustomEvent<{ value?: unknown }>) => this._onLinkPermissionChange(event)}
            ></platform-field>
            <div class="hint">${this.t('access.link_subtree_hint')}</div>
            ${this._isPublished() ? nothing : html`<div class="warning">${this.t('access.link_draft_warning')}</div>`}
            ${this._issuedLinkUrl === ''
                ? html`
                    <div class="hint">${this.t('access.link_hidden')}</div>
                    <platform-button
                        variant="ghost"
                        size="sm"
                        data-wiki-rotate-link
                        @click=${() => this._rotateLink()}
                    >${this.t('access.link_rotate')}</platform-button>
                `
                : html`
                    <div class="link-actions">
                        <div class="link-url" data-wiki-link-url>${this._issuedLinkUrl}</div>
                        <div class="link-icon-actions">
                            <platform-button
                                variant="ghost"
                                icon-only
                                size="sm"
                                data-wiki-copy-link
                                title=${this.t('access.link_copy')}
                                aria-label=${this.t('access.link_copy')}
                                @click=${() => this._copyLink()}
                            >
                                <platform-icon name="copy" size="16"></platform-icon>
                            </platform-button>
                            <platform-button
                                variant="ghost"
                                icon-only
                                size="sm"
                                data-wiki-open-site
                                title=${this.t('access.link_open_site')}
                                aria-label=${this.t('access.link_open_site')}
                                @click=${() => this._openSite()}
                            >
                                <platform-icon name="external-link" size="16"></platform-icon>
                            </platform-button>
                        </div>
                    </div>
                `}
        `;
    }
}

customElements.define('wiki-page-access-modal', WikiPageAccessModal);
registerModalKind(WikiPageAccessModal.modalKind, 'wiki-page-access-modal');
