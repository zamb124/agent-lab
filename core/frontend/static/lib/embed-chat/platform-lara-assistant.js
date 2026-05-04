import { LitElement, html } from './lit-shim.js';
import './platform-embed-chat-drawer.js';

/**
 * Единый модуль подключения Lara в UI приложений платформы.
 * Приложения передают только контекст/авторизацию и не дублируют wiring drawer.
 */
export class PlatformLaraAssistant extends LitElement {
    static properties = {
        flowsBaseUrl: { type: String, attribute: 'flows-base-url' },
        flowId: { type: String, attribute: 'flow-id' },
        embedId: { type: String, attribute: 'embed-id' },
        branchId: { type: String, attribute: 'branch-id' },
        skillId: { type: String, attribute: 'skill-id' },
        theme: { type: String, attribute: 'theme' },
        showLauncher: { type: Boolean, attribute: 'show-launcher' },
        assistantTitle: { type: String, attribute: 'assistant-title' },
        locale: { type: String },
        useCredentials: { type: Boolean, attribute: 'use-credentials' },
        toggleEventName: { type: String, attribute: 'toggle-event-name' },
        eventNamespace: { type: String, attribute: 'event-namespace' },
        getAuthToken: { type: Object },
        getExtraMetadataVariables: { type: Object },
        getContextVariables: { type: Object },
        actionHandlers: { type: Object },
        voiceEnabled: { type: Boolean, attribute: 'voice-enabled' },
        voiceDefaultOn: { type: Boolean, attribute: 'voice-default-on' },
        voiceBaseUrl: { type: String, attribute: 'voice-base-url' },
        companyId: { type: String, attribute: 'company-id' },
    };

    createRenderRoot() {
        return this;
    }

    constructor() {
        super();
        this.flowsBaseUrl = '';
        this.flowId = 'lara';
        this.embedId = '';
        this.branchId = '';
        this.skillId = '';
        this.theme = 'auto';
        this.showLauncher = false;
        this.assistantTitle = 'Lara';
        this.locale = 'ru';
        this.useCredentials = false;
        this.toggleEventName = 'humanitec-embed-chat-toggle';
        this.eventNamespace = 'assistant';
        this.getAuthToken = undefined;
        this.getExtraMetadataVariables = undefined;
        this.getContextVariables = undefined;
        this.actionHandlers = {};
        this.voiceEnabled = false;
        this.voiceDefaultOn = false;
        this.voiceBaseUrl = '';
        this.companyId = '';
    }

    render() {
        return html`
            <platform-embed-chat-drawer
                .theme=${this.theme || 'auto'}
                .showLauncher=${this.showLauncher}
                .flowsBaseUrl=${this.flowsBaseUrl}
                flow-id=${this.flowId || 'lara'}
                embed-id=${this.embedId || ''}
                branch-id=${(this.branchId || this.skillId || '').trim()}
                skill-id=${(this.skillId || this.branchId || '').trim()}
                .assistantTitle=${this.assistantTitle || 'Lara'}
                .locale=${this.locale || 'ru'}
                ?use-credentials=${this.useCredentials}
                toggle-event-name=${this.toggleEventName || 'humanitec-embed-chat-toggle'}
                event-namespace=${this.eventNamespace || 'assistant'}
                .getAuthToken=${this.getAuthToken}
                .getExtraMetadataVariables=${this.getExtraMetadataVariables}
                .getContextVariables=${this.getContextVariables}
                .actionHandlers=${this.actionHandlers && typeof this.actionHandlers === 'object'
                    ? this.actionHandlers
                    : {}}
                ?voice-enabled=${this.voiceEnabled}
                ?voice-default-on=${this.voiceDefaultOn}
                voice-base-url=${this.voiceBaseUrl || ''}
                company-id=${this.companyId || ''}
            ></platform-embed-chat-drawer>
        `;
    }
}

customElements.define('platform-lara-assistant', PlatformLaraAssistant);
