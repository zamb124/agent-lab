/**
 * Files — общий аплоад файла в платформенный файловый API.
 *
 * Backend (`POST /crm/api/v1/files/`, multipart/form-data, поле `file`):
 *   200 → FileResponse { file_id, original_name, content_type, size_bytes,
 *                        download_url, ... }
 *
 * Возвращаемый объект используется wizard'ом импорта знаний для построения
 * `source_file_ids` в payload `taskKnowledgeImportStartOp`.
 */

import { createMultipartFileUploadOp } from '@platform/lib/events/index.js';

export const fileUploadOp = createMultipartFileUploadOp({
    name: 'crm/file_upload',
    url: '/crm/api/v1/files/',
});
