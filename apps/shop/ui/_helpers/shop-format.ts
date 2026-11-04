/**
 * Чистые функции отображения каталога и меню: цена в minor-единицах, выход
 * блюда, аллергены, URL фото, иконка метки. Перевод передаётся вызывающим компонентом
 * (`this.t`).
 */

import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';
import type { ShopAllergen, ShopMeasureUnit } from '@platform/lib/events/wire/shop.gen.js';

export type ShopTranslate = (key: string, vars?: Record<string, string | number> | null) => string;

export function shopFileUrl(fileId: string): string {
    if (fileId === '') {
        throw new Error('shopFileUrl: fileId required');
    }
    return `/shop/api/v1/files/download/${fileId}`;
}

export function formatShopPrice(minor: number, locale: string): string {
    return formatPlatformNumber(minor / 100, locale, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

/** Цена из поля формы (рубли) → minor; `null` — пустое или невалидное значение. */
export function shopPriceMinor(value: unknown): number | null {
    const major = typeof value === 'number'
        ? value
        : typeof value === 'string' && value.trim() !== ''
            ? Number(value.replace(',', '.'))
            : Number.NaN;
    if (!Number.isFinite(major) || major < 0) {
        return null;
    }
    return Math.round(major * 100);
}

/** Иконка метки магазина: SVG path из каталога `shop/badge_icons_list`. */
export function shopBadgeSvg(iconPath: string): ReturnType<typeof unsafeHTML> {
    return unsafeHTML(`<svg viewBox="0 -960 960 960"><path d="${iconPath}"/></svg>`);
}

export function shopMeasureUnitLabel(unit: ShopMeasureUnit, t: ShopTranslate): string {
    switch (unit) {
        case 'g':
            return t('measure.g');
        case 'ml':
            return t('measure.ml');
        case 'pcs':
            return t('measure.pcs');
    }
}

/** Выход блюда «250 г»; пустая строка — выход не задан. */
export function formatShopMeasure(measure: number | null, unit: ShopMeasureUnit, t: ShopTranslate): string {
    if (measure === null) {
        return '';
    }
    return `${measure} ${shopMeasureUnitLabel(unit, t)}`;
}

export const SHOP_ALLERGENS: readonly ShopAllergen[] = [
    'gluten', 'dairy', 'egg', 'fish', 'shellfish', 'nuts', 'peanuts',
    'soy', 'sesame', 'mustard', 'celery', 'lupin', 'molluscs', 'sulphites',
];

export function shopAllergenLabel(allergen: ShopAllergen, t: ShopTranslate): string {
    switch (allergen) {
        case 'gluten': return t('allergens.gluten');
        case 'dairy': return t('allergens.dairy');
        case 'egg': return t('allergens.egg');
        case 'fish': return t('allergens.fish');
        case 'shellfish': return t('allergens.shellfish');
        case 'nuts': return t('allergens.nuts');
        case 'peanuts': return t('allergens.peanuts');
        case 'soy': return t('allergens.soy');
        case 'sesame': return t('allergens.sesame');
        case 'mustard': return t('allergens.mustard');
        case 'celery': return t('allergens.celery');
        case 'lupin': return t('allergens.lupin');
        case 'molluscs': return t('allergens.molluscs');
        case 'sulphites': return t('allergens.sulphites');
    }
}
