/**
 * Обновление title и мета-тегов документа для публичных страниц (SEO / Open Graph).
 */

import { isI18nBundleReady } from '@platform/lib/events/effects/i18n.effect.js';
import type { ReactiveController } from 'lit';
import type { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';

/**
 * Синк document meta после загрузки i18n-бандла.
 *
 * `connectedCallback`/`queueMicrotask` бегут до ответа `/api/i18n/<locale>` —
 * `t()` тогда отдаёт сырой ключ и он запекается в title снапшота и вкладки.
 * Контроллер ждёт `isI18nBundleReady` и синкает один раз на локаль.
 */
export class PublicDocumentMetaSyncController implements ReactiveController {
    private _readyLocale: SelectController<string>;
    private _applied: string = '';

    constructor(host: PlatformElement, private _sync: () => void) {
        host.addController(this);
        this._readyLocale = host.select((s) => (isI18nBundleReady(s.i18n) ? s.i18n.locale : ''));
    }

    hostUpdated(): void {
        const locale = this._readyLocale.value;
        if (locale === '' || locale === this._applied) return;
        this._applied = locale;
        this._sync();
    }
}

function _ensureMeta(attrName: string, attrValue: string) {
    let el = document.querySelector(`meta[${attrName}="${attrValue}"]`);
    if (!el) {
        el = document.createElement('meta');
        el.setAttribute(attrName, attrValue);
        document.head.appendChild(el);
    }
    return el;
}

function _setMetaName(name: string, content: string) {
    const el = _ensureMeta('name', name);
    el.setAttribute('content', content);
}

function _setMetaProperty(property: string, content: string) {
    const el = _ensureMeta('property', property);
    el.setAttribute('content', content);
}

/**
 * @param {{ title: string, description: string, canonicalUrl: string, ogImageUrl: string }} params
 */
export function applyPublicDocumentMeta(params: { title?: unknown; description?: unknown; canonicalUrl?: unknown; ogImageUrl?: unknown }) {
    if (typeof document === 'undefined') {
        return;
    }
    const title = params.title;
    const description = params.description;
    const canonicalUrl = params.canonicalUrl;
    const ogImageUrl = params.ogImageUrl;
    if (typeof title !== 'string' || title === '') {
        throw new Error('applyPublicDocumentMeta: title required');
    }
    if (typeof description !== 'string' || description === '') {
        throw new Error('applyPublicDocumentMeta: description required');
    }
    if (typeof canonicalUrl !== 'string' || canonicalUrl === '') {
        throw new Error('applyPublicDocumentMeta: canonicalUrl required');
    }
    if (typeof ogImageUrl !== 'string' || ogImageUrl === '') {
        throw new Error('applyPublicDocumentMeta: ogImageUrl required');
    }

    document.title = title;
    _setMetaName('description', description);
    _setMetaProperty('og:title', title);
    _setMetaProperty('og:description', description);
    _setMetaProperty('og:url', canonicalUrl);
    _setMetaProperty('og:image', ogImageUrl);
    _setMetaName('twitter:title', title);
    _setMetaName('twitter:description', description);
    _setMetaName('twitter:image', ogImageUrl);

    let link = document.querySelector('link[rel="canonical"]');
    if (!link) {
        link = document.createElement('link');
        link.setAttribute('rel', 'canonical');
        document.head.appendChild(link);
    }
    link.setAttribute('href', canonicalUrl);
}
