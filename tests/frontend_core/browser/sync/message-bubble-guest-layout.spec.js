/**
 * Бабл Sync: гость без сырого id, mic+From audio на одной линии, текст без воздуха шаблона.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { bootstrapPlatformBus, collectFactories, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { channelsResource } from '../../../../apps/sync/ui/events/resources/channels.resource.js';
import { chatUiResource } from '../../../../apps/sync/ui/events/resources/chat-ui.resource.js';
import {
    messagesReactOp,
    messagesStoreSlice,
    messagesTranscribeAudioOp,
    messagesTranscribeCallOp,
    messagesTranscribeVideoOp,
} from '../../../../apps/sync/ui/events/resources/messages.resource.js';
import { callAcceptOp } from '../../../../apps/sync/ui/events/resources/calls.resource.js';
import syncEn from '../../../../core/i18n/translations/en/sync.json' with { type: 'json' };
import '../../../../apps/sync/ui/components/sync-message-bubble.js';

const TOKENS_HREF = '/core/frontend/static/assets/css/tokens.css';

const FACTORIES = [
    channelsResource,
    chatUiResource,
    messagesStoreSlice,
    messagesReactOp,
    messagesTranscribeAudioOp,
    messagesTranscribeVideoOp,
    messagesTranscribeCallOp,
    callAcceptOp,
];

function loadTokens() {
    return new Promise((resolve, reject) => {
        const existing = document.querySelector(`link[rel="stylesheet"][href="${TOKENS_HREF}"]`);
        if (existing) {
            resolve();
            return;
        }
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = TOKENS_HREF;
        link.onload = () => resolve();
        link.onerror = () => reject(new Error(`tokens.css: ${TOKENS_HREF}`));
        document.head.appendChild(link);
    });
}

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

function guestSpeechMessage() {
    return {
        message_id: 'm-guest-speech',
        channel_id: 'ch-meeting',
        sent_at: '2026-09-17T12:07:00Z',
        sender: {
            user_id: 'guest:8890baea:артем',
            display_name: 'guest:8890baea:артем',
            avatar_url: null,
        },
        contents: [
            {
                type: 'text/plain',
                data: { body: 'привееет!!!', origin: 'speech' },
            },
        ],
        reactions: [],
    };
}

function ownShortDmMessage() {
    return {
        message_id: 'm-own-short',
        channel_id: 'ch-dm',
        sent_at: '2026-09-17T12:08:00Z',
        sender: {
            user_id: 'user-me',
            display_name: 'Viktor',
            avatar_url: null,
        },
        contents: [
            {
                type: 'text/plain',
                data: { body: 'Хехе' },
            },
        ],
        reactions: [],
    };
}

describe('sync-message-bubble guest / speech / compact text', () => {
    beforeEach(async () => {
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
        await loadTokens();
    });

    afterEach(() => fixtureCleanup());

    it('гость: иконка user + имя, сырой id не показывается', async () => {
        const el = await fixture(html`
            <sync-message-bubble
                .message=${guestSpeechMessage()}
                my-user-id="user-me"
                data-position="single"
            ></sync-message-bubble>
        `);
        await elementUpdated(el);
        const root = el.shadowRoot;
        const sender = root.querySelector('.sender');
        expect(sender).to.not.equal(null);
        expect(sender.textContent).to.equal('артем');
        expect(sender.textContent.includes('guest:')).to.equal(false);
        expect(sender.classList.contains('guest')).to.equal(true);

        const avatar = root.querySelector('.avatar.guest');
        expect(avatar).to.not.equal(null);
        const icon = avatar.querySelector('platform-icon');
        expect(icon).to.not.equal(null);
        expect(icon.getAttribute('name')).to.equal('user');

        const events = [];
        getPlatformBus().subscribeAny((e) => events.push(e));
        sender.click();
        const modal = events.find((e) => e.type === CoreEvents.UI_MODAL_OPEN);
        expect(modal).to.equal(undefined);
    });

    it('From audio: mic и подпись на одной вертикали, без whitespace-flex', async () => {
        const el = await fixture(html`
            <sync-message-bubble
                .message=${guestSpeechMessage()}
                my-user-id="user-me"
                data-position="single"
            ></sync-message-bubble>
        `);
        await elementUpdated(el);
        const origin = el.shadowRoot.querySelector('.speech-origin');
        expect(origin).to.not.equal(null);
        const textNodes = [...origin.childNodes].filter(
            (n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim() !== '',
        );
        expect(textNodes.length).to.equal(0);
        expect(origin.children.length).to.equal(2);

        const icon = origin.querySelector('platform-icon');
        const label = origin.querySelector('span');
        expect(icon).to.not.equal(null);
        expect(label).to.not.equal(null);
        expect(label.textContent).to.equal('From audio');

        const originStyle = getComputedStyle(origin);
        // Flex-item внутри .body--speech: computed display блочится в flex.
        expect(originStyle.display === 'flex' || originStyle.display === 'inline-flex').to.equal(true);
        expect(originStyle.alignItems).to.equal('center');
        expect(originStyle.whiteSpace).to.equal('nowrap');

        const iconBox = icon.getBoundingClientRect();
        const labelBox = label.getBoundingClientRect();
        const iconMid = (iconBox.top + iconBox.bottom) / 2;
        const labelMid = (labelBox.top + labelBox.bottom) / 2;
        expect(Math.abs(iconMid - labelMid)).to.be.lessThan(2);
    });

    it('короткий свой текст: pre-wrap только на body-text, пузырь без индента шаблона', async () => {
        const el = await fixture(html`
            <div style="width: 420px;">
                <sync-message-bubble
                    .message=${ownShortDmMessage()}
                    my-user-id="user-me"
                    data-position="single"
                ></sync-message-bubble>
            </div>
        `);
        const bubbleEl = el.querySelector('sync-message-bubble');
        await elementUpdated(bubbleEl);
        const root = bubbleEl.shadowRoot;
        const body = root.querySelector('.body');
        const bodyText = root.querySelector('.body-text');
        const bubble = root.querySelector('.bubble');
        expect(body).to.not.equal(null);
        expect(bodyText).to.not.equal(null);
        expect(bubble).to.not.equal(null);

        expect(getComputedStyle(body).whiteSpace).to.equal('normal');
        expect(getComputedStyle(bodyText).whiteSpace).to.equal('pre-wrap');
        expect(bodyText.textContent).to.equal('Хехе');

        const bubbleBox = bubble.getBoundingClientRect();
        const textBox = bodyText.getBoundingClientRect();
        expect(bubbleBox.height).to.be.lessThan(textBox.height + 48);
        expect(bubbleBox.width).to.be.lessThan(220);
    });
});
