/**
 * Worktracker — точка входа Lit UI (ядро задач WorkItem).
 */

import '@platform/lib/utils/viewport-app-vh.js';
import '@platform/lib/utils/platform-deeplink-init.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/company-modal.js';
import './app/worktracker-app.js';

export { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';
