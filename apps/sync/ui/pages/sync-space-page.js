import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';

export class SyncSpacePage extends PlatformPage {
    static properties = { spaceId: { type: String } };
    static styles = css`:host { display: block; padding: var(--space-4); }`;

    constructor() {
        super();
        this.spaceId = '';
        this._spaces = this.useResource('sync/spaces', { autoload: true });
        this._channels = this.useResource('sync/channels', { autoload: true });
    }

    render() {
        const space = this._spaces.byId[this.spaceId];
        const channels = this._channels.items.filter((c) => c.space_id === this.spaceId);
        return html`
            <h2>${space ? space.name : this.spaceId}</h2>
            <ul>
                ${channels.map((c) => html`
                    <li @click=${() => this.navigate('channel', { channelId: c.id })}>${c.name}</li>
                `)}
            </ul>
        `;
    }
}

customElements.define('sync-space-page', SyncSpacePage);
