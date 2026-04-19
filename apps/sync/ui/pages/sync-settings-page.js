import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';

export class SyncSettingsPage extends PlatformPage {
    static styles = css`:host { display: block; padding: var(--space-4); }`;

    render() {
        return html`<h2>${this.t('settings.title')}</h2>`;
    }
}

customElements.define('sync-settings-page', SyncSettingsPage);
