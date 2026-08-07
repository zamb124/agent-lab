"""Flow UI submit FileUpload → state.files + [FILE] content canon."""

from __future__ import annotations

from core.models.flow_interface import build_default_chat_document
from core.state.flow_ui_contract import (
    build_flow_ui_submit_contract,
    flow_ui_submit_file_refs,
)


def test_flow_ui_submit_file_refs_from_composer_upload() -> None:
    document = build_default_chat_document()
    contract = build_flow_ui_submit_contract(
        document,
        surface_id="main",
        values={
            "message": "что в файле",
            "files": [
                {
                    "file_id": "file_e82cc35e2182",
                    "url": "/flows/api/v1/files/download/file_e82cc35e2182",
                    "content_type": "image/jpeg",
                    "file_size": 1742772,
                    "original_name": "IMG_2444.JPG",
                }
            ],
        },
    )
    refs = flow_ui_submit_file_refs(contract)
    assert len(refs) == 1
    assert refs[0].file_id == "file_e82cc35e2182"
    assert refs[0].original_name == "IMG_2444.JPG"
    assert refs[0].content_type == "image/jpeg"


def test_flow_ui_submit_content_uses_file_blocks_not_bullet_list() -> None:
    document = build_default_chat_document()
    contract = build_flow_ui_submit_contract(
        document,
        surface_id="main",
        values={
            "message": "",
            "files": [
                {
                    "file_id": "file_b7c6aba8694b",
                    "url": "/flows/api/v1/files/download/file_b7c6aba8694b",
                    "content_type": (
                        "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document"
                    ),
                    "file_size": 33009,
                    "original_name": "ТЗ_Виджет_KYC_v1.2.docx",
                }
            ],
        },
    )
    assert "[FILE]" in contract.content
    assert "[/FILE]" in contract.content
    assert "original_name: ТЗ_Виджет_KYC_v1.2.docx" in contract.content
    assert "url: /flows/api/v1/files/download/file_b7c6aba8694b" in contract.content
    assert "**files:**" not in contract.content
    assert "- ТЗ_Виджет_KYC_v1.2.docx" not in contract.content


def test_flow_ui_submit_message_plus_file_appends_file_block() -> None:
    document = build_default_chat_document()
    contract = build_flow_ui_submit_contract(
        document,
        surface_id="main",
        values={
            "message": "разбери файл",
            "files": [
                {
                    "file_id": "file_abc",
                    "url": "/flows/api/v1/files/download/file_abc",
                    "content_type": "application/pdf",
                    "file_size": 10,
                    "original_name": "a.pdf",
                }
            ],
        },
    )
    assert contract.content.startswith("разбери файл\n[FILE]\n")
    assert "original_name: a.pdf" in contract.content


def test_flow_ui_submit_file_refs_empty_without_upload() -> None:
    document = build_default_chat_document()
    contract = build_flow_ui_submit_contract(
        document,
        surface_id="main",
        values={"message": "привет", "files": []},
    )
    assert flow_ui_submit_file_refs(contract) == []
