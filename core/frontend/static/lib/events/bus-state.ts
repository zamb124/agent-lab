/**
 * Состояние шины. Core-слайсы создаёт `buildPlatformReducer` вместе с bus,
 * поэтому к моменту `select` они уже есть. Слайс сервиса, которого нет
 * в этом интерфейсе, читается как `unknown`, пока фабрика его не добавит.
 */

import type { AuthState } from './reducers/auth.js';
import type { BottomSheetsState } from './reducers/bottom_sheets.js';
import type { CalendarState } from './reducers/calendar.js';
import type { CompaniesState } from './reducers/companies.js';
import type { FileTypesState } from './reducers/file-types.js';
import type { FilesState } from './reducers/files.js';
import type { I18nState } from './reducers/i18n.js';
import type { IconState } from './reducers/icon.js';
import type { MailState } from './reducers/mail.js';
import type { ModalsState } from './reducers/modals.js';
import type { NetworkState } from './reducers/network.js';
import type { NotificationsState } from './reducers/notifications.js';
import type { NotifyState } from './reducers/notify.js';
import type { PwaState } from './reducers/pwa.js';
import type { RouterState } from './reducers/router.js';
import type { TeamState } from './reducers/team.js';
import type { ThemeState } from './reducers/theme.js';
import type { UiState } from './reducers/ui.js';

export interface PlatformBusState {
    auth: AuthState;
    theme: ThemeState;
    i18n: I18nState;
    notify: NotifyState;
    modals: ModalsState;
    bottomSheets: BottomSheetsState;
    network: NetworkState;
    router: RouterState;
    pwa: PwaState;
    ui: UiState;
    icon: IconState;
    fileTypes: FileTypesState;
    files: FilesState;
    companies: CompaniesState;
    team: TeamState;
    calendar: CalendarState;
    mail: MailState;
    notifications: NotificationsState;
    [sliceKey: string]: unknown;
}
