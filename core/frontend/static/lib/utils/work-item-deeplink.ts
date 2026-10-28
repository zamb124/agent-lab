/**
 * Deep link для WorkItem в сервисе worktracker.
 */

import { CoreEvents } from '../events/contract.js';
import type { PlatformBusLike } from '../events/bus-singleton.js';

const WORKTRACKER_BASE_PATH = '/worktracker';
const WORK_ITEM_TASK_PATH_PREFIX = `${WORKTRACKER_BASE_PATH}/tasks/`;

export function isWorktrackerAppPath(pathname: string): boolean {
    if (typeof pathname !== 'string' || pathname.length === 0) {
        throw new Error('isWorktrackerAppPath: pathname required');
    }
    return pathname === WORKTRACKER_BASE_PATH
        || pathname === `${WORKTRACKER_BASE_PATH}/`
        || pathname.startsWith(`${WORKTRACKER_BASE_PATH}/`);
}

export function isMobileViewport(): boolean {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
        return false;
    }
    return window.matchMedia('(max-width: 767px)').matches;
}

export function readWorkItemIdFromPathname(pathname: string): string {
    if (typeof pathname !== 'string' || pathname.length === 0) {
        return '';
    }
    if (!pathname.startsWith(WORK_ITEM_TASK_PATH_PREFIX)) {
        return '';
    }
    const rest = pathname.slice(WORK_ITEM_TASK_PATH_PREFIX.length);
    const segment = rest.split('/')[0];
    if (segment === undefined) {
        throw new Error('readWorkItemIdFromPathname: path segment missing');
    }
    if (segment.length === 0) {
        return '';
    }
    return decodeURIComponent(segment);
}

export function readWorkItemFromParam(locationLike: { search?: string } | null | undefined): string {
    if (!locationLike || typeof locationLike.search !== 'string') {
        return '';
    }
    const from = new URLSearchParams(locationLike.search).get('from');
    if (from === null) {
        return '';
    }
    if (typeof from !== 'string' || from.length === 0) {
        throw new Error('readWorkItemFromParam: from must be non-empty string');
    }
    return from;
}

export interface WorkItemDeeplinkOptions {
    from?: string;
    mode?: 'page' | 'panel';
}

export function buildWorkItemUrl(workItemId: string, options: WorkItemDeeplinkOptions = {}): string {
    if (typeof workItemId !== 'string' || workItemId.length === 0) {
        throw new Error('buildWorkItemUrl: workItemId required');
    }
    let url = `${WORK_ITEM_TASK_PATH_PREFIX}${encodeURIComponent(workItemId)}`;
    const params = new URLSearchParams();
    if (typeof options.from === 'string' && options.from.length > 0) {
        params.set('from', options.from);
    }
    const query = params.toString();
    if (query.length > 0) {
        url = `${url}?${query}`;
    }
    return url;
}

export function readWorkItemIdFromLocation(locationLike: { pathname?: string; search?: string } | null | undefined): string {
    if (!locationLike || typeof locationLike.pathname !== 'string') {
        throw new Error('readWorkItemIdFromLocation: location.pathname required');
    }
    const fromPath = readWorkItemIdFromPathname(locationLike.pathname);
    if (fromPath.length > 0) {
        return fromPath;
    }
    if (typeof locationLike.search !== 'string') {
        return '';
    }
    const params = new URLSearchParams(locationLike.search);
    const workItemId = params.get('work_item_id');
    if (workItemId === null) {
        return '';
    }
    if (typeof workItemId !== 'string' || workItemId.length === 0) {
        throw new Error('readWorkItemIdFromLocation: work_item_id must be non-empty string');
    }
    return workItemId;
}

export function hasLegacyWorkItemQuery(locationLike: { search?: string } | null | undefined): boolean {
    if (!locationLike || typeof locationLike.search !== 'string') {
        return false;
    }
    return new URLSearchParams(locationLike.search).has('work_item_id');
}

export function replaceWorkItemUrl(workItemId: string): void {
    if (typeof window === 'undefined' || typeof window.location === 'undefined') {
        return;
    }
    const url = new URL(window.location.href);
    if (readWorkItemIdFromPathname(url.pathname).length > 0) {
        return;
    }
    if (typeof workItemId === 'string' && workItemId.length > 0) {
        url.searchParams.set('work_item_id', workItemId);
        url.searchParams.set('view', 'detail');
    } else {
        url.searchParams.delete('work_item_id');
        url.searchParams.delete('view');
    }
    const next = `${url.pathname}${url.search}${url.hash}`;
    window.history.replaceState(window.history.state, '', next);
}

function _resolveOpenMode(options: WorkItemDeeplinkOptions): 'page' | 'panel' {
    if (options.mode === 'page' || options.mode === 'panel') {
        return options.mode;
    }
    if (isMobileViewport()) {
        return 'page';
    }
    return 'panel';
}

export function navigateToWorkItemPage(workItemId: string, bus: Pick<PlatformBusLike, 'dispatch'> | null | undefined, options: WorkItemDeeplinkOptions = {}): void {
    if (typeof workItemId !== 'string' || workItemId.length === 0) {
        throw new Error('navigateToWorkItemPage: workItemId required');
    }
    if (typeof window === 'undefined') {
        return;
    }
    if (isWorktrackerAppPath(window.location.pathname) && bus && typeof bus.dispatch === 'function') {
        const searchParams = new URLSearchParams();
        if (typeof options.from === 'string' && options.from.length > 0) {
            searchParams.set('from', options.from);
        }
        const search = searchParams.toString();
        bus.dispatch(
            CoreEvents.ROUTER_NAVIGATE_REQUESTED,
            {
                routeKey: 'work_item_detail',
                params: { workItemId },
                search: search.length > 0 ? `?${search}` : '',
            },
            { source: 'local' },
        );
        return;
    }
    window.location.href = buildWorkItemUrl(workItemId, options);
}

export function openWorkItemDetail(workItemId: string, bus: Pick<PlatformBusLike, 'dispatch'> | null | undefined, options: WorkItemDeeplinkOptions = {}): void {
    if (typeof workItemId !== 'string' || workItemId.length === 0) {
        throw new Error('openWorkItemDetail: workItemId required');
    }
    if (typeof window === 'undefined') {
        return;
    }
    const mode = _resolveOpenMode(options);
    if (!isWorktrackerAppPath(window.location.pathname)) {
        window.location.href = buildWorkItemUrl(workItemId, options);
        return;
    }
    if (!bus || typeof bus.dispatch !== 'function') {
        throw new Error('openWorkItemDetail: bus required inside worktracker SPA');
    }
    if (mode === 'page') {
        navigateToWorkItemPage(workItemId, bus, options);
        return;
    }
    replaceWorkItemUrl(workItemId);
    bus.dispatch(
        CoreEvents.PLATFORM_WORK_ITEM_DETAIL_OPEN_REQUESTED,
        { work_item_id: workItemId },
        { source: 'local' },
    );
}

export function navigateToWorkItem(workItemId: string, options: WorkItemDeeplinkOptions = {}): void {
    window.location.href = buildWorkItemUrl(workItemId, options);
}
