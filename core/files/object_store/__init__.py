"""Единственный вход к байтам объектного хранилища."""

from core.files.object_store.gate import FileGate, FileHandle
from core.files.object_store.principals import (
    AnonymousPrincipal,
    ExecutionPrincipal,
    FilePrincipal,
    SessionPrincipal,
    SignedFileGrant,
    SystemPrincipal,
)

__all__ = [
    "AnonymousPrincipal",
    "ExecutionPrincipal",
    "FileGate",
    "FileHandle",
    "FilePrincipal",
    "SessionPrincipal",
    "SignedFileGrant",
    "SystemPrincipal",
]
