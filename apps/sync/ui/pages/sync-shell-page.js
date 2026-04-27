/**
 * sync-shell-page — экран `/sync` без выбранного канала.
 * Показывает <sync-channel-picker>.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '../components/sync-channel-picker.js';

export class SyncShellPage extends PlatformPage {
    static styles = css`
        :host {
            display: flex;
            flex-direction: column;
            flex: 1;
            min-height: 0;
            height: 100%;
        }
    `;

    constructor() {
        super();
        this.useEvent('sync/calls/adhoc_create_requested', () => this._onAdhocCall());
    }

    _onAdhocCall() {
        this.openModal('sync.channel_create', { adhocCall: true });
    }

    render() {
        return html`<sync-channel-picker></sync-channel-picker>`;
    }
}

customElements.define('sync-shell-page', SyncShellPage);
