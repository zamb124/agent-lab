export function emptyFlowUIPage(pageId = 'page') {
    return Object.freeze({
        page_id: pageId,
        title: { default: 'Untitled page', translations: {} },
        route: `/${pageId}`,
        root_surface_id: pageId,
        navigation: { visible: true, allow_back: true, allow_direct: true },
        default_target_profile_id: 'runtime',
    });
}
