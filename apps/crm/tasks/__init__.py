"""
CRM TaskIQ задачи.
"""

from apps.crm.tasks.attachment_tasks import (
    process_crm_attachment_task,
    delete_crm_attachment_task,
    delete_note_attachments_task,
    import_note_from_file_task,
)

__all__ = [
    "process_crm_attachment_task",
    "delete_crm_attachment_task",
    "delete_note_attachments_task",
    "import_note_from_file_task",
]

