import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '../components/sync-chat-header.js';

export class SyncSettingsPage extends PlatformPage {
    static styles = css`
        :host {
            display: flex;
            flex-direction: column;
            flex: 1;
            min-height: 0;
            height: 100%;
        }
        .body {
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            padding: var(--space-4);
        }
    `;

    render() {
        return html`
            <sync-chat-header
                header-mode="list"
                .listTitle=${this.t('settings.title')}
                .listSubtitle=${''}
            ></sync-chat-header>
            <div class="body"></div>
        `;
    }
}

customElements.define('sync-settings-page', SyncSettingsPage);
