/**
 * Materialize a page starter into a minimal FlowUIDocument for gallery preview.
 */
import { LINNEX_CATALOG_ID } from '../../protocol/constants.js';
import { emptyFlowUIPage } from '../empty-page-template.js';
import { flowUIPageTemplate } from '../page-templates.js';

/**
 * @param {string} templateId
 * @param {'ru' | 'en'} locale
 */
export function buildFlowUIPageTemplatePreviewDocument(templateId, locale) {
    const template = flowUIPageTemplate(templateId);
    const surfaceId = 'main';
    const built = template.buildSurface(surfaceId, locale === 'ru' ? 'ru' : 'en');
    const page = emptyFlowUIPage(surfaceId);
    const title = template.title[locale === 'ru' ? 'ru' : 'en'];
    return Object.freeze({
        document_id: `preview:${template.template_id}:${template.version}`,
        catalog_id: LINNEX_CATALOG_ID,
        template_version: template.version,
        revision: 1,
        active_page_id: surfaceId,
        pages: Object.freeze({
            [surfaceId]: Object.freeze({
                ...page,
                title: Object.freeze({ default: title, translations: Object.freeze({}) }),
            }),
        }),
        surfaces: Object.freeze({
            [surfaceId]: Object.freeze({
                ...built,
                catalog_id: LINNEX_CATALOG_ID,
            }),
        }),
        policy: Object.freeze({}),
    });
}
