"""
API эндпоинты для FASHN виртуальной примерки.
"""

import asyncio
import io
import re
import logging
import httpx
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from PIL import Image

from ...core.file_processor import FileProcessor, get_default_file_processor
from ...tools.integrations.fashn_tools import virtual_try_on
from ...tools.integrations.nano_banana_tools import generate_images
from ...core.context import get_context
from app.frontend.dependencies import StorageDep
from app.core.container import get_container
from . import admin
logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Виртуальная примерка"],
    responses={
        400: {"description": "Неверные параметры или некорректные изображения"},
        500: {"description": "Ошибка сервиса примерки"}
    }
)


class TryOnRequest(BaseModel):
    """Запрос на виртуальную примерку"""

    model_image_url: str = Field(..., description="URL изображения модели")
    product_image_url: str = Field(..., description="URL изображения продукта")
    product_image_urls: Optional[List[str]] = Field(None, description="Дополнительные URL изображений товара")
    product_url: Optional[str] = Field(None, description="Исходный URL товара с сайта")
    model_height_cm: float = Field(..., description="Рост модели в см", ge=100, le=250)
    product_width_cm: float = Field(
        default=30, description="Ширина продукта в см", ge=1, le=200
    )
    product_height_cm: float = Field(
        default=0,
        description="Высота продукта в см (0 = сохранить пропорции)",
        ge=0,
        le=200,
    )
    item_kind: str = Field(default="bag", description="Тип продукта: bag или garment")
    placement: str = Field(default="left_shoulder", description="Размещение для сумок")
    offset_x_pct: float = Field(default=-6.0, description="Смещение по X в %")
    offset_y_pct: float = Field(default=0.0, description="Смещение по Y в %")
    visible_top_pct: float = Field(
        default=0.04, description="Верхний срез фигуры (0..1)"
    )
    visible_bottom_pct: float = Field(
        default=0.98, description="Нижний срез фигуры (0..1)"
    )
    scale_bias: float = Field(default=1.0, description="Финальный множитель размера")
    variations: int = Field(
        default=0,
        description="Количество дополнительных вариаций модели (0-3)",
        ge=0,
        le=3,
    )
    engine: str = Field(
        default="nano_banana", 
        description="Движок для виртуальной примерки: 'fashn' или 'nano_banana'"
    )


class TryOnResponse(BaseModel):
    """Ответ виртуальной примерки"""

    status: str
    job_ids: list[str]
    output_urls: list[str]  # Список всех результатов (основной + вариации)
    model_urls: list[str]  # Список URL моделей (основная + вариации)
    product_scaled_url: str
    message: str


async def download_image(url: str) -> bytes:
    """Скачивает изображение по URL"""
    try:
        logger.info(f"Скачивание изображения: {url}")
        
        # Если это ссылка на наш API (относительная или абсолютная) - используем прямой доступ к файлу
        if "/api/v1/files/download/" in url:
            file_id = url.split("/")[-1]
            logger.info(f"Обнаружена ссылка на внутренний файл, file_id: {file_id}")

            # Получаем файл напрямую из файлового процессора
            file_processor = await get_default_file_processor()
            file_record = await file_processor.get_file_record(file_id)

            if not file_record:
                logger.error(f"Файл {file_id} не найден в базе данных")
                raise HTTPException(status_code=404, detail=f"Файл {file_id} не найден")

            # Используем прямой S3 URL из модели
            if not file_record.direct_s3_url:
                logger.error(f"Не удалось получить S3 URL для файла {file_id}")
                raise HTTPException(
                    status_code=500, detail="Не удалось получить ссылку на файл"
                )

            logger.info(f"Использую прямую S3 ссылку: {file_record.direct_s3_url}")
            url = file_record.direct_s3_url

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()

            # Проверяем, что это действительно изображение
            content_type = response.headers.get("content-type", "").lower()
            if not content_type.startswith("image/"):
                logger.error(f"URL не содержит изображение: {url}, Content-Type: {content_type}")
                raise HTTPException(
                    status_code=400,
                    detail=f"URL не содержит изображение. Content-Type: {content_type}",
                )

            content = response.content

            # Дополнительная проверка - пытаемся открыть как изображение
            try:
                Image.open(io.BytesIO(content)).verify()
            except Exception as e:
                logger.error(f"Контент не является валидным изображением: {e}")
                raise HTTPException(
                    status_code=400,
                    detail="Скачанный контент не является валидным изображением",
                )

            logger.info(f"Изображение успешно скачано: {len(content)} байт")
            return content

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при скачивании изображения с {url}: {e}")
        raise HTTPException(
            status_code=400, detail=f"Не удалось скачать изображение с {url}: {str(e)}"
        )


async def process_nano_banana_try_on(request: TryOnRequest, model_record, product_record):
    """
    Обрабатывает виртуальную примерку через nano_banana
    """
    try:
        # Получаем file_id из storage key
        model_file_id = model_record.key.split(":")[-1] if ":" in model_record.key else model_record.file_id
        product_file_id = product_record.key.split(":")[-1] if ":" in product_record.key else product_record.file_id
        
        reference_file_ids = [model_file_id, product_file_id]
        
        # Если есть дополнительные изображения товара, добавляем их
        additional_product_records = []
        if request.product_image_urls:
            logger.info(f"Обрабатываем {len(request.product_image_urls)} дополнительных изображений товара параллельно")
            
            async def process_additional_image(url, index):
                """Обрабатывает одно дополнительное изображение"""
                try:
                    # Скачиваем дополнительное изображение
                    additional_bytes = await download_image(url)
                    
                    # Создаем отдельный FileProcessor для каждого изображения
                    file_processor = FileProcessor()
                    try:
                        # Загружаем в S3
                        additional_record = await file_processor.process_file_from_bytes(
                            data=additional_bytes,
                            original_name=f"additional_product_{index}.png",
                            content_type="image/png",
                            uploaded_by="fashn_api",
                            public=True,
                        )
                        
                        additional_file_id = additional_record.key.split(":")[-1] if ":" in additional_record.key else additional_record.file_id
                        logger.info(f"Дополнительное изображение {index+1} загружено: {additional_record.url}")
                        
                        return additional_record, additional_file_id
                        
                    finally:
                        await file_processor.close()
                        
                except Exception as e:
                    logger.warning(f"Не удалось загрузить дополнительное изображение {index+1}: {e}")
                    return None, None
            
            # Запускаем загрузку всех дополнительных изображений параллельно
            tasks = [
                process_additional_image(url, i) 
                for i, url in enumerate(request.product_image_urls[:3])  # Ограничиваем до 3 дополнительных
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"Ошибка при параллельной загрузке изображения: {result}")
                    continue
                    
                additional_record, additional_file_id = result
                if additional_record and additional_file_id:
                    additional_product_records.append(additional_record)
                    reference_file_ids.append(additional_file_id)
        
        prompt = f"""PHOTO EDITING TASK - NOT IMAGE GENERATION!

**CONTEXT & INPUTS:**
You are provided with {len(reference_file_ids)} images:
- **Image #1: BASE - ORIGINAL PERSON PHOTO (WITHOUT THE TARGET PRODUCT).** This is the **ABSOLUTE PRIMARY CANVAS AND THE UNCHANGEABLE SUBJECT**. It features a specific person, potentially with their own clothing or accessories, but **NOT** the specific {request.item_kind} you need to add. This image MUST remain the primary canvas. **DO NOT ALTER THE PERSON IN IMAGE #1 IN ANY WAY THAT CHANGES THEIR IDENTITY, FACE, BODY, GENDER, CLOTHING, HAIR, OR POSE BEYOND MINIMAL INTERACTION.**
- **Images #2-{len(reference_file_ids)}: REFERENCE - {request.item_kind.upper()} product(s) and/or person with product.** These images serve as detailed references. If multiple, they show DIFFERENT ANGLES of the *SAME SINGLE TARGET PRODUCT* (front view, back view, side views, top/bottom if visible). They might also include a person wearing/holding a product (either the target product or a similar one) to demonstrate natural interaction. **YOU MUST STUDY ALL REFERENCE IMAGES SYSTEMATICALLY TO UNDERSTAND THE PRODUCT'S COMPLETE 3D STRUCTURE, INCLUDING:**
    - Front vs back identification (logos, design elements, seams, closures)
    - How all sides look and connect in 3D space
    - Accurate placement of straps, handles, zippers, and hardware
    - Texture, patterns, and material direction across all surfaces
    - How the product naturally interacts with a person's body when worn/carried

**YOUR SOLE OBJECTIVE:**
Integrate ONE {request.item_kind} from the reference images (Images #2+) onto the **EXACT, UNMODIFIED PERSON** in Image #1. This is a sophisticated photo editing task, akin to a professional retoucher adding a product in Photoshop, NOT generating a new scene. The goal is a seamless, natural integration, making it look as if the person in Image #1 was originally photographed with the target product. **The final image MUST look like a professional studio photograph, not a digital overlay, and MUST strictly adhere to the provided references for both the original person and the exact product.**

**CRITICAL REQUIREMENTS FOR NATURAL & REALISTIC INTEGRATION:**

1.  **PERSON & SCENE INTEGRITY (ABSOLUTE, UNCOMPROMISING, AND TOP PRIORITY):**
    *   **DO NOT GENERATE:** No new person, no new background, no new scene.
    *   **PRESERVE EXACTLY AND WITHOUT EXCEPTION:** The **EXACT PERSON** (same face, same body, same gender, same identity, same clothing, same hair, same skin tone, same pose) from Image #1 must be maintained **ABSOLUTELY WITHOUT ANY ALTERATION OR SUBSTITUTION**. The background and lighting from Image #1 must also be preserved.
    *   **ALLOWED MINIMAL ADJUSTMENTS (ONLY FOR PRODUCT INTERACTION - EXTREMELY LIMITED):**
        *   Slight camera angle rotation (5-15 degrees) to optimize product visibility.
        *   Subtle body angle/turn of the person to naturally showcase the product (e.g., turning a shoulder for a bag).
        *   Realistic modification of hand/arm position to VISIBLY HOLD, WEAR, or CARRY the product. Fingers MUST visibly grip straps, hands MUST support bottoms, straps MUST go over shoulders naturally. **The interaction must be physically convincing and show tension/support where appropriate. THESE ARE THE ONLY PERMISSIBLE CHANGES TO THE PERSON'S POSE OR LIMB POSITION. NO OTHER CHANGES TO THE PERSON ARE ALLOWED.**
    *   **ABSOLUTELY FORBIDDEN:** 
        - Changing facial features, identity, **GENDER**, clothing, hair, body shape, background, or dramatic lighting shifts
        - **IMPROVING or ENHANCING the person's appearance** (better skin texture, smoother features, perfect makeup, enhanced beauty, removal of imperfections)
        - **IMPROVING or CHANGING the person's clothing** (making it more fashionable, cleaner, newer looking, better fitting, removing wrinkles or wear)
        - **TOUCHING UP or BEAUTIFYING** any aspect of the person or their clothing
        - Floating products without physical contact
        - Hands "holding" without visible, convincing grip
        - Products "on" a person without visible means of attachment (e.g., straps, support)
        - **ANY CHANGE TO THE PERSON'S APPEARANCE OR IDENTITY BEYOND THE EXTREMELY MINIMAL INTERACTION ADJUSTMENTS IS A CRITICAL FAILURE.**
        - **PRESERVE ALL IMPERFECTIONS, WEAR, AND REALISTIC APPEARANCE EXACTLY AS SHOWN IN THE BASE IMAGE.**

2.  **PRODUCT ACCURACY & DETAILS (ABSOLUTE AND NON-NEGOTIABLE):**
    *   **COMPREHENSIVE PRODUCT ANALYSIS (CRITICAL FIRST STEP):**
        *   **STUDY ALL REFERENCE IMAGES SYSTEMATICALLY:** Before placing the product, you MUST carefully examine ALL reference images (Images #2+) from EVERY angle they show.
        *   **IDENTIFY FRONT vs BACK:** Determine which side is the FRONT and which is the BACK of the product. Look for distinguishing features:
            - Front typically shows: main design, logos, primary decorative elements, zippers/closures (if visible from front), main pockets
            - Back typically shows: seams, less decoration, zippers/closures (if visible from back), different strap/handle attachment points
        *   **UNDERSTAND 3D STRUCTURE:** Mentally reconstruct the 3D shape of the product from all reference angles. Note:
            - How the product curves and bends in 3D space
            - Where straps/handles attach and how they align
            - How the product opens/closes (zippers, buttons, closures)
            - Textile grain direction and any patterns that might indicate orientation
        *   **VERIFY ORIENTATION BEFORE PLACEMENT:** Based on the person's pose in Image #1, determine which side of the product should face the camera:
            - If person faces camera: FRONT of product faces camera
            - If person is in profile/side view: appropriate side of product is visible
            - If person's back is visible: BACK of product faces camera (with front hidden)
        *   **DO NOT GUESS OR REVERSE:** If you cannot clearly determine front/back from references, study them MORE CAREFULLY. Do NOT randomly choose orientation. The product's orientation MUST match the logical viewing angle given the person's pose.
    
    *   **IDENTICAL REPLICATION:** Use the EXACT target product from Image #2+. Maintain ALL details: color, pattern, texture, shape, hardware, logos, stitching, **AND SPECIFIC FEATURES LIKE STRAPS, HANDLES, ZIPPERS, AND EMBLEMS.**
    *   **NO MODIFICATION, NO GENERATION, NO INFERENCE:** DO NOT alter the product's appearance, simplify details, change colors, **ADD NEW FEATURES (e.g., chains on straps if not present in reference, extra handles, different logos), or remove existing features.** The product must be a PHOTOREALISTIC, pixel-perfect copy from the reference images. **Every visible detail of the product must come directly from the provided reference images, not from imagination or other sources.**

3.  **PRODUCT SIZE & PROPORTIONS (PARAMOUNT - EXACT SIZES REQUIRED):**
    *   **PERSON HEIGHT:** {request.model_height_cm} cm.
    *   **PRODUCT DIMENSIONS (EXACT - NOT APPROXIMATE):**
        - **Width:** {request.product_width_cm} cm (EXACT width, do not make smaller)
        - **Height:** {request.product_height_cm} cm (if specified) or maintain reference proportions
        - **Size Multiplier:** {request.scale_bias}x (apply this final scaling factor to the base dimensions)
        - **FINAL WIDTH MUST BE:** {request.product_width_cm * request.scale_bias} cm after applying multiplier
    *   **CRITICAL SIZE CALCULATION PROCESS:**
        1. **MEASURE THE PERSON IN IMAGE #1:** First, measure the visible height of the person in Image #1 (in pixels). Call this value `person_pixels`. This is your reference scale.
        2. **CALCULATE PIXELS PER CENTIMETER:** 
           - Real person height = {request.model_height_cm} cm
           - Scale ratio = `person_pixels` pixels ÷ {request.model_height_cm} cm = pixels_per_cm
           - Example: If person is 1200 pixels tall and {request.model_height_cm} cm real height, then pixels_per_cm = 1200 ÷ {request.model_height_cm} = {1200 / request.model_height_cm:.2f} pixels per cm
        3. **CALCULATE PRODUCT SIZE IN PIXELS:**
           - Product real width = {request.product_width_cm * request.scale_bias} cm (base width × multiplier)
           - Product width in pixels = {request.product_width_cm * request.scale_bias} cm × pixels_per_cm
           - **THIS IS THE EXACT SIZE THE PRODUCT MUST BE IN THE IMAGE**
        4. **VERIFY BEFORE PLACING:** Check that the product matches this calculated pixel size. If the reference product appears at a different size, scale it to match this EXACT pixel width.
        5. **APPLY EXACTLY:** The product MUST be EXACTLY this calculated size, not "approximately" or "close to". Do NOT make it smaller. Use precise pixel measurements and scaling.
    *   **SIZE ACCURACY IS NON-NEGOTIABLE:**
        - **DO NOT** make the product smaller than specified "to fit better" or "look more natural"
        - **DO NOT** approximate sizes - use EXACT dimensions
        - **DO NOT** scale down proportionally unless the specified dimensions require it
        - **ALWAYS** verify the product appears at the correct size relative to the person's {request.model_height_cm} cm height
        - If you think the size looks "too large", the issue is NOT the size - it's the correct size. Trust the measurements.
    *   **SIZE EXAMPLES FOR REFERENCE:**
        - If person is {request.model_height_cm} cm tall and product is {request.product_width_cm * request.scale_bias} cm wide, the product width should be {request.product_width_cm * request.scale_bias / request.model_height_cm * 100:.1f}% of the person's height
        - A {request.product_width_cm * request.scale_bias} cm bag on a {request.model_height_cm} cm person should look substantial, not tiny
        - If {request.product_width_cm * request.scale_bias} cm seems large, it IS large - that's the correct size
    *   **NO SHRINKING TO FIT:** If the product's correct size means it won't entirely fit within the frame, **DO NOT shrink it**. Instead, show a partial view (crop edges) at the correct, EXACT scale.
    *   **PRIORITY:** Exact size accuracy is **MORE IMPORTANT** than fitting the entire product in frame. Always use the EXACT specified dimensions. NEVER make the product smaller than specified.

4.  **SMART & NATURAL PLACEMENT & INTERACTION (PROFESSIONAL TOUCH):**
    *   **ANALYZE POSE:** Carefully assess the person's pose in Image #1:
        *   Hand positions (visible/hidden, free/busy, gripping).
        *   Arm angles (along body, bent, extended).
        *   Body orientation (front, side, turned).
        *   Activity (walking, standing, sitting).
    *   **LOGICAL INTERACTION:**
        *   **Hands Free & Visible:** Person actively holds the product naturally (e.g., carrying a shopping bag).
        *   **Arm Along Body:** Product hangs on shoulder/crossbody with the strap clearly visible and interacting with the body.
        *   **Hands in Pockets:** Product on shoulder, strap over shoulder, clearly visible and supported.
        *   **Walking/Movement:** Product shows natural motion (slight tilt/swing) consistent with movement.
    *   **PHYSICAL INTERACTION IS KEY:** The product MUST physically interact with the person's body realistically – touching hand/shoulder/body, straps visible, natural grip. **If the product has a strap/handle, it MUST be realistically worn/held, showing appropriate tension and drape. The person's hand/arm MUST convincingly interact with the strap/handle, appearing to bear its weight or support it.**

5.  **ADVANCED REALISM: DEPTH, SHADOWS, AND PERSPECTIVE (CRITICAL FOR NATURAL LOOK):**
    *   **VOLUME & CONTOUR:** The product must appear to have **3D volume** and naturally conform to the contours of the person's body (e.g., a bag pressing slightly against a hip, a strap curving over a shoulder). It should not look flat or "pasted on."
    *   **SHADOWS:** Generate **ACCURATE AND NATURAL SHADOWS** cast by the product onto the person's body and clothing, as well as self-shadows on the product itself. Shadows must match the direction, intensity, and softness of the existing lighting in Image #1. This is crucial for depth and integration.
    *   **HIGHLIGHTS:** Ensure highlights on the product are consistent with the lighting in Image #1.
    *   **PERSPECTIVE:** The product's perspective must perfectly match the camera angle and perspective of Image #1.
    *   **CLOTHING INTERACTION:** If the product (e.g., a strap) goes over clothing, the clothing should show **subtle deformation or compression** where the product rests, enhancing realism.

6.  **VISIBILITY:**
    *   **MAXIMUM VISIBILITY:** Position the product for maximum visibility in frame, clearly showing its details, pattern, and shape from reference.

**FORBIDDEN ACTIONS (REITERATED AND EMPHASIZED - ANY OF THESE IS A CRITICAL FAILURE):**
*   **CHANGING THE PERSON IN IMAGE #1 IN ANY WAY (FACE, IDENTITY, GENDER, BODY, CLOTHING, HAIR, SKIN TONE, POSE BEYOND MINIMAL INTERACTION).**
*   **IMPROVING OR ENHANCING THE PERSON'S APPEARANCE:** Better skin texture, smoother features, perfect makeup, enhanced beauty, removal of blemishes, wrinkles, or imperfections. Keep ALL natural, realistic appearance exactly as shown.
*   **IMPROVING OR CHANGING THE PERSON'S CLOTHING:** Making it more fashionable, cleaner, newer looking, better fitting, removing wrinkles, wear, or stains. Keep clothing EXACTLY as shown with all imperfections.
*   **TOUCHING UP OR BEAUTIFYING:** Any cosmetic improvements, retouching, or enhancement of the person or their clothing is FORBIDDEN.
*   Changing the background or lighting dramatically.
*   Products floating unnaturally without contact.
*   Unnatural or unrealistic product placement.
*   **REVERSING OR INCORRECTLY ORIENTING THE PRODUCT:** Placing the product with front and back reversed, or with wrong orientation relative to the person's pose. You MUST correctly identify which side is front and which is back from reference images, and place it accordingly.
*   **PLACING PRODUCT WITHOUT STUDYING ALL REFERENCE ANGLES:** Do NOT proceed to place the product until you have systematically examined ALL reference images and understand the product's 3D structure from every visible angle.
*   **MAKING PRODUCT SMALLER THAN SPECIFIED:** The product MUST be EXACTLY {request.product_width_cm * request.scale_bias} cm wide (after multiplier). DO NOT make it smaller because you think it "looks better" or "fits better". The specified size IS the correct size.
*   **APPROXIMATING SIZES INSTEAD OF USING EXACT DIMENSIONS:** You MUST use precise pixel calculations based on the person's {request.model_height_cm} cm height. Do NOT guess or approximate the size.
*   **MODIFYING THE PRODUCT'S APPEARANCE IN ANY WAY FROM THE REFERENCE IMAGES.**
*   **SIMPLIFYING OR CHANGING PRODUCT DETAILS.**
*   **ADDING OR REMOVING ANY PRODUCT FEATURES (e.g., chains, handles, pockets, logos).**
*   Major pose changes that alter the person's identity or scene.
*   Shrinking the product to an unrealistic size to fit the frame.
*   Omitting the product entirely.
*   Adding multiple products.
*   Producing a flat, "pasted-on" look without realistic shadows, volume, and interaction.
*   **GENERATING ANY DETAIL OR FEATURE FOR THE PRODUCT THAT IS NOT EXPLICITLY PRESENT IN THE PROVIDED REFERENCE IMAGES.**

**EXPECTED OUTPUT:**
A single, high-quality edited image that is 98-99.5% identical to the original Image #1, with 0.5-2% being ONE EXACT target product from the reference images, placed naturally and realistically. The product must look **IDENTICAL IN EVERY SINGLE DETAIL** to the reference, and the **ORIGINAL PERSON FROM IMAGE #1 MUST APPEAR UNCHANGED** (except for minimal interaction with the product), genuinely using or carrying the single item, as if captured by a professional photographer. **The integration must be so seamless that it's indistinguishable from an original photograph, and the product must be an exact, pixel-perfect replica of the reference, without any creative alterations. THE PERSON'S IDENTITY AND GENDER MUST BE PRESERVED AT ALL COSTS.**
"""
        
        # Логируем детали для отладки
        logger.info("=== ДЕТАЛЬНАЯ ОТЛАДКА ПОРЯДКА ИЗОБРАЖЕНИЙ ===")
        logger.info("Исходные данные:")
        logger.info(f"  model_file_id (должен быть [0]): {model_file_id}")
        logger.info(f"  product_file_id (должен быть [1]): {product_file_id}")
        
        logger.info("Итоговый массив reference_file_ids:")
        for i, file_id in enumerate(reference_file_ids):
            role = "МОДЕЛЬ (человек)" if i == 0 else f"ТОВАР {i}"
            logger.info(f"  [{i}] {role}: {file_id}")
        
        logger.info(f"Общее количество изображений: {len(reference_file_ids)}")
        logger.info(f"Промпт (первые 300 символов): {prompt[:300]}...")
        
        # КРИТИЧЕСКАЯ ПРОВЕРКА: убедимся что модель действительно первая
        if len(reference_file_ids) > 0 and reference_file_ids[0] != model_file_id:
            logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: Модель НЕ на первом месте!")
            logger.error(f"   Ожидалось: {model_file_id}")
            logger.error(f"   Получили: {reference_file_ids[0]}")
            raise HTTPException(status_code=500, detail="Ошибка порядка изображений: модель не на первом месте")
        
        # Генерируем изображения
        num_images = max(1, request.variations + 1)
        result_text = await generate_images.ainvoke({
            "prompt": prompt,
            "reference_file_ids": reference_file_ids,
            "num_images": num_images,
            "is_editing": True,  # Режим редактирования: первое изображение - база
        })
        
        logger.info(f"Результат generate_images: {result_text}")
        
        if result_text.startswith("❌"):
            raise HTTPException(status_code=500, detail=result_text)
        
        # Парсим результат для извлечения URL-ов
        # Используем метод из FileProcessor для извлечения информации о файлах
        file_info_list = FileProcessor.extract_file_info_from_message(result_text)
        
        logger.info(f"Извлеченная информация о файлах: {file_info_list}")
        
        if file_info_list:
            file_urls = [file_info["url"] for file_info in file_info_list]
            logger.info(f"Найденные URL-ы файлов: {file_urls}")
        else:
            # Попробуем найти URL-ы напрямую как fallback
            logger.warning(f"Не найдены файлы через FileProcessor в результате: {result_text}")
            
            url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
            urls = re.findall(url_pattern, result_text)
            
            if urls:
                file_urls = urls
                logger.info(f"Найдены URL-ы напрямую: {file_urls}")
            else:
                raise HTTPException(status_code=500, detail=f"Не удалось получить результаты генерации. Ответ: {result_text}")
        
        # Формируем ответ в том же формате что и FASHN
        job_ids = [f"nano_banana_{i}" for i in range(len(file_urls))]
        
        # Сохраняем запись в историю
        context = get_context()
        if context and context.user:
            user_id = context.user.user_id
            try_on_uuid = uuid.uuid4().hex
            try_on_id = f"try_on:{user_id}:{try_on_uuid}"
            
            model_url = model_record.direct_s3_url or model_record.url
            product_url_value = product_record.direct_s3_url or product_record.url
            
            try_on_record = {
                "id": try_on_id,
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "model_file_id": model_record.key,
                "model_url": model_url,
                "product_file_id": product_record.key,
                "product_image_url": product_url_value,
                "product_url": request.product_url,
                "result_urls": file_urls,
                "parameters": {
                    "model_height_cm": request.model_height_cm,
                    "product_width_cm": request.product_width_cm,
                    "product_height_cm": request.product_height_cm,
                    "item_kind": request.item_kind,
                    "placement": request.placement,
                    "offset_x_pct": request.offset_x_pct,
                    "offset_y_pct": request.offset_y_pct,
                    "visible_top_pct": request.visible_top_pct,
                    "visible_bottom_pct": request.visible_bottom_pct,
                    "scale_bias": request.scale_bias,
                    "variations": request.variations
                }
            }

            storage = get_container().storage
            await storage.set(try_on_id, json.dumps(try_on_record))
            logger.info(f"✅ Примерка сохранена в историю: {try_on_id}")
        else:
            logger.warning("⚠️ Нет контекста пользователя, история не сохранена")
        
        return TryOnResponse(
            status="ok",
            job_ids=job_ids,
            output_urls=file_urls,
            model_urls=[model_record.direct_s3_url or model_record.url] * len(file_urls),
            product_scaled_url=product_record.direct_s3_url or product_record.url,
            message=f"Виртуальная примерка через nano_banana завершена! Создано {len(file_urls)} изображений"
        )
        
    except Exception as e:
        logger.error(f"Ошибка nano_banana виртуальной примерки: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")


@router.post("/try-on", response_model=TryOnResponse, summary="Виртуальная примерка")
async def virtual_try_on_api(request: TryOnRequest, storage: StorageDep):
    """
    Создает изображение с виртуальной примеркой одежды или аксессуаров.
    
    **Что можно примерять:**
    - Одежда (футболки, платья, свитера, пиджаки)
    - Аксессуары (сумки, рюкзаки, клатчи)
    
    **Параметры:**
    - model_image_url - фото модели (пользователя)
    - product_image_url - фото товара
    - model_height_cm - рост модели (обязательно)
    - Дополнительные параметры для точной настройки
    
    **Вариации:**
    Можно создать до 3 вариаций изображения для выбора лучшего результата.
    
    **Движки:**
    - nano_banana (рекомендуется) - быстрее и качественнее
    - fashn - оригинальный движок

    Эмулирует работу агента:
    1. Скачивает изображения по URL
    2. Загружает их в наш S3 через FileProcessor
    3. Получает file_id из нашей системы
    4. Вызывает upload_image_for_try_on.ainvoke()
    5. Затем вызывает virtual_try_on.ainvoke()
    """
    file_processor = None

    try:
        logger.info(
            f"Начинаем виртуальную примерку: модель={request.model_image_url}, продукт={request.product_image_url}"
        )

        # Скачиваем изображения
        model_bytes = await download_image(request.model_image_url)
        product_bytes = await download_image(request.product_image_url)

        logger.info(
            f"Изображения скачаны: модель={len(model_bytes)} байт, продукт={len(product_bytes)} байт"
        )

        # Инициализируем FileProcessor для загрузки в наш S3 (как делал бы агент)
        file_processor = FileProcessor()

        # Загружаем изображение модели в наш S3 и получаем file_id (публично доступно для FASHN)
        model_record = await file_processor.process_file_from_bytes(
            data=model_bytes,
            original_name="model.jpg",
            content_type="image/jpeg",
            uploaded_by="fashn_api",
            public=True,
        )
        logger.info(
            f"Модель загружена в S3: {model_record.url}, file_id: {model_record.file_id}"
        )

        # Загружаем изображение продукта в наш S3 и получаем file_id (публично доступно для FASHN)
        product_record = await file_processor.process_file_from_bytes(
            data=product_bytes,
            original_name="product.png",
            content_type="image/png",
            uploaded_by="fashn_api",
            public=True,
        )
        logger.info(
            f"Продукт загружен в S3: {product_record.url}, file_id: {product_record.file_id}"
        )

        # Выбираем движок для виртуальной примерки
        if request.engine == "nano_banana":
            logger.info("Используем nano_banana для виртуальной примерки")
            return await process_nano_banana_try_on(request, model_record, product_record)

        # Используем FASHN (по умолчанию)
        logger.info("Используем FASHN для виртуальной примерки")
        
        # Используем правильные ключи для storage (s3:provider:file_id)
        model_storage_key = model_record.key  # s3:vkcloud:file_id
        product_storage_key = product_record.key  # s3:vkcloud:file_id

        logger.info(
            f"Вызываем virtual_try_on.ainvoke() с ключами: модель={model_storage_key}, продукт={product_storage_key}"
        )

        result_text = await virtual_try_on.ainvoke(
            {
                "model_image_file_id": model_storage_key,
                "product_image_file_id": product_storage_key,
                "model_height_cm": request.model_height_cm,
                "product_width_cm": request.product_width_cm,
                "product_height_cm": request.product_height_cm,
                "item_kind": request.item_kind,
                "placement": request.placement,
                "offset_x_pct": request.offset_x_pct,
                "offset_y_pct": request.offset_y_pct,
                "visible_top_pct": request.visible_top_pct,
                "visible_bottom_pct": request.visible_bottom_pct,
                "scale_bias": request.scale_bias,
                "variations": request.variations,
                "product_url": request.product_url,
            }
        )

        logger.info(f"Результат виртуальной примерки: {result_text}")

        # Парсим результат для извлечения URL-ов
        if request.variations == 0:
            # Обычный результат
            job_id_match = re.search(r"Job ID: ([^\n]+)", result_text)
            job_id = job_id_match.group(1) if job_id_match else None

            output_url_match = re.search(
                r"Финальное изображение: ([^\n]+)", result_text
            )
            output_url = output_url_match.group(1) if output_url_match else ""

            model_url_match = re.search(r"Изображение модели: ([^\n]+)", result_text)
            model_url = model_url_match.group(1) if model_url_match else ""

            product_url_match = re.search(
                r"Изображение продукта: ([^\n]+)", result_text
            )
            product_scaled_url = product_url_match.group(1) if product_url_match else ""

            if not output_url:
                raise HTTPException(
                    status_code=500, detail="Не удалось получить URL результата"
                )

            return TryOnResponse(
                status="ok",
                job_ids=[job_id] if job_id else [],
                output_urls=[output_url],
                model_urls=[model_url],
                product_scaled_url=product_scaled_url,
                message=f"Виртуальная примерка завершена успешно! Исходные файлы: модель={model_record.url}, продукт={product_record.url}",
            )
        else:
            # Результат с вариациями
            job_ids = re.findall(r"Job ID: ([^\n]+)", result_text)
            output_urls = re.findall(r"Финальное изображение: ([^\n]+)", result_text)
            model_urls = re.findall(r"Модель: ([^\n]+)", result_text)

            product_url_match = re.search(r"Продукт: ([^\n]+)", result_text)
            product_scaled_url = product_url_match.group(1) if product_url_match else ""

            if not output_urls:
                raise HTTPException(
                    status_code=500, detail="Не удалось получить URL результатов"
                )

            return TryOnResponse(
                status="ok",
                job_ids=job_ids,
                output_urls=output_urls,
                model_urls=model_urls,
                product_scaled_url=product_scaled_url,
                message=f"Виртуальная примерка с {request.variations} вариациями завершена! Создано {len(output_urls)} изображений",
            )

    finally:
        # Закрываем ресурсы
        if file_processor:
            await file_processor.close()


@router.get("/help")
async def get_fashn_help():
    """
    Получить справку по использованию FASHN API.
    """
    return {
        "title": "FASHN - Виртуальная примерка одежды и аксессуаров",
        "endpoints": {
            "/try-on": "Основной эндпоинт для виртуальной примерки (поддерживает вариации)",
            "/help": "Эта справка",
        },
        "parameters": {
            "model_image_url": "URL изображения модели (обязательно)",
            "product_image_url": "URL изображения продукта (обязательно)",
            "product_image_urls": "Дополнительные URL изображений товара (опционально, до 3 штук)",
            "model_height_cm": "Рост модели в см (100-250)",
            "product_width_cm": "Ширина продукта в см (1-200)",
            "product_height_cm": "Высота продукта в см (0-200, 0 = сохранить пропорции)",
            "item_kind": "Тип продукта: 'bag' или 'garment'",
            "placement": "Размещение для сумок: 'left_shoulder', 'right_shoulder', 'left_hand', 'right_hand', 'center'",
            "variations": "Количество дополнительных вариаций модели (0-3)",
            "engine": "Движок виртуальной примерки: 'fashn' (по умолчанию) или 'nano_banana'",
        },
        "examples": {
            "bag_try_on": {
                "model_image_url": "https://example.com/model.jpg",
                "product_image_url": "https://example.com/bag.png",
                "model_height_cm": 170,
                "product_width_cm": 30,
                "item_kind": "bag",
                "placement": "left_shoulder",
            },
            "garment_try_on": {
                "model_image_url": "https://example.com/model.jpg",
                "product_image_url": "https://example.com/dress.png",
                "model_height_cm": 170,
                "item_kind": "garment",
            },
            "try_on_with_variations": {
                "model_image_url": "https://example.com/model.jpg",
                "product_image_url": "https://example.com/bag.png",
                "model_height_cm": 170,
                "product_width_cm": 30,
                "item_kind": "bag",
                "variations": 2,
            },
            "nano_banana_try_on": {
                "model_image_url": "https://example.com/model.jpg",
                "product_image_url": "https://example.com/dress.png",
                "model_height_cm": 170,
                "item_kind": "garment",
                "engine": "nano_banana",
            },
            "multiple_images_try_on": {
                "model_image_url": "https://example.com/model.jpg",
                "product_image_url": "https://example.com/bag_front.png",
                "product_image_urls": [
                    "https://example.com/bag_side.png",
                    "https://example.com/bag_back.png"
                ],
                "model_height_cm": 170,
                "product_width_cm": 25,
                "item_kind": "bag",
                "engine": "nano_banana",
            },
        },
    }


@router.get("/history", response_model=List[dict])
async def get_try_on_history(storage: StorageDep, limit: int = 20, offset: int = 0):
    """
    Получает историю примерок текущего пользователя
    
    Args:
        limit: Количество записей для возврата (по умолчанию 20)
        offset: Смещение для пагинации (по умолчанию 0)
    
    Returns:
        Список записей TryOnRecord для текущего пользователя
    """

    
    # Получаем пользователя из контекста
    context = get_context()
    if not context or not context.user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    user_id = context.user.user_id
    
    try:
        storage = get_container().storage
        
        # Получаем все ключи примерок для пользователя
        prefix = f"try_on:{user_id}:"
        keys = await storage.list_by_prefix(prefix, limit=100)
        
        if not keys:
            return []
        
        # Сортируем ключи по времени создания (новые первыми)
        keys.sort(reverse=True)
        
        # Применяем пагинацию
        paginated_keys = keys[offset:offset + limit]
        
        # Получаем данные для каждого ключа
        try_on_records = []
        for key in paginated_keys:
            data = await storage.get(key)
            if data:
                # Парсим JSON обратно в dict
                
                try_on_data = json.loads(data) if isinstance(data, str) else data
                try_on_records.append(try_on_data)
        
        logger.info(f"Возвращаем {len(try_on_records)} записей истории для пользователя {user_id}")
        return try_on_records
        
    except Exception as e:
        logger.error(f"Ошибка получения истории примерок для пользователя {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get try-on history: {str(e)}")


@router.get("/history/{try_on_id}")
async def get_try_on_details(try_on_id: str, storage: StorageDep):
    """
    Получает детали конкретной примерки
    
    Args:
        try_on_id: ID примерки (полный ключ: try_on:user_id:uuid)
    
    Returns:
        Детали записи TryOnRecord
    """

    
    # Получаем пользователя из контекста
    context = get_context()
    if not context or not context.user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    user_id = context.user.user_id
    
    # Проверяем, что примерка принадлежит текущему пользователю
    if not try_on_id.startswith(f"try_on:{user_id}:"):
        raise HTTPException(status_code=403, detail="Access denied to this try-on record")
    
    try:
        data = await storage.get(try_on_id)
        
        if not data:
            raise HTTPException(status_code=404, detail="Try-on record not found")
        
        try_on_data = json.loads(data) if isinstance(data, str) else data
        return try_on_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения примерки {try_on_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get try-on details: {str(e)}")


@router.get("/history-panel")
async def get_history_panel(storage: StorageDep):
    """
    Возвращает HTML панель с историей примерок для HTMX
    """
    
    # Получаем пользователя из контекста
    context = get_context()
    if not context or not context.user:
        logger.warning("История примерок: нет контекста пользователя")
        return HTMLResponse("""
            <div class="history-panel-content active">
                <div class="history-panel-header">
                    <h2 class="history-panel-title">Your Try-On History</h2>
                    <button class="history-close-btn" onclick="closeHistoryPanel()">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
                <div class="history-content">
                    <p style="text-align: center; color: #6b7280; padding: 40px;">
                        Please log in to view your try-on history
                    </p>
                </div>
            </div>
        """)
    
    user_id = context.user.user_id
    logger.info(f"📜 Запрос истории примерок для пользователя: {user_id}")

    try:
        # Получаем все ключи примерок для пользователя
        prefix = f"try_on:{user_id}:"
        logger.info(f"🔍 Ищем ключи по префиксу: {prefix}")
        keys = await storage.list_by_prefix(prefix, limit=100)
        logger.info(f"📊 Найдено ключей: {len(keys) if keys else 0}")
        
        if keys:
            logger.info(f"🔑 Первые 3 ключа: {keys[:3]}")
        
        if not keys:
            return HTMLResponse("""
                <div class="history-panel-content active">
                    <div class="history-panel-header">
                        <h2 class="history-panel-title">Your Try-On History</h2>
                        <button class="history-close-btn" onclick="closeHistoryPanel()">
                            <i class="bi bi-x"></i>
                        </button>
                    </div>
                    <div class="history-content">
                        <div style="text-align: center; padding: 60px 20px;">
                            <i class="bi bi-clock-history" style="font-size: 48px; color: #9ca3af; margin-bottom: 16px;"></i>
                            <h3 style="color: var(--dark-gray); margin-bottom: 8px;">No try-ons yet</h3>
                            <p style="color: #6b7280;">Start creating styled images to build your history</p>
                        </div>
                    </div>
                </div>
            """)
        
        # Сортируем ключи по времени создания (новые первыми)
        keys.sort(reverse=True)
        
        # Ограничиваем до 20 последних записей для панели
        recent_keys = keys[:20]
        
        # Получаем данные для каждого ключа
        try_on_records = []
        for key in recent_keys:
            data = await storage.get(key)
            if data:
                try_on_data = json.loads(data) if isinstance(data, str) else data
                try_on_records.append(try_on_data)
        
        # Генерируем HTML для каждой примерки
        history_items_html = ""
        for record in try_on_records:
            # Форматируем дату
            try:
                created_date = datetime.fromisoformat(record['created_at'].replace('Z', '+00:00'))
                formatted_date = created_date.strftime('%d.%m.%Y %H:%M')
            except:
                formatted_date = "Unknown date"
            
            # Получаем первый результат для отображения
            result_url = record['result_urls'][0] if record['result_urls'] else '/static/img/empty.png'
            
            # Получаем данные о товаре если есть product_url
            product_info = None
            if record.get('product_url'):
                try:
                    # Вызываем функцию парсинга напрямую, без HTTP запроса
                    # Вызываем функцию парсинга напрямую
                    product_info = await admin.parse_product_url(record['product_url'])
                    
                    # Короткая ссылка на товар
                    parsed_url = urlparse(record['product_url'])
                    parsed_url.path.split('/')[-1][:8] + "..."
                except Exception as e:
                    logger.warning(f"Не удалось получить данные товара для {record.get('product_url')}: {e}")
                    product_info = None
            
            # Формируем HTML для товара
            product_section = ""
            if product_info and product_info.get('status') == 'success':
                product_image = product_info.get('image_url', '/static/img/empty.png')
                product_title = product_info.get('title', 'Product')
                dimensions = product_info.get('dimensions', {})
                
                dimensions_text = ""
                if dimensions.get('length'):
                    dimensions_text += f"L: {dimensions['length']}cm "
                if dimensions.get('width'):
                    dimensions_text += f"W: {dimensions['width']}cm "
                if dimensions.get('height'):
                    dimensions_text += f"H: {dimensions['height']}cm"
                
                product_section = f"""
                    <div class="history-product-info">
                        <a href="{record['product_url']}" target="_blank" class="history-product-image-link">
                            <img src="{product_image}" alt="Product" class="history-product-image">
                        </a>
                        <div class="history-product-details">
                            <div class="history-product-title">{product_title[:30]}...</div>
                            <div class="history-product-dimensions">{dimensions_text}</div>
                        </div>
                    </div>
                """
            
            history_items_html += f"""
                <div class="history-item">
                    <div class="history-item-date">{formatted_date}</div>
                    
                    <div class="history-original-photo" onclick="openFullscreen('{record['model_url']}')">
                        <img src="{record['model_url']}" alt="Original photo">
                    </div>
                    
                    <div class="history-connector">
                        {product_section}
                    </div>
                    
                    <div class="history-result-photo" onclick="openFullscreen('{result_url}')">
                        <img src="{result_url}" alt="Result photo">
                    </div>
                </div>
            """
        
        html_content = f"""
            <div class="history-panel-content active">
                <div class="history-panel-header">
                    <h2 class="history-panel-title">Your Try-On History</h2>
                    <button class="history-close-btn" onclick="closeHistoryPanel()">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
                <div class="history-content">
                    {history_items_html}
                </div>
            </div>
        """
        
        return HTMLResponse(html_content)
        
    except Exception as e:
        logger.error(f"Ошибка получения панели истории для пользователя {user_id}: {e}")
        return HTMLResponse(f"""
            <div class="history-panel-content active">
                <div class="history-panel-header">
                    <h2 class="history-panel-title">Your Try-On History</h2>
                    <button class="history-close-btn" onclick="closeHistoryPanel()">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
                <div class="history-content">
                    <p style="text-align: center; color: #ef4444; padding: 40px;">
                        Error loading history: {str(e)}
                    </p>
                </div>
            </div>
        """)
