"""SHA-256 hex контрольная сумма содержимого байтов (канон с FileRecord.checksum при upload)."""

import hashlib


def compute_content_checksum_sha256(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data must be bytes")
    return hashlib.sha256(data).hexdigest()
