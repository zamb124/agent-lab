import { describe, expect, it } from 'vitest';

import { createFlowUIRenderContext } from '../../../../core/frontend/static/lib/flow-ui/rendering/render-context.js';
import {
    applyFlowUIProfileKindOverrides,
    createLocalFlowUIProfile,
} from '../../../../core/frontend/static/lib/flow-ui/runtime/flow-ui-profile.js';
import { LINNEX_CATALOG_ID } from '../../../../core/frontend/static/lib/flow-ui/protocol/constants.js';

describe('render-context + profile', () => {
    it('freezes render context with document identity', () => {
        const context = createFlowUIRenderContext({
            document: {
                document_id: 'flow-ui:x',
                revision: 4,
                catalog_id: LINNEX_CATALOG_ID,
                active_page_id: 'main',
                pages: { main: { page_id: 'main', root_surface_id: 'main' } },
            },
            display: 'panel',
            theme: 'dark',
            locale: 'en',
        });
        expect(context.document_id).toBe('flow-ui:x');
        expect(context.document_revision).toBe(4);
        expect(context.display).toBe('panel');
        expect(Object.isFrozen(context)).toBe(true);
        expect(() => createFlowUIRenderContext({})).toThrow(/requires document/);
    });

    it('builds local editor profile with Linnex catalog only', () => {
        const profile = createLocalFlowUIProfile('editor_test');
        expect(profile.catalog.platform_catalog_id).toBe(LINNEX_CATALOG_ID);
        expect(profile.viewer.can_interact).toBe(true);
        expect(profile.capabilities.autosync).toBe(false);
        expect(() => createLocalFlowUIProfile('unknown')).toThrow(/Unknown Flow UI profile/);
    });

    it('forces autosync off for live editor_test without touching spa', () => {
        const live = Object.freeze({
            viewer: Object.freeze({ can_interact: true }),
            catalog: Object.freeze({ platform_catalog_id: LINNEX_CATALOG_ID }),
            capabilities: Object.freeze({
                bootstrap: true, autosync: true, cancel: true, files: true, voice: true,
            }),
        });
        const overridden = applyFlowUIProfileKindOverrides(live, 'editor_test');
        expect(overridden.capabilities.autosync).toBe(false);
        expect(overridden.capabilities.voice).toBe(true);
        expect(applyFlowUIProfileKindOverrides(live, 'spa').capabilities.autosync).toBe(true);
    });

    it('forces can_interact and disables autosync for operator_handoff', () => {
        const live = Object.freeze({
            viewer: Object.freeze({ can_interact: false }),
            catalog: Object.freeze({ platform_catalog_id: LINNEX_CATALOG_ID }),
            capabilities: Object.freeze({
                bootstrap: true, autosync: true, cancel: true, files: true, voice: true,
            }),
        });
        const overridden = applyFlowUIProfileKindOverrides(live, 'operator_handoff');
        expect(overridden.viewer.can_interact).toBe(true);
        expect(overridden.capabilities.autosync).toBe(false);
        expect(overridden.capabilities.voice).toBe(true);
    });
});
