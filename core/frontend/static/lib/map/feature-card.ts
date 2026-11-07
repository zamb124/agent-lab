/**
 * Карточка фичи карты — аналог балуна Яндекс.Карт для <platform-map>.
 *
 * Рендер — чистая функция в HTML-строку (MapLibre Popup принимает строку).
 * Для каждого канонического слоя — типизированная карточка по whitelist-
 * свойствам `apps/geo/layers.py`; неизвестный слой — читаемая таблица полей.
 * Hover-хинт — `featureTitle`: короткий заголовок без разметки.
 */

export interface FeatureCardInput {
    layer: string;
    properties: Record<string, unknown>;
}

type Translate = (key: string, vars?: Record<string, string | number> | null, namespace?: string) => string;

const _ESC_RE = /[&<>"]/g;
const _ESC_MAP: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
};

export function escHtml(v: unknown): string {
    return String(v ?? '').replace(_ESC_RE, (c) => _ESC_MAP[c]!);
}

/** Короткий заголовок фичи для hover-хинта и шапки карточки. */
export function featureTitle({ layer, properties }: FeatureCardInput): string {
    const display = properties['display_name'] ?? properties['name'];
    if (typeof display === 'string' && display !== '') return display;
    if (layer === 'addresses') {
        const joined = `${String(properties['street'] ?? '')} ${String(properties['housenumber'] ?? '')}`.trim();
        if (joined !== '') return joined;
    }
    if (layer === 'roads' && typeof properties['highway'] === 'string') {
        return properties['highway'];
    }
    if (layer === 'barriers' && typeof properties['barrier'] === 'string') {
        return properties['barrier'];
    }
    return layer;
}

const _NONEMPTY = (v: unknown): v is string => typeof v === 'string' && v !== '';

/** Локализованное значение: булевы/числовые/строковые — безопасный вывод. */
function _val(v: unknown): string {
    if (v === true) return 'yes';
    if (v === false) return 'no';
    return String(v ?? '');
}

/** Первое непустое строковое свойство по списку ключей. */
function _pick(properties: Record<string, unknown>, ...keys: string[]): string {
    for (const k of keys) {
        const v = properties[k];
        if (_NONEMPTY(v)) return v.trim();
    }
    return '';
}

/** URL только http(s)/относительный — javascript: и прочие схемы отсекаются. */
function _safeUrl(v: string): string {
    return /^(https?:\/\/|\/)/i.test(v) ? v : '';
}

function _row(label: string, value: string): string {
    return `<div class="pm-card-row"><span class="pm-card-row-k">${escHtml(label)}</span><span class="pm-card-row-v">${escHtml(value)}</span></div>`;
}

function _fmtLen(m: unknown): string {
    const n = Number(m);
    if (!Number.isFinite(n) || n <= 0) return '';
    return n >= 1000 ? `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)} km` : `${Math.round(n)} m`;
}

function _osm(kind: string, id: unknown): string {
    const v = String(id ?? '');
    return v === '' ? '' : `OSM ${kind} #${v}`;
}

export interface FeatureCardOptions {
    /** Кнопка «Маршрут» — точка назначения через `data-pm-action`. */
    routeTo?: boolean;
    /** Админ-действия слоя: скрыть объект / закрыть дорогу (`pm-feature-admin`). */
    admin?: boolean;
}

/** Типизированная карточка слоя: заголовок + значимая meta-строка. */
export function renderFeatureCard(
    input: FeatureCardInput,
    t: Translate,
    layerColor: string | null,
    opts: FeatureCardOptions = {},
): string {
    const { layer, properties } = input;
    const layerLabel = layer !== '' ? t(`layers.${layer}`, null, 'geo') : '';
    const chip =
        layerLabel !== '' && layerLabel !== `layers.${layer}`
            ? `<div class="pm-card-kind"><span class="pm-card-dot"${layerColor ? ` style="--chip:${escHtml(layerColor)}"` : ''}></span>${escHtml(layerLabel)}</div>`
            : '';

    // Яндекс-стиль rich-блоки — data-driven по свойствам фичи.
    const photo = _safeUrl(
        _pick(properties, 'photo', 'photo_url', 'image', 'image_url', 'picture', 'cover_url', 'cover'),
    );
    const rating = Number(properties['rating']);
    const reviews = Number(
        properties['reviews'] ?? properties['reviews_count'] ?? properties['ratings'] ?? properties['votes'],
    );
    const hours = _pick(properties, 'open_until', 'opening_hours', 'hours', 'schedule', 'working_hours');
    const website = _safeUrl(_pick(properties, 'website', 'url', 'site', 'contact_website'));
    const phone = _pick(properties, 'phone', 'phone_number', 'contact_phone');

    let title = featureTitle(input);
    let sub = '';
    let meta = '';
    let tags = '';
    const rows: string[] = [];

    switch (layer) {
        case 'addresses': {
            const street = String(properties['street'] ?? '');
            const house = String(properties['housenumber'] ?? '');
            const joined = `${street} ${house}`.trim();
            if (joined !== '') title = joined;
            sub = String(properties['city'] ?? '');
            break;
        }
        case 'roads': {
            const name = String(properties['name'] ?? '');
            if (name !== '') title = name;
            const parts: string[] = [];
            const len = _fmtLen(properties['length_m']);
            if (len !== '') parts.push(len);
            if (properties['oneway'] === true || properties['oneway'] === 'yes') parts.push(t('map.card_one_way', null, 'geo'));
            if (parts.length > 0) sub = parts.join(' · ');
            const osm = _osm('way', properties['osm_way_id']);
            if (osm !== '') meta = osm;
            break;
        }
        case 'barriers': {
            const kind = String(properties['barrier'] ?? '');
            const kindLabel = kind !== '' ? t(`map.card_barrier_${kind}`, null, 'geo') : '';
            if (kindLabel !== '' && kindLabel !== `map.card_barrier_${kind}`) title = kindLabel;
            else if (kind !== '') title = kind;
            const blocked = (['car', 'foot', 'bike', 'scooter'] as const).filter(
                (mode) => properties[`block_${mode}`] === true,
            );
            const icons: Record<string, string> = { car: '🚗', foot: '🚶', bike: '🚲', scooter: '🛴' };
            if (blocked.length > 0) {
                tags = `<div class="pm-card-tags" title="${escHtml(t('map.card_blocks', null, 'geo'))}">${blocked
                    .map((mode) => `<span class="pm-card-tag">${icons[mode]}</span>`)
                    .join('')}</div>`;
            }
            const osm = _osm('node', properties['osm_node_id']);
            if (osm !== '') meta = osm;
            break;
        }
        case 'restrictions': {
            const kind = String(properties['restriction'] ?? '');
            const kindLabel = kind !== '' ? t(`map.card_restriction_${kind}`, null, 'geo') : '';
            if (kindLabel !== '' && kindLabel !== `map.card_restriction_${kind}`) title = kindLabel;
            else if (kind !== '') title = kind;
            const parts = [_osm('relation', properties['osm_relation_id'])];
            const fromTo = [properties['from_way'], properties['to_way']]
                .map((v) => String(v ?? ''))
                .filter((v) => v !== '')
                .join(' → ');
            if (fromTo !== '') parts.push(fromTo);
            meta = parts.filter((v) => v !== '').join(' · ');
            break;
        }
        case 'regions': {
            const regTitle = String(properties['title'] ?? '');
            if (regTitle !== '') title = regTitle;
            const parts = [String(properties['kind'] ?? ''), String(properties['name'] ?? '')].filter((v) => v !== '');
            if (parts.length > 0) sub = parts.join(' · ');
            if (properties['enabled'] === true) meta = t('map.card_enabled', null, 'geo');
            else if (properties['enabled'] === false) meta = t('map.card_disabled', null, 'geo');
            break;
        }
        case 'signals': {
            title = t('map.card_signal', null, 'geo');
            const osm = _osm('node', properties['osm_node_id']);
            if (osm !== '') meta = osm;
            break;
        }
        case 'buildings': {
            const kn = _pick(properties, 'cadastral_number');
            const addr = _pick(properties, 'address');
            if (addr !== '') title = addr;
            else if (kn !== '') title = kn;
            const src = _pick(properties, 'source');
            const parts = [
                kn !== '' ? `${t('map.card_kn', null, 'geo')} ${kn}` : '',
                src,
            ].filter((v) => v !== '');
            if (parts.length > 0) meta = parts.join(' · ');
            break;
        }
        default: {
            // Неизвестный слой — читаемая таблица первых полей.
            for (const [k, v] of Object.entries(properties)) {
                if (k === 'layer' || k.startsWith('__') || v === '' || v === null || v === undefined) continue;
                if (rows.length >= 6) break;
                rows.push(_row(k.replace(/_/g, ' '), _val(v)));
            }
        }
    }

    const coords = properties['__coords'] as string | undefined;
    const footer =
        coords !== undefined
            ? `<div class="pm-card-footer"><span class="pm-card-coords">${escHtml(coords)}</span></div>`
            : meta !== ''
              ? `<div class="pm-card-footer"><span class="pm-card-meta">${escHtml(meta)}</span></div>`
              : '';
    const metaRow = coords !== undefined && meta !== '' ? `<div class="pm-card-meta">${escHtml(meta)}</div>` : '';

    const hero = photo !== '' ? `<img class="pm-card-hero" src="${escHtml(photo)}" alt="" loading="lazy" />` : '';

    let ratingRow = '';
    if (Number.isFinite(rating) && rating > 0) {
        const pct = Math.max(0, Math.min(100, (rating / 5) * 100));
        const reviewsTxt =
            Number.isFinite(reviews) && reviews > 0
                ? ` ${t('map.card_reviews', { count: reviews }, 'geo')}`
                : '';
        ratingRow =
            `<div class="pm-card-rating">` +
            `<span class="pm-card-stars"><span class="pm-card-stars-bg">★★★★★</span>` +
            `<span class="pm-card-stars-fill" style="width:${pct}%">★★★★★</span></span>` +
            `<span class="pm-card-rating-v">${rating.toFixed(1)}</span>` +
            `<span class="pm-card-rating-n">${escHtml(reviewsTxt)}</span></div>`;
    }

    const subParts = [hours, sub].filter((v) => v !== '');
    const subRow = subParts.length > 0 ? `<div class="pm-card-sub">${escHtml(subParts.join(' · '))}</div>` : '';

    const actions: string[] = [];
    if (opts.routeTo === true) {
        actions.push(
            `<button type="button" class="pm-card-act pm-card-act-primary" data-pm-action="route-here">${escHtml(t('map.card_route', null, 'geo'))}</button>`,
        );
    }
    if (website !== '') {
        actions.push(
            `<a class="pm-card-act" href="${escHtml(website)}" target="_blank" rel="noopener noreferrer">${escHtml(t('map.card_site', null, 'geo'))}</a>`,
        );
    }
    if (phone !== '') {
        actions.push(
            `<a class="pm-card-act" href="tel:${escHtml(phone.replace(/[^+\d]/g, ''))}">${escHtml(t('map.card_call', null, 'geo'))}</a>`,
        );
    }
    if (opts.admin === true) {
        if (layer === 'roads') {
            const wayId = Number(properties['osm_way_id']);
            if (Number.isFinite(wayId) && wayId !== 0) {
                actions.push(
                    `<button type="button" class="pm-card-act pm-card-act-danger" data-pm-action="edge-close" data-osm-id="${wayId}">${escHtml(t('map.card_close_road', null, 'geo'))}</button>`,
                );
            }
        } else if (layer === 'barriers' || layer === 'signals' || layer === 'restrictions') {
            const entity = layer === 'barriers' ? 'barrier' : layer === 'signals' ? 'signal' : 'restriction';
            const idKey = entity === 'restriction' ? 'osm_relation_id' : 'osm_node_id';
            const osmId = Number(properties[idKey]);
            if (Number.isFinite(osmId) && osmId !== 0) {
                actions.push(
                    `<button type="button" class="pm-card-act pm-card-act-danger" data-pm-action="feature-suppress" data-entity="${entity}" data-osm-id="${osmId}">${escHtml(t('map.card_hide', null, 'geo'))}</button>`,
                );
            }
        }
    }
    const actionsRow = actions.length > 0 ? `<div class="pm-card-actions">${actions.join('')}</div>` : '';

    if (title === '' && sub === '' && rows.length === 0 && meta === '' && hero === '') return '';
    return (
        `<div class="pm-card">${hero}${chip}` +
        `<div class="pm-card-title">${escHtml(title)}</div>` +
        ratingRow +
        subRow +
        (rows.length > 0 ? `<div class="pm-card-rows">${rows.join('')}</div>` : '') +
        tags +
        actionsRow +
        metaRow +
        footer +
        `</div>`
    );
}
