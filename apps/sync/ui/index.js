/**
 * Bootstrap Sync UI: импорт <sync-app> + страниц + компонентов + модалок.
 *
 * Доменная логика — в `events/resources/*.resource.js` (factories с
 * `transport: 'ws'` + restMirror). Транспорт — единый platform WS
 * `/sync/api/ws/notifications` (см. `architecture.mdc`).
 */

import '@platform/lib/components/platform-notification-manager.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/glass-form-modal.js';
import '@platform/lib/components/platform-modal-stack.js';
import '@platform/lib/components/layout/platform-island.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/platform-user-info-modal.js';
import '@platform/lib/components/platform-audio-message-player.js';

import './app/sync-app.js';

import './pages/sync-shell-page.js';
import './pages/sync-channel-page.js';
import './pages/sync-calls-scheduled-page.js';
import './pages/sync-settings-page.js';
import './pages/sync-call-join-page.js';

import './components/sync-sidebar.js';
import './components/sync-channel-row.js';
import './components/sync-direct-member-row.js';
import './components/sync-chat-header.js';
import './components/sync-pin-strip.js';
import './components/sync-selection-bar.js';
import './components/sync-message-list.js';
import './components/sync-message-bubble.js';
import './components/sync-message-composer.js';
import './components/sync-message-context-menu.js';
import './components/sync-thread-drawer.js';
import './components/sync-channel-picker.js';

import './modals/sync-namespace-modal.js';
import './modals/sync-channel-create-modal.js';
import './modals/sync-channel-edit-modal.js';
import './modals/sync-channel-notifications-modal.js';
import './modals/sync-channel-members-add-modal.js';
import './modals/sync-call-link-create-modal.js';
import './modals/sync-call-link-edit-modal.js';
import './modals/sync-call-incoming-modal.js';
import './modals/sync-call-overlay-modal.js';
import './modals/sync-forward-modal.js';
