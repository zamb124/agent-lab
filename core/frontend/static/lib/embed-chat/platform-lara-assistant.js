import { LitElement, html } from 'lit';
import './platform-embed-chat-drawer.js';

/**
 * Единый модуль подключения Lara в UI приложений платформы.
 * Приложения передают только контекст/авторизацию и не дублируют wiring drawer.
 */
export class PlatformLaraAssistant extends LitElement {
    static properties = {
        flowsBaseUrl: { type: String, attribute: 'flows-base-url' },
        flowId: { type: String, attribute: 'flow-id' },
        skillId: { type: String, attribute: 'skill-id' },
        assistantTitle: { type: String, attribute: 'assistant-title' },
        locale: { type: String },
        useCredentials: { type: Boolean, attribute: 'use-credentials' },
        toggleEventName: { type: String, attribute: 'toggle-event-name' },
        eventNamespace: { type: String, attribute: 'event-namespace' },
        getAuthToken: { type: Object },
        getExtraMetadataVariables: { type: Object },
        getContextVariables: { type: Object },
        actionHandlers: { type: Object },
    };

    createRenderRoot() {
        return this;
    }

    constructor() {
        super();
        this.flowsBaseUrl = '';
        this.flowId = 'lara';
        this.skillId = '';
        this.assistantTitle = 'Lara';
        this.locale = 'ru';
        this.useCredentials = false;
        this.toggleEventName = 'humanitec-embed-chat-toggle';
        this.eventNamespace = 'assistant';
        this.getAuthToken = undefined;
        this.getExtraMetadataVariables = undefined;
        this.getContextVariables = undefined;
        this.actionHandlers = {};
    }

    render() {
        return html`
            <platform-embed-chat-drawer
                theme="auto"
                .flowsBaseUrl=${this.flowsBaseUrl}
                flow-id=${this.flowId || 'lara'}
                skill-id=${this.skillId || ''}
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
            ></platform-embed-chat-drawer>
        `;
    }
}

customElements.define('platform-lara-assistant', PlatformLaraAssistant);
