/**
 * auth-modal — окно входа в платформу.
 *
 * Открытие: dispatch CoreEvents.UI_MODAL_OPEN { kind: 'auth.login',
 *                                               props: { returnPath?, plan? } }.
 * Закрытие: this.close() (dispatch CoreEvents.UI_MODAL_CLOSE).
 *
 * Логика входа: модалка только диспатчит auth/oauth/start_requested и
 * auth/demo/login_requested; редирект делает auth.effect. Состояние демо
 * (enabled, email) и список провайдеров — из state.auth (prefetch в PlatformApp).
 */
import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformModal } from './glass-modal.js';
import { registerModalKind } from '../utils/modal-registry.js';
import { CoreAuthEvents } from '../events/effects/auth.effect.js';
import type { AuthProvidersState, AuthState } from '../events/reducers/auth.js';
import type { SelectController } from '../events/select-controller.js';
import { isPlainRecord } from '../events/payload.js';

function payloadMessage(payload: unknown): string | undefined {
    if (!isPlainRecord(payload)) return undefined;
    const message = payload.message;
    return typeof message === 'string' && message.length > 0 ? message : undefined;
}

function providerI18nKey(name: string): string | undefined {
    if (name === 'yandex' || name === 'google' || name === 'github' || name === 'apple') {
        return PROVIDER_I18N_KEYS[name];
    }
    return undefined;
}

function inputValue(event: Event): string {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
        throw new Error('auth-modal: input required');
    }
    return target.value;
}
import './platform-icon.js';

/** Провайдеры с цветным брендовым SVG (не monochrome currentColor). */
const COLORED_PROVIDER_ICONS = new Set(['yandex', 'google']);

const PROVIDER_I18N_KEYS = Object.freeze({
    yandex: 'auth.yandex',
    google: 'auth.google',
    github: 'auth.github',
    apple: 'auth.apple',
});

/** Скелет кнопок, пока providers.list ещё пуст — держит высоту модалки. */
const PROVIDER_SKELETON_COUNT = 4;

export class AuthModal extends PlatformModal {
    static modalKind = 'auth.login';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        returnPath: { type: String, attribute: 'return-path' },
        plan: { type: String },
        loading: { state: true },
        error: { state: true },
        _demoPassword: { state: true },
    };
    declare returnPath: string;
    declare plan: string;
    declare loading: boolean;
    declare error: string;
    declare _demoPassword: string;

    private _demoSel: SelectController<AuthState['demo']>;
    private _providersSel: SelectController<AuthProvidersState>;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        css`
            .modal-subtitle { text-align: center; opacity: 0.7; margin-bottom: var(--space-6); }
            .providers { display: flex; flex-direction: column; gap: var(--space-3); }
            .provider-button {
                display: flex; align-items: center; justify-content: center; gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                min-height: var(--button-height, 44px);
                background: var(--glass-bg-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                font-size: var(--text-base); color: var(--text-primary);
                cursor: pointer; transition: var(--motion-transition-interactive);
            }
            .provider-button:hover {
                background: var(--glass-bg-medium);
                transform: translateY(-1px);
            }
            .provider-button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
            .provider-button--skeleton {
                cursor: default;
                pointer-events: none;
                opacity: 0.45;
            }
            .provider-button--skeleton:hover { transform: none; }
            .provider-skeleton-bar {
                display: block;
                width: 9.5rem;
                height: 0.875rem;
                border-radius: var(--radius-sm);
                background: var(--border-subtle);
            }
            .error {
                margin-top: var(--space-4); padding: var(--space-3);
                background: var(--error-bg, rgba(255, 59, 48, 0.1));
                border: 1px solid var(--error-border, rgba(255, 59, 48, 0.3));
                border-radius: var(--radius-sm); color: var(--error);
                font-size: var(--text-sm); text-align: center;
            }
            .demo-title { margin: var(--space-6) 0 var(--space-3); text-align: center; opacity: 0.85; font-size: var(--text-sm); }
            .demo-form { display: flex; flex-direction: column; gap: var(--space-2); }
            .demo-label { font-size: var(--text-xs); opacity: 0.8; }
            .demo-input {
                width: 100%; box-sizing: border-box;
                padding: var(--space-3);
                min-height: var(--input-height, 44px);
                background: var(--glass-bg-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                color: var(--text-primary); font-size: var(--text-base);
            }
            .demo-input:focus { outline: none; border-color: var(--accent); }
            .demo-slot {
                min-height: calc(
                    var(--space-6) + var(--space-3) + 1.25rem
                    + (var(--text-xs, 0.75rem) * 2) + (var(--space-2) * 2)
                    + (var(--input-height, 44px) * 2)
                    + var(--button-height, 44px)
                );
            }
            .demo-slot--empty { min-height: 0; }
        `,
    ];

    constructor() {
        super();
        this.returnPath = '';
        this.plan = '';
        this.loading = false;
        this.error = '';
        this._demoPassword = '';
        this.size = 'sm';
        this._demoSel = this.select((s) => s.auth.demo);
        this._providersSel = this.select((s) => s.auth.providers);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        const demo: AuthState['demo'] = this._demoSel.value || { enabled: false, email: null, loaded: false };
        const providers: AuthProvidersState = this._providersSel.value || { list: [], loading: false, error: null };
        if (!demo.loaded) {
            this.dispatch(CoreAuthEvents.DEMO_STATUS_REQUESTED, null);
        }
        if (!providers.loading && providers.list.length === 0 && !providers.error) {
            this.dispatch(CoreAuthEvents.PROVIDERS_LOAD_REQUESTED, null);
        }
        this.useEvent(CoreAuthEvents.OAUTH_FAILED, (event) => {
            this.loading = false;
            this.error = payloadMessage(event.payload) || (this.t('auth.oauth_error') || 'OAuth error');
        });
        this.useEvent(CoreAuthEvents.DEMO_LOGIN_FAILED, (event) => {
            this.loading = false;
            this.error = payloadMessage(event.payload) || (this.t('auth.demo_error') || 'Demo login error');
        });
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this.title = this.t('auth.title') || 'auth.title';
        if (changed.has('open') && this.open) {
            this.loading = false;
            this.error = '';
            this._demoPassword = '';
        }
    }

    _handleProvider(provider: string): void {
        if (this.loading) return;
        this.loading = true;
        this.error = '';
        const returnPath = (typeof this.returnPath === 'string' && this.returnPath !== '') ? this.returnPath : undefined;
        const plan = (typeof this.plan === 'string' && this.plan !== '') ? this.plan : undefined;
        this.startOAuth(provider, { returnPath, plan });
    }

    _openSupport() {
        this.close();
        this.navigate('support');
    }

    override renderHeaderActions(): TemplateResult {
        const label = this.t('auth.support_link_aria');
        return html`
            <button
                type="button"
                class="header-btn"
                title=${label}
                aria-label=${label}
                @click=${this._openSupport}
            >
                <platform-icon name="help" size="16"></platform-icon>
            </button>
        `;
    }

    _handleDemoSubmit(e: Event): void {
        e.preventDefault();
        if (this.loading) return;
        const demo = this._demoSel.value || { enabled: false, email: null, loaded: false };
        const email = typeof demo.email === 'string' ? demo.email.trim() : '';
        if (!email || !this._demoPassword) {
            this.error = this.t('auth.demo_error') || 'Email and password required';
            return;
        }
        this.loading = true;
        this.error = '';
        this.dispatch(CoreAuthEvents.DEMO_LOGIN_REQUESTED, {
            email,
            password: this._demoPassword,
        });
    }

    _providerLabel(name: string): string {
        const key = providerI18nKey(name);
        if (typeof key === 'string') {
            return this.t(key) || key;
        }
        return name;
    }

    _renderProviderButton(name: string): TemplateResult {
        const colored = COLORED_PROVIDER_ICONS.has(name);
        return html`
            <button
                type="button"
                class="provider-button"
                @click=${() => this._handleProvider(name)}
                ?disabled=${this.loading}
            >
                <platform-icon
                    name=${name}
                    size="24"
                    ?colored=${colored}
                ></platform-icon>
                <span>${this._providerLabel(name)}</span>
            </button>
        `;
    }

    _renderProviders(): TemplateResult[] {
        const providers = this._providersSel.value || { list: [], loading: false, error: null };
        const list = providers.list;
        if (list.length > 0) {
            return list.map((item: { name?: string }) => {
                if (!item || typeof item.name !== 'string' || item.name.length === 0) {
                    throw new Error('auth-modal: provider item.name is required');
                }
                return this._renderProviderButton(item.name);
            });
        }
        const skeletonCount = providers.loading || !providers.error
            ? PROVIDER_SKELETON_COUNT
            : 0;
        return Array.from({ length: skeletonCount }, () => html`
            <div class="provider-button provider-button--skeleton" aria-hidden="true">
                <span class="provider-skeleton-bar"></span>
            </div>
        `);
    }

    _renderDemoSlot(): TemplateResult {
        const demo = this._demoSel.value || { enabled: false, email: null, loaded: false };
        if (!demo.loaded) {
            return html`
                <div class="demo-slot" aria-hidden="true">
                    <p class="demo-title">${this.t('auth.demo_title') || 'auth.demo_title'}</p>
                    <div class="demo-form">
                        <span class="demo-label">${this.t('auth.demo_email_label') || 'auth.demo_email_label'}</span>
                        <div class="demo-input"></div>
                        <span class="demo-label">${this.t('auth.demo_password_label') || 'auth.demo_password_label'}</span>
                        <div class="demo-input"></div>
                        <div class="provider-button provider-button--skeleton">
                            <span class="provider-skeleton-bar"></span>
                        </div>
                    </div>
                </div>
            `;
        }
        if (!demo.enabled) {
            return html`<div class="demo-slot demo-slot--empty"></div>`;
        }
        const email = typeof demo.email === 'string' ? demo.email : '';
        return html`
            <div class="demo-slot">
                <p class="demo-title">${this.t('auth.demo_title') || 'auth.demo_title'}</p>
                <form class="demo-form" @submit=${(e: Event) => this._handleDemoSubmit(e)}>
                    <label class="demo-label" for="demo-email">${this.t('auth.demo_email_label') || 'auth.demo_email_label'}</label>
                    <input id="demo-email" class="demo-input" type="email" name="username" autocomplete="username"
                        .value=${email} disabled />
                    <label class="demo-label" for="demo-password">${this.t('auth.demo_password_label') || 'auth.demo_password_label'}</label>
                    <input id="demo-password" class="demo-input" type="password" name="password" autocomplete="current-password"
                        .value=${this._demoPassword}
                        @input=${(ev: InputEvent) => { this._demoPassword = inputValue(ev); }} />
                    <button type="submit" class="provider-button" ?disabled=${this.loading}>
                        ${this.t('auth.demo_submit') || 'auth.demo_submit'}
                    </button>
                </form>
            </div>
        `;
    }

    override renderBody(): TemplateResult {
        return html`
            <p class="modal-subtitle">${this.t('auth.subtitle') || 'auth.subtitle'}</p>
            <div class="providers">
                ${this._renderProviders()}
            </div>
            ${this._renderDemoSlot()}
            ${this.error ? html`<div class="error">${this.error}</div>` : nothing}
        `;
    }

    override renderFooter(): TemplateResult {
        return html``;
    }
}

customElements.define('auth-modal', AuthModal);
registerModalKind(AuthModal.modalKind, 'auth-modal');
