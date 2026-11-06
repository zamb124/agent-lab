/**
 * Публичный каталог демо-агентов: карточки + пробный чат через <flow-ui-drawer>.
 */
import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { marketingPublicContentPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import '@platform/lib/flow-ui/shell/drawer.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-empty-state.js';
import { resolveVoiceHttpOriginFromFlowsBaseUrl } from '@platform/lib/voice/voice-http-origin.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';
import '../components/cosmic/cosmic-scope.js';
import '../components/cosmic/scramble-text.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

/** Изолированный toggle: не пересекается с Lara (`platform-lara-open`). */
const LANDING_DEMO_DRAWER_TOGGLE_EVENT = 'landing-demo-flow-ui-toggle';

export class LandingDigitalWorkersPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static override properties: PropertyDeclarations = {
        _drawerSpec: { state: true },
        _drawerOpen: { state: true },
    }
    declare _drawerSpec: any;
    declare _drawerOpen: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        ...marketingPublicContentPageStyles,
        css`
            .marketing-digital-workers {
                max-width: var(--marketing-content-max-width);
            }

            platform-breadcrumbs {
                display: block;
                margin-bottom: var(--space-6);
            }

            .marketing-digital-workers-disclaimer {
                max-width: 48rem;
                margin: 0 auto var(--space-10);
                padding: var(--space-4);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-bg-subtle);
                font-size: var(--text-sm);
                line-height: var(--leading-relaxed);
                color: var(--text-tertiary);
                text-align: center;
            }

            .marketing-digital-workers-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: var(--space-6);
            }

            .marketing-digital-workers-card {
                overflow: hidden;
                padding: 0;
                display: flex;
                flex-direction: column;
            }

            .marketing-digital-workers-card-image {
                width: 100%;
                aspect-ratio: 16 / 10;
                object-fit: cover;
            }

            .marketing-digital-workers-card-body {
                padding: var(--space-6);
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                flex: 1;
            }

            .marketing-digital-workers-card-title {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                margin: 0;
                color: var(--text-primary);
            }

            .marketing-digital-workers-card-desc {
                font-size: var(--text-base);
                line-height: var(--leading-relaxed);
                color: var(--text-secondary);
                margin: 0;
                flex: 1;
            }

            .marketing-digital-workers-card-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
            }

            .marketing-digital-workers-state {
                display: grid;
                place-items: center;
                min-height: 12rem;
                color: var(--text-secondary);
            }

            .marketing-digital-workers-state.is-error {
                color: var(--error);
            }
        `,
    ];

    constructor() {
        super();
        this._drawerSpec = null;
        this._drawerOpen = false;
        this._load = this.useOp('frontend/landing_agents_load');
        this._session = this.useOp('frontend/landing_demo_session');
        if (typeof window === 'undefined' || typeof window.location.origin !== 'string') {
            throw new Error('landing_digital_workers_page: window.location.origin required');
        }
        this._flowsBaseUrl = new URL('/flows', window.location.origin).href;
    }
    private _load: OpController;
    private _session: OpController;
    private _flowsBaseUrl: unknown;


    _onDrawerOpenChanged(e: CustomEvent) {
        const d = e.detail;
        if (d && typeof d.open === 'boolean') {
            this._drawerOpen = d.open;
        }
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._load.run(null);
    }

    _getDemoRequestHeaders = async () => {
        const spec = this._drawerSpec;
        if (!spec || typeof spec.embed_id !== 'string' || spec.embed_id === '') {
            throw new Error('landing_digital_workers: drawer embed context missing');
        }
        const result = await this._session.run({ embed_id: spec.embed_id });
        if (result === null) {
            const msg = this._session.error;
            if (typeof msg === 'string' && msg !== '') {
                this.toast('digital_workers.session_error', {
                    type: 'error',
                    vars: { detail: msg },
                });
            } else {
                this.toast('digital_workers.session_error_generic', { type: 'error' });
            }
            return {};
        }
        if (!isPlainRecord(result)) {
            throw new Error('landing_digital_workers: session token missing');
        }
        const token = result.token;
        if (typeof token !== 'string' || token === '') {
            throw new Error('landing_digital_workers: session token missing');
        }
        return { Authorization: `Bearer ${token}` };
    };

    _tryAgent(card: Record<string, unknown>) {
        if (typeof card.embed_id !== 'string' || card.embed_id === '') {
            throw new Error('landing_digital_workers: card.embed_id required');
        }
        if (typeof card.flow_id !== 'string' || card.flow_id === '') {
            throw new Error('landing_digital_workers: card.flow_id required');
        }
        if (typeof card.branch_id !== 'string' || card.branch_id === '') {
            throw new Error('landing_digital_workers: card.branch_id required');
        }
        const theme = card.theme === 'light' || card.theme === 'dark' || card.theme === 'auto' ? card.theme : 'dark';
        const locale =
            card.interface_locale === 'ru' || card.interface_locale === 'en' ? card.interface_locale : 'auto';
        this._drawerSpec = {
            embed_id: card.embed_id,
            flow_id: card.flow_id,
            branch_id: card.branch_id,
            theme,
            interface_locale: locale,
        };
        this._drawerOpen = true;
        this.requestUpdate();
    }

    _hire() {
        this.openModal('auth.login');
    }

    _drawerConfig() {
        const spec = this._drawerSpec;
        if (spec === null) {
            throw new Error('landing_digital_workers: drawer spec required');
        }
        return {
            embedId: spec.embed_id,
            flowId: spec.flow_id,
            branchId: spec.branch_id as string,
            baseUrl: this._flowsBaseUrl as string,
            companyId: 'system',
            voiceBaseUrl: resolveVoiceHttpOriginFromFlowsBaseUrl(this._flowsBaseUrl as string),
            profile: 'embed_public',
            theme: spec.theme as string,
            locale: spec.interface_locale,
            showLauncher: true,
            credentials: 'omit',
            toggleEventName: LANDING_DEMO_DRAWER_TOGGLE_EVENT,
            getRequestHeaders: this._getDemoRequestHeaders,
        };
    }

    _itemsList() {
        const raw = this._load.lastResult;
        if (raw === null || typeof raw !== 'object') {
            return [];
        }
        if (!isPlainRecord(raw)) {
            throw new Error('landing_digital_workers: items must be array');
        }
        const items = raw.items;
        if (!Array.isArray(items)) {
            throw new Error('landing_digital_workers: items must be array');
        }
        return items;
    }

    override render(): TemplateResult {
        const busy = this._load.busy;
        const err = this._load.error;
        const items = this._itemsList();

        return html`
            <cosmic-scope class="marketing-page-container">
                <landing-header></landing-header>
                <section data-cosmic-chapter data-cosmic-hue="252" data-cosmic-label=${this.t('digital_workers.title')}>
                <div class="marketing-content marketing-digital-workers">
                    <platform-breadcrumbs></platform-breadcrumbs>
                    <header class="marketing-content-hero">
                        <h1 class="marketing-content-title"><scramble-text .text=${this.t('digital_workers.title')}></scramble-text></h1>
                        <p class="marketing-content-lede">${this.t('digital_workers.subtitle')}</p>
                    </header>
                    <p class="marketing-digital-workers-disclaimer">${this.t('digital_workers.disclaimer')}</p>

                    ${busy && items.length === 0
                        ? html`<platform-empty-state loading></platform-empty-state>`
                        : ''}
                    ${err !== null && items.length === 0
                        ? html`<div class="marketing-digital-workers-state is-error">${this.t('digital_workers.load_error')}</div>`
                        : ''}
                    ${!busy && err === null && items.length === 0
                        ? html`<div class="marketing-digital-workers-state">${this.t('digital_workers.empty')}</div>`
                        : ''}

                    ${items.length > 0
                        ? html`
                              <div class="marketing-digital-workers-grid">
                                  ${items.map((card) => html`
                                          <article class="marketing-content-card glass-medium marketing-digital-workers-card">
                                              <img
                                                  class="marketing-digital-workers-card-image"
                                                  src=${card.landing_card_image_url}
                                                  alt=""
                                                  loading="lazy"
                                              />
                                              <div class="marketing-digital-workers-card-body">
                                                  <h2 class="marketing-digital-workers-card-title">${card.name}</h2>
                                                  <p class="marketing-digital-workers-card-desc">
                                                      ${typeof card.greeting_message === 'string' &&
                                                      card.greeting_message !== ''
                                                          ? card.greeting_message
                                                          : this.t('digital_workers.card_fallback_desc')}
                                                  </p>
                                                  <div class="marketing-digital-workers-card-actions">
                                                      <platform-button
                                                          variant="primary"
                                                          density="compact"
                                                          @click=${() => this._tryAgent(card)}
                                                      >
                                                          ${this.t('digital_workers.cta_try')}
                                                      </platform-button>
                                                      <platform-button
                                                          variant="secondary"
                                                          density="compact"
                                                          @click=${this._hire}
                                                      >
                                                          ${this.t('digital_workers.cta_hire')}
                                                      </platform-button>
                                                  </div>
                                              </div>
                                          </article>
                                      `,
                                  )}
                              </div>
                          `
                        : ''}
                </div>
                </section>
                <landing-footer></landing-footer>
            </cosmic-scope>
            ${this._drawerSpec === null
                ? nothing
                : html`
                      <flow-ui-drawer
                          .open=${this._drawerOpen}
                          .config=${this._drawerConfig()}
                          @flow-ui-drawer-open-changed=${this._onDrawerOpenChanged}
                      ></flow-ui-drawer>
                  `}
        `;
    }
}

customElements.define('landing-digital-workers-page', LandingDigitalWorkersPage);
