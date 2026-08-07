import { describe, expect, it } from 'vitest';
import { buildFlowUIPageTemplatePreviewDocument } from '../../../../core/frontend/static/lib/flow-ui/templates/gallery/preview-document.js';
import { FLOW_UI_PAGE_TEMPLATES } from '../../../../core/frontend/static/lib/flow-ui/templates/page-templates.js';
import { LINNEX_CATALOG_ID } from '../../../../core/frontend/static/lib/flow-ui/protocol/constants.js';
import { validateInterfaceDocument } from '../../../../apps/flows/ui/components/interface-editor/interface-editor-domain.js';

describe('page template preview document', () => {
    it('materializes every template into a catalog-backed document with submit', () => {
        for (const template of FLOW_UI_PAGE_TEMPLATES) {
            const document = buildFlowUIPageTemplatePreviewDocument(template.template_id, 'en');
            expect(document.catalog_id).toBe(LINNEX_CATALOG_ID);
            expect(document.active_page_id).toBe('main');
            expect(document.surfaces.main.root_component_id).toBe('root');
            expect(document.document_id).toContain(template.template_id);

            const blocking = validateInterfaceDocument(document)
                .filter((problem) => problem.severity === 'error');
            expect(blocking, `${template.template_id}: ${JSON.stringify(blocking)}`).toEqual([]);
        }
    });

    it('localizes preview page title from template metadata', () => {
        const en = buildFlowUIPageTemplatePreviewDocument('linnex.page.login', 'en');
        const ru = buildFlowUIPageTemplatePreviewDocument('linnex.page.login', 'ru');
        expect(en.pages.main.title.default).toBe('Login form');
        expect(ru.pages.main.title.default).toBe('Вход');
    });
});
