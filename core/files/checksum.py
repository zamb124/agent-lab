"""SHA-256 hex контрольная сумма содержимого байтов (канон с FileRecord.checksum при upload)."""

import hashlib


def compute_content_checksum_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
