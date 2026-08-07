import { describe, expect, it } from 'vitest';

import { createFlowUIRenderContext } from '../../../../core/frontend/static/lib/flow-ui/rendering/render-context.js';
import {
    diffFlowUIRenderContexts,
    flowUIRenderFingerprint,
} from '../../../../core/frontend/static/lib/flow-ui/rendering/render-fingerprint.js';

function documentFixture() {
    return {
        document_id: 'flow-ui:ctx',
        revision: 3,
        catalog_id: 'https://linnex.io/a2ui/catalog/platform/v1',
        active_page_id: 'main',
        pages: { main: { page_id: 'main', root_surface_id: 'main' } },
        surfaces: {},
    };
}

describe('render-fingerprint', () => {
    it('is stable for identical contexts and changes when one field differs', () => {
        const left = createFlowUIRenderContext({
            document: documentFixture(),
            display: 'page',
            theme: 'dark',
            locale: 'ru',
            catalogManifestChecksum: 'abc',
        });
        const right = createFlowUIRenderContext({
            document: documentFixture(),
            display: 'page',
            theme: 'dark',
            locale: 'ru',
            catalogManifestChecksum: 'abc',
        });
        expect(flowUIRenderFingerprint(left)).toBe(flowUIRenderFingerprint(right));

        const changed = createFlowUIRenderContext({
            document: documentFixture(),
            display: 'page',
            theme: 'light',
            locale: 'ru',
            catalogManifestChecksum: 'abc',
        });
        expect(flowUIRenderFingerprint(changed)).not.toBe(flowUIRenderFingerprint(left));
        const diffs = diffFlowUIRenderContexts(left, changed);
        expect(diffs.some((item) => item.field === 'theme')).toBe(true);
    });
});
