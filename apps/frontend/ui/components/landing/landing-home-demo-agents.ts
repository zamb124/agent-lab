/**
 * Секция главной: три публичных демо-агента (lawyer, support_demo, psy) + flow-ui-drawer.
 */
import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/flow-ui/shell/drawer.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/glass-spinner.js';
import { resolveVoiceHttpOriginFromFlowsBaseUrl } from '@platform/lib/voice/voice-http-origin.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

const HOME_DEMO_FLOW_ORDER = Object.freeze(['lawyer', 'support_demo', 'psy']);

/** Изолированный toggle: не пересекается с Lara (`platform-lara-open`). */
const LANDING_DEMO_DRAWER_TOGGLE_EVENT = 'landing-demo-flow-ui-toggle';

export class LandingHomeDemoAgents extends PlatformElement {
    static i18nNamespace = 'landing';

    static override properties: PropertyDeclarations = {
        _drawerSpec: { state: true },
        _drawerOpen: { state: true },
    }
    declare _drawerSpec: any;
    declare _drawerOpen: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                box-sizing: border-box;
            }
            .wrap {
                max-width: 1200px;
                margin: 0 auto;
                padding: var(--space-8) 20px;
                box-sizing: border-box;
            }
            .head {
                text-align: center;
                margin-bottom: var(--space-8);
            }
            h2 {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: clamp(1.5rem, 4vw, 2.25rem);
                font-weight: 600;
                margin: 0 0 var(--space-3);
                line-height: 1.2;
            }
            .lede {
                font-family: var(--font-sans);
                font-size: var(--text-md);
                line-height: 1.6;
                color: var(--landing-text-subtle, rgba(255, 255, 255, 0.72));
                max-width: 40rem;
                margin: 0 auto;
            }
            .toolbar {
                display: flex;
                justify-content: center;
                margin-top: var(--space-4);
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: var(--space-6);
            }
            .card-image {
                width: 100%;
                aspect-ratio: 16 / 10;
                object-fit: cover;
                border-radius: var(--radius-md);
                display: block;
                background: var(--landing-panel-bg, rgba(255, 255, 255, 0.06));
            }
            .card-body {
                padding: var(--space-4) 0 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                flex: 1;
            }
            .card-title {
                font-size: var(--text-lg);
                font-weight: 600;
                margin: 0;
            }
            .card-desc {
                font-size: var(--text-sm);
                color: var(--landing-text-subtle, rgba(255, 255, 255, 0.65));
                margin: 0;
                line-height: 1.5;
                flex: 1;
            }
            .card-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-top: var(--space-2);
            }
            .state-center {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-4);
                min-height: 160px;
                font-family: var(--font-sans);
                color: var(--landing-text-subtle, rgba(255, 255, 255, 0.7));
            }
            .err {
                color: #f87171;
                text-align: center;
                max-width: 36rem;
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
            throw new Error('landing_home_demo_agents: window.location.origin required');
        }
        this._flowsBaseUrl = new URL('/flows', window.location.origin).href;
    }
    private _load: OpController;
    private _session: OpController;
    private _flowsBaseUrl: unknown;


    override connectedCallback(): void {
        super.connectedCallback();
        this._load.run(null);
    }

    _onDrawerOpenChanged(e: CustomEvent) {
        const d = e.detail;
        if (d && typeof d.open === 'boolean') {
            this._drawerOpen = d.open;
        }
    }

    _getDemoRequestHeaders = async () => {
        const spec = this._drawerSpec;
        if (!spec || typeof spec.embed_id !== 'string' || spec.embed_id === '') {
            throw new Error('landing_home_demo_agents: drawer embed context missing');
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
            throw new Error('landing_home_demo_agents: session token missing');
        }
        const token = result.token;
        if (typeof token !== 'string' || token === '') {
            throw new Error('landing_home_demo_agents: session token missing');
        }
        return { Authorization: `Bearer ${token}` };
    };

    _tryAgent(card: Record<string, any>) {
        if (typeof card.embed_id !== 'string' || card.embed_id === '') {
            throw new Error('landing_home_demo_agents: card.embed_id required');
        }
        if (typeof card.flow_id !== 'string' || card.flow_id === '') {
            throw new Error('landing_home_demo_agents: card.flow_id required');
        }
        if (typeof card.branch_id !== 'string' || card.branch_id === '') {
            throw new Error('landing_home_demo_agents: card.branch_id required');
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
            throw new Error('landing_home_demo_agents: drawer spec required');
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

    _allItemsList() {
        const raw = this._load.lastResult;
        if (Array.isArray(raw)) {
            throw new Error('landing_home_demo_agents: items must be array');
        }
        if (!isPlainRecord(raw)) {
            return [];
        }
        const items = raw.items;
        if (!Array.isArray(items)) {
            throw new Error('landing_home_demo_agents: items must be array');
        }
        return items;
    }

    _filteredItems() {
        const all = this._allItemsList();
        if (all.length === 0) {
            return [];
        }
        const byFlow = new Map();
        for (const card of all) {
            if (card === null || typeof card !== 'object') {
                continue;
            }
            const fid = card.flow_id;
            if (typeof fid !== 'string') {
                continue;
            }
            if (HOME_DEMO_FLOW_ORDER.includes(fid)) {
                byFlow.set(fid, card);
            }
        }
        const out: any[] = [];
        for (const fid of HOME_DEMO_FLOW_ORDER) {
            const c = byFlow.get(fid);
            if (c !== undefined) {
                out.push(c);
            }
        }
        return out;
    }

    override render(): TemplateResult {
        const busy = this._load.busy;
        const err = this._load.error;
        const allItems = this._allItemsList();
        const items = this._filteredItems();

        return html`
            <div class="wrap">
                <header class="head">
                    <h2>${this.t('home_demo_agents.title')}</h2>
                    <p class="lede">${this.t('home_demo_agents.subtitle')}</p>
                    <div class="toolbar">
                        <glass-button variant="secondary" size="sm" @click=${() => this.navigate('digital-workers')}>
                            ${this.t('home_demo_agents.view_all')}
                        </glass-button>
                    </div>
                </header>

                ${busy && allItems.length === 0
                    ? html`<div class="state-center"><glass-spinner></glass-spinner></div>`
                    : ''}
                ${err !== null && allItems.length === 0
                    ? html`<div class="state-center err">${this.t('digital_workers.load_error')}</div>`
                    : ''}
                ${!busy && err === null && allItems.length === 0
                    ? html`<div class="state-center">${this.t('digital_workers.empty')}</div>`
                    : ''}
                ${!busy && err === null && allItems.length > 0 && items.length === 0
                    ? html`<div class="state-center">${this.t('home_demo_agents.filter_empty')}</div>`
                    : ''}

                ${items.length > 0
                    ? html`
                          <div class="grid">
                              ${items.map((card) => html`
                                      <glass-card>
                                          <img
                                              class="card-image"
                                              src=${card.landing_card_image_url}
                                              alt=""
                                              loading="lazy"
                                          />
                                          <div class="card-body">
                                              <h3 class="card-title">${card.name}</h3>
                                              <p class="card-desc">
                                                  ${typeof card.greeting_message === 'string' && card.greeting_message !== ''
                                                      ? card.greeting_message
                                                      : this.t('digital_workers.card_fallback_desc')}
                                              </p>
                                              <div class="card-actions">
                                                  <glass-button
                                                      variant="primary"
                                                      size="sm"
                                                      @click=${() => this._tryAgent(card)}
                                                  >
                                                      ${this.t('digital_workers.cta_try')}
                                                  </glass-button>
                                                  <glass-button variant="secondary" size="sm" @click=${this._hire}>
                                                      ${this.t('digital_workers.cta_hire')}
                                                  </glass-button>
                                              </div>
                                          </div>
                                      </glass-card>
                                  `,
                              )}
                          </div>
                      `
                    : ''}
            </div>
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

customElements.define('landing-home-demo-agents', LandingHomeDemoAgents);
