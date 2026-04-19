/**
 * Публичный фасад модуля core events. Импорт через:
 *   import { dispatch, select, CoreEvents, ... } from '@platform/lib/events/index.js';
 *
 * Это единственный API, который компоненты Lit и сервисные effects должны
 * использовать. Прямые обращения к bus.js / log.js / *.effect.js — только
 * внутри платформы и внутри bootstrap'а сервиса.
 */

export { EventBus } from './bus.js';
export { EventLog } from './log.js';
export { CoreEvents, CORE_SCOPES, createEvent, assertEventType } from './contract.js';
export { createSelector, selectorFamily, pluck } from './selectors.js';
export { SelectController } from './select-controller.js';
export {
    setPlatformBus,
    getPlatformBus,
    hasPlatformBus,
    resetPlatformBusForTests,
} from './bus-singleton.js';
export { bootstrapPlatformBus, completeBootstrap } from './bootstrap.js';
export { buildPlatformReducer, combineReducers, coreSlices } from './reducers/index.js';
export { translate } from './effects/i18n.effect.js';
export { httpRequest, httpStream, HttpError } from './http.js';

export { CoreAuthEvents } from './effects/auth.effect.js';
export { ICON_EVENTS } from './reducers/icon.js';
export { FILE_TYPES_EVENTS, selectExtensionsFor, selectMimesFor, selectAcceptStringFor, selectIsAllowedFile } from './reducers/file-types.js';
export { FILES_EVENTS, buildFileDownloadUrl } from './reducers/files.js';
export { COMPANIES_EVENTS } from './reducers/companies.js';
export { TEAM_EVENTS } from './reducers/team.js';
export { CALENDAR_EVENTS } from './reducers/calendar.js';
export { NOTIFICATIONS_EVENTS } from './reducers/notifications.js';
export { PWA_EVENTS } from './effects/pwa.effect.js';
export { I18N_NAMESPACE_SET_REQUESTED } from './reducers/i18n.js';

export { createAsyncOp } from './factories/async-op.js';
export { createResourceCollection } from './factories/resource-collection.js';
export { createCursorList } from './factories/cursor-list.js';
export { createFacets } from './factories/facets.js';
export { createForm } from './factories/form.js';
export { createSlice } from './factories/slice.js';
export { collectFactories, resources } from './factories/register.js';
export { registerFactory, getFactory, hasFactory, clearFactoryRegistry } from './factory-registry.js';
export { platformWs, WsTransportError } from './effects/ws.effect.js';
