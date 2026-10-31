/**
 * Сайдбар Sync: поиск и «Чаты» не должны перекрываться карточками при скролле ленты.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, waitUntil } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { bootstrapPlatformBus, collectFactories, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { channelsResource } from '../../../../apps/sync/ui/events/resources/channels.resource.js';
import { companyMembersResource } from '../../../../apps/sync/ui/events/resources/members.resource.js';
import { chatUiResource } from '../../../../apps/sync/ui/events/resources/chat-ui.resource.js';
import {
    callUiResource,
    channelCreateAdhocCallOp,
    callInviteOp,
} from '../../../../apps/sync/ui/events/resources/calls.resource.js';
import { presenceResource } from '../../../../apps/sync/ui/events/resources/presence.resource.js';
import syncEn from '../../../../core/i18n/translations/en/sync.json' with { type: 'json' };
import '../../../../apps/sync/ui/components/sync-chat-list.js';

const FACTORIES = [
    channelsResource,
    companyMembersResource,
    chatUiResource,
    callUiResource,
    channelCreateAdhocCallOp,
    callInviteOp,
    presenceResource,
];

function seedSyncTranslations() {
    const bus = getPlatformBus();
    const previous = bus.getState().i18n.translations.en;
    bus.dispatch(
        CoreEvents.I18N_LOCALE_LOADED,
        { locale: 'en', bundle: { ...previous, sync: syncEn } },
        { source: 'system' },
    );
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: 'sync' },
        { source: 'system' },
    );
}

function seedChannels(count) {
    const items = [];
    for (let i = 0; i < count; i += 1) {
        items.push({
            channel_id: `ch-scroll-${i}`,
            name: `Meeting ${i}`,
            type: 'group',
            last_message_at: `2026-08-18T12:${String(i).padStart(2, '0')}:00Z`,
            last_message_preview: 'hello',
        });
    }
    getPlatformBus().dispatch(
        channelsResource.events.LIST_LOADED,
        { items },
        { source: 'local' },
    );
    getPlatformBus().dispatch(
        companyMembersResource.events.LIST_LOADED,
        { items: [] },
        { source: 'local' },
    );
}

function hitStackHasChannelRow(x, y) {
    const stack = document.elementsFromPoint(x, y);
    for (const node of stack) {
        if (node.tagName === 'SYNC-CHANNEL-ROW') return true;
        const root = node.getRootNode();
        if (root instanceof ShadowRoot && root.host && root.host.tagName === 'SYNC-CHANNEL-ROW') {
            return true;
        }
    }
    return false;
}

describe('sync-chat-list sidebar scroll clip', () => {
    beforeEach(() => {
        resetPlatformState();
        setDefaultI18nNamespace('sync');
        for (const factory of FACTORIES) registerFactory(factory);
        const collected = collectFactories(FACTORIES);
        bootstrapPlatformBus({
            baseUrl: '',
            routes: [],
            slices: collected.slices,
            effects: [],
        });
        seedSyncTranslations();
    });

    afterEach(() => fixtureCleanup());

    it('карточки ленты не наезжают на поиск и заголовок секции', async () => {
        const shell = await fixture(html`
            <div style="display:flex;flex-direction:column;height:360px;width:280px;overflow:hidden;">
                <sync-chat-list mode="sidebar"></sync-chat-list>
            </div>
        `);
        const list = shell.querySelector('sync-chat-list');
        seedChannels(24);
        await elementUpdated(list);
        await waitUntil(
            () => list.shadowRoot.querySelectorAll('sync-channel-row').length >= 8,
            'channel rows rendered',
        );

        const header = list.shadowRoot.querySelector('.header');
        const search = list.shadowRoot.querySelector('.search-box');
        const title = list.shadowRoot.querySelector('.section-title');
        const sectionContent = list.shadowRoot.querySelector('.section-content');
        expect(header).to.not.equal(null);
        expect(search).to.not.equal(null);
        expect(title).to.not.equal(null);
        expect(sectionContent).to.not.equal(null);

        const hostStyle = getComputedStyle(list);
        expect(hostStyle.overflow).to.equal('hidden');
        expect(sectionContent.scrollHeight).to.be.greaterThan(sectionContent.clientHeight);

        const headerTopBefore = header.getBoundingClientRect().top;
        sectionContent.scrollTop = 140;
        await elementUpdated(list);

        expect(header.getBoundingClientRect().top).to.equal(headerTopBefore);

        const searchBox = search.getBoundingClientRect();
        const titleBox = title.getBoundingClientRect();
        expect(hitStackHasChannelRow(searchBox.left + searchBox.width / 2, searchBox.top + searchBox.height / 2)).to.equal(false);
        expect(hitStackHasChannelRow(titleBox.left + titleBox.width / 2, titleBox.top + titleBox.height / 2)).to.equal(false);
    });
});
