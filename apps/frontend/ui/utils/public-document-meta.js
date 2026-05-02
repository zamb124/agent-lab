/**
 * Обновление title и мета-тегов документа для публичных страниц (SEO / Open Graph).
 */

function _ensureMeta(attrName, attrValue) {
    let el = document.querySelector(`meta[${attrName}="${attrValue}"]`);
    if (!el) {
        el = document.createElement('meta');
        el.setAttribute(attrName, attrValue);
        document.head.appendChild(el);
    }
    return el;
}

function _setMetaName(name, content) {
    const el = _ensureMeta('name', name);
    el.setAttribute('content', content);
}

function _setMetaProperty(property, content) {
    const el = _ensureMeta('property', property);
    el.setAttribute('content', content);
}

/**
 * @param {{ title: string, description: string, canonicalUrl: string, ogImageUrl: string }} params
 */
export function applyPublicDocumentMeta(params) {
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
