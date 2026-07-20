/**
 * Bootstrap UI Flows: импорт <flows-app> + shell routes + CRUD modals.
 *
 * Editor stack (node/resource editors, editor-only modals) — в flow-editor-page.js.
 * Evaluation Lab — в flows-evaluation-page.js.
 */

import '@platform/lib/components/app-loader.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/glass-form-modal.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/glass-toast.js';
import '@platform/lib/components/platform-modal-stack.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/company-modal.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-notification-manager.js';
import '@platform/lib/components/layout/platform-island.js';
import '@platform/lib/components/platform-shell-page.js';

import './app/flows-app.js';

// Shell pages
import './pages/flows-home-page.js';
import './pages/chat-page.js';
import './pages/flow-editor-page.js';
import './pages/flows-evaluation-page.js';
import './pages/flows-agent-skills-page.js';

// Shell components
import './components/flows-sidebar.js';
import './components/flows-catalog-list.js';
import './components/flow-card.js';
import './components/branch-item.js';

// CRUD modals (home / catalog / chat)
import './modals/flows-flow-create-modal.js';
import './modals/flows-flow-edit-modal.js';
import './modals/flows-branch-create-modal.js';
import './modals/flows-sessions-modal.js';
import './modals/flows-mcp-servers-modal.js';
import './modals/flows-variable-editor-modal.js';
import './modals/flows-variables-modal.js';
import './modals/flows-trigger-editor-modal.js';
import './modals/flows-triggers-modal.js';
import './modals/flows-integrations-modal.js';
import './modals/flows-agent-skill-create-modal.js';
import './modals/flows-agent-skill-edit-modal.js';
import './modals/flows-agent-skill-import-modal.js';
import './modals/flows-agent-skill-picker-modal.js';
import './modals/flows-embedded-tool-config-modal.js';
import './modals/flows-library-picker-modal.js';

// Observability modals (chat + editor header)
import './modals/flows-tracing-modal.js';
import './modals/flows-span-details-modal.js';
import './modals/flows-logs-modal.js';
import './modals/flows-durable-history-modal.js';
import './modals/flows-browser-preview-modal.js';
import './modals/flows-preview-share-modal.js';

export { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';
export { platformVoiceDictationOp } from '@platform/lib/events/factories/platform-voice-dictation.js';
