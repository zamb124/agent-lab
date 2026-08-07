import { LINNEX_CATALOG_ID } from '../protocol/constants.js';

export function createFlowUIRenderContext(input) {
    if (!input?.document) throw new Error('flow-ui render context requires document');
    const document = input.document;
    return Object.freeze({
        document_id: document.document_id,
        document_revision: document.revision,
        snapshot_sequence: input.snapshotSequence || 0,
        state_hash: input.stateHash || '',
        page_id: input.pageId || document.active_page_id,
        surface_id: input.surfaceId || document.pages?.[document.active_page_id]?.root_surface_id || 'main',
        target_surface_profile_id: input.targetSurfaceProfileId || 'runtime.page.v1',
        display: input.display || 'page',
        viewport: Object.freeze({
            css_width: input.viewport?.css_width || 1440,
            css_height: input.viewport?.css_height || 900,
            device_pixel_ratio: input.viewport?.device_pixel_ratio || 1,
            safe_area: input.viewport?.safe_area || 'none',
            scrollbar_mode: input.viewport?.scrollbar_mode || 'overlay',
        }),
        renderer_build_hash: input.rendererBuildHash || 'flow-ui-dev',
        catalog_id: document.catalog_id || LINNEX_CATALOG_ID,
        catalog_manifest_checksum: input.catalogManifestChecksum || '',
        design_token_checksum: input.designTokenChecksum || '',
        font_manifest_checksum: input.fontManifestChecksum || '',
        asset_manifest_checksum: input.assetManifestChecksum || '',
        brand_id: input.brandId || 'linnex',
        resolved_host_profile: input.resolvedHostProfile || 'linnex.primary',
        theme: input.theme || 'auto',
        contrast: input.contrast || 'normal',
        reduced_motion: input.reducedMotion === true,
        locale: input.locale || 'ru',
        timezone: input.timezone || 'Europe/Moscow',
        direction: input.direction || 'ltr',
        viewer_permissions: Object.freeze([...(input.viewerPermissions || ['view', 'interact'])]),
        client_capabilities: Object.freeze({ ...(input.clientCapabilities || {}) }),
        data_model_hash: input.dataModelHash || '',
        task_projection_sequence: input.taskProjectionSequence || 0,
    });
}
