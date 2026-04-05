"""
Vision Analyze - универсальный анализ изображений через multimodal LLM.
Агент сам формулирует prompt для анализа.
"""

from typing import Optional

from apps.flows.src.tools import tool


def _vision_mock(args: dict, state=None) -> dict:
    """Mock для тестов с валидацией файлов."""
    from pathlib import Path

    prompt = args.get("prompt", "")
    
    SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"}
    
    if state is not None:
        files = getattr(state, "files", None)
        if files is None and isinstance(state, dict):
            files = state.get("files", [])
        files = files or []
        
        if not files:
            return {"success": False, "error": "Нет файлов для анализа"}
        
        file_name = args.get("file_name")
        if file_name:
            file_info = next((f for f in files if f.get("name") == file_name), None)
            if file_info is None:
                available = [f.get("name") for f in files]
                return {
                    "success": False,
                    "error": f"Файл '{file_name}' не найден. Доступные: {available}",
                }
        else:
            file_info = files[0]
        
        mime_type = file_info.get("mime_type")
        if mime_type and mime_type not in SUPPORTED_MIME_TYPES:
            return {"success": False, "error": f"Неподдерживаемый тип файла: {mime_type}"}
        
        file_path = file_info.get("path")
        if file_path and not Path(file_path).exists():
            return {"success": False, "error": f"Файл не найден: {file_path}"}
        
        resolved_name = file_info.get("name", "first_file")
    else:
        resolved_name = args.get("file_name") or "first_file"
    
    return {
        "success": True,
        "result": f"Mock vision result for: {prompt[:50]}",
        "file_name": resolved_name,
        "model": args.get("model", "mock"),
    }


@tool(
    name="vision_analyze",
    description=(
        "Анализирует изображение с помощью multimodal LLM. "
        "Агент сам формулирует prompt для анализа. "
        "file_name - название файла (если не указано, берется первый файл). "
        "json_output - запросить JSON формат ответа. "
        "model - модель (по умолчанию gemini-2.5-pro-preview). "
        "Примеры prompt:\n"
        "- 'Извлеки весь текст с изображения'\n"
        "- 'Найди серию и номер паспорта в JSON формате'\n"
        "- 'Опиши что изображено на фото'\n"
        "- 'Извлеки таблицу в markdown'"
    ),
    tags=["vision", "ocr", "image"],
    mock_response=_vision_mock,
)
async def vision_analyze(
    prompt: str,
    file_name: Optional[str] = None,
    json_output: bool = False,
    model: str = "gemini-2.5-pro-preview",
    state: Optional[dict] = None,
) -> dict:
    """
    Универсальный анализ изображения через vision LLM.
    
    ВСЯ логика inline - SafeEval должен видеть все импорты и функции.
    """
    import base64
    import mimetypes
    import uuid
    from pathlib import Path
    
    import fitz
    from a2a.types import FilePart, FileWithBytes, Message, Part, Role, TextPart
    
    from core.clients.llm.factory import get_vision_llm
    from core.logging import get_logger
    from core.models.billing_models import UsageType
    from core.tracing.operation_span import traced_operation
    
    logger = get_logger(__name__)
    
    SUPPORTED_MIME_TYPES = {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "application/pdf",
    }
    
    # === Helper functions inline ===
    
    def detect_mime_type(file_path: str) -> str:
        """Определяет MIME тип файла."""
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "application/octet-stream"
    
    def convert_pdf_to_image(file_path: str, page_num: int = 0) -> tuple:
        """Конвертирует страницу PDF в PNG изображение."""
        doc = fitz.open(file_path)
        if page_num >= len(doc):
            page_num = 0
        page = doc[page_num]
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        doc.close()
        return base64.b64encode(img_bytes).decode("utf-8"), "image/png"
    
    def find_file(files: list, name: str | None) -> dict | None:
        """Находит файл в списке по имени или возвращает первый."""
        if not files:
            return None
        if not name:
            return files[0]
        for f in files:
            if f.get("name") == name:
                return f
        # Частичное совпадение
        name_lower = name.lower()
        for f in files:
            if name_lower in f.get("name", "").lower():
                return f
        return None
    
    # === Main logic ===
    
    state = state or {}
    files = state.get("files", [])
    
    if not files:
        return {"success": False, "error": "Нет файлов для анализа"}
    
    file_info = find_file(files, file_name)
    if not file_info:
        available = [f.get("name") for f in files]
        return {
            "success": False, 
            "error": f"Файл '{file_name}' не найден. Доступные: {available}"
        }
    
    file_path = file_info.get("path")
    mime_type = file_info.get("mime_type") or detect_mime_type(file_path)
    
    if mime_type not in SUPPORTED_MIME_TYPES:
        return {"success": False, "error": f"Неподдерживаемый тип файла: {mime_type}"}
    
    path = Path(file_path)
    if not path.exists():
        return {"success": False, "error": f"Файл не найден: {file_path}"}
    
    # Конвертируем PDF в изображение
    if mime_type == "application/pdf":
        b64_data, actual_mime = convert_pdf_to_image(file_path)
    else:
        file_bytes = path.read_bytes()
        b64_data = base64.b64encode(file_bytes).decode("utf-8")
        actual_mime = mime_type
    
    # Формируем A2A Message с TextPart + FilePart
    message = Message(
        message_id=str(uuid.uuid4()),
        role=Role.user,
        parts=[
            Part(root=TextPart(text=prompt)),
            Part(root=FilePart(
                file=FileWithBytes(
                    bytes=b64_data,
                    mime_type=actual_mime,
                    name=file_info.get("name", "image"),
                )
            )),
        ],
    )
    
    logger.info(f"Vision analyze: model={model}, prompt_len={len(prompt)}, file={file_info.get('name')}")
    
    llm = get_vision_llm(model_name=model)

    async with traced_operation(
        "flows.tools.ocr_vision",
        event_type="llm.vision",
        operation_category="llm",
        billing_usage_type=UsageType.LLM_REQUEST.value,
        billing_resource_name=f"llm:{model}",
        billing_quantity=1,
        billing_pending_settlement=True,
    ):
        result = await llm.invoke([message], json_output=json_output)

    return {
        "success": True,
        "result": result,
        "file_name": file_info.get("name"),
        "model": model,
    }
