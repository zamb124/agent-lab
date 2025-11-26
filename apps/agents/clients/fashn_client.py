"""
FASHN API клиент для виртуальной примерки одежды и аксессуаров
"""

import io
import asyncio
import logging
from typing import Literal, Optional, Tuple
from PIL import Image
import httpx
import numpy as np
from pydantic import BaseModel

from apps.agents.config import get_agents_settings
settings = get_agents_settings()
from core.files.processors import FileProcessor

logger = logging.getLogger(__name__)


class TryOnResult(BaseModel):
    """Результат виртуальной примерки"""

    status: Literal["ok"]
    job_id: Optional[str]
    output_url: str
    model_url: str
    product_scaled_url: str


class FashnClient:
    """Клиент для работы с FASHN API"""

    def __init__(self):
        self.config = settings.fashn

        if not self.config.enabled:
            raise RuntimeError("FASHN не включен в конфигурации")

        if not self.config.api_key:
            raise RuntimeError("Не указан API ключ FASHN")

        # Используем FileProcessor платформы для загрузки файлов
        from apps.agents.container import get_agents_container
        self.storage = get_agents_container().storage
        self.file_processor = FileProcessor(storage=self.storage)

        logger.info("FASHN клиент инициализирован")

    async def close(self):
        """Закрывает ресурсы клиента"""
        if self.file_processor:
            await self.file_processor.close()

    def _pil_open(self, raw: bytes, rgba: bool = False) -> Image.Image:
        """Открывает изображение из байтов"""
        img = Image.open(io.BytesIO(raw))
        return img.convert("RGBA") if rgba else img

    def _compute_px_per_mm_visible(
        self,
        model_height_cm: float,
        model_img: Image.Image,
        visible_top_pct: float,
        visible_bottom_pct: float,
    ) -> float:
        """Вычисляет пиксели на мм для видимой части модели"""
        if model_height_cm <= 0:
            raise ValueError("model_height_cm должен быть > 0")

        H = model_img.height
        top = max(0.0, min(1.0, visible_top_pct))
        bot = max(0.0, min(1.0, visible_bottom_pct))

        if bot <= top:
            top, bot = 0.0, 1.0

        visible_px = max(1, int(round((bot - top) * H)))
        height_mm = model_height_cm * 10.0
        return visible_px / height_mm

    def _resize_product_by_width(
        self, product_rgba: Image.Image, target_w_px: int
    ) -> Image.Image:
        """Изменяет размер продукта по ширине, сохраняя пропорции"""
        target_w_px = max(1, int(round(target_w_px)))
        ratio = product_rgba.height / product_rgba.width
        target_h_px = max(1, int(round(target_w_px * ratio)))
        return product_rgba.resize((target_w_px, target_h_px), Image.LANCZOS)

    def _resize_product_by_dimensions(
        self, product_rgba: Image.Image, target_w_px: int, target_h_px: int
    ) -> Image.Image:
        """Изменяет размер продукта точно по заданным размерам (реальные размеры сумки в см)"""
        target_w_px = max(1, int(round(target_w_px)))
        target_h_px = max(1, int(round(target_h_px)))
        return product_rgba.resize((target_w_px, target_h_px), Image.LANCZOS)

    def _analyze_product_bounds(
        self, product_image: Image.Image
    ) -> Tuple[Optional[float], Optional[Tuple[int, int, int, int]]]:
        """
        Анализирует реальные границы продукта на изображении

        Args:
            product_image: PIL изображение продукта

        Returns:
            tuple: (aspect_ratio, bounds) где bounds = (left, top, right, bottom)
        """
        try:
            # Конвертируем в RGB если нужно
            if product_image.mode != "RGB":
                product_image = product_image.convert("RGB")

            # Конвертируем в numpy array
            img_array = np.array(product_image)

            # Определяем фоновый цвет по углам изображения
            h, w = img_array.shape[:2]
            corner_size = min(50, w // 10, h // 10)

            # Берем пиксели из углов
            corners = [
                img_array[0:corner_size, 0:corner_size],  # Верхний левый
                img_array[0:corner_size, -corner_size:],  # Верхний правый
                img_array[-corner_size:, 0:corner_size],  # Нижний левый
                img_array[-corner_size:, -corner_size:],  # Нижний правый
            ]

            # Находим средний цвет углов
            corner_pixels = np.concatenate(
                [corner.reshape(-1, 3) for corner in corners]
            )
            bg_color = np.mean(corner_pixels, axis=0).astype(int)

            # Создаем маску для пикселей, похожих на фон
            color_diff = np.sqrt(np.sum((img_array - bg_color) ** 2, axis=2))
            bg_threshold = 30  # Порог различия цветов

            background_mask = color_diff < bg_threshold
            non_bg_mask = ~background_mask

            # Находим координаты всех не фоновых пикселей
            non_bg_coords = np.where(non_bg_mask)

            if len(non_bg_coords[0]) == 0:
                logger.warning("Не удалось найти границы продукта на изображении")
                return None, None

            # Находим границы
            top = np.min(non_bg_coords[0])
            bottom = np.max(non_bg_coords[0])
            left = np.min(non_bg_coords[1])
            right = np.max(non_bg_coords[1])

            product_width = right - left + 1
            product_height = bottom - top + 1

            # Вычисляем соотношение сторон (высота/ширина)
            aspect_ratio = product_height / product_width

            logger.info(
                f"Анализ границ продукта: {product_width}×{product_height}px, соотношение {aspect_ratio:.3f}"
            )
            logger.info(f"Фоновый цвет: RGB{tuple(bg_color)}")

            return aspect_ratio, (left, top, right, bottom)

        except Exception as e:
            logger.error(f"Ошибка анализа границ продукта: {e}")
            return None, None

    def debug_scaling_calculation(
        self,
        model_height_cm: float,
        model_img_width: int,
        model_img_height: int,
        product_width_cm: float,
        product_height_cm: float,
        visible_top_pct: float = 0.04,
        visible_bottom_pct: float = 0.98,
        scale_bias: float = 1.0,
    ) -> dict:
        """Отладочная функция для анализа масштабирования сумки"""

        print("\n=== АНАЛИЗ МАСШТАБИРОВАНИЯ СУМКИ ===")
        print(f"Размеры модели: {model_img_width}×{model_img_height} пикселей")
        print(f"Рост модели: {model_height_cm} см")
        print(f"Размеры сумки: {product_width_cm}×{product_height_cm} см")
        print(f"Видимая часть модели: {visible_top_pct:.2%} - {visible_bottom_pct:.2%}")
        print(f"Scale bias: {scale_bias}")

        # Шаг 1: Вычисляем пиксели на мм
        H = model_img_height
        top = max(0.0, min(1.0, visible_top_pct))
        bot = max(0.0, min(1.0, visible_bottom_pct))

        if bot <= top:
            top, bot = 0.0, 1.0

        visible_px = max(1, int(round((bot - top) * H)))
        height_mm = model_height_cm * 10.0
        px_per_mm = visible_px / height_mm

        print("\nШаг 1: Расчет масштаба")
        print(f"  Видимая высота в пикселях: {visible_px} px")
        print(f"  Рост модели в мм: {height_mm} мм")
        print(f"  Пикселей на мм: {px_per_mm:.3f} px/mm")

        # Шаг 2: Переводим размеры сумки в пиксели
        product_width_mm = product_width_cm * 10.0
        product_height_mm = product_height_cm * 10.0

        base_w_px = max(1, int(round(product_width_mm * px_per_mm)))
        base_h_px = max(1, int(round(product_height_mm * px_per_mm)))

        target_w_px = max(1, int(round(base_w_px * scale_bias)))
        target_h_px = max(1, int(round(base_h_px * scale_bias)))

        print("\nШаг 2: Размеры сумки в пикселях")
        print(
            f"  Ширина: {product_width_cm} см = {product_width_mm} мм = {base_w_px} px"
        )
        print(
            f"  Высота: {product_height_cm} см = {product_height_mm} мм = {base_h_px} px"
        )
        print(f"  С учетом scale_bias ({scale_bias}): {target_w_px}×{target_h_px} px")

        # Шаг 3: Анализируем пропорции
        original_ratio = product_height_cm / product_width_cm
        pixel_ratio = target_h_px / target_w_px

        print("\nШаг 3: Анализ пропорций")
        print(
            f"  Исходные пропорции сумки: {product_height_cm}/{product_width_cm} = {original_ratio:.3f}"
        )
        print(
            f"  Пропорции в пикселях: {target_h_px}/{target_w_px} = {pixel_ratio:.3f}"
        )
        print(f"  Разница в пропорциях: {abs(original_ratio - pixel_ratio):.6f}")

        # Шаг 4: Процент от размера модели
        model_width_pct = (target_w_px / model_img_width) * 100
        model_height_pct = (target_h_px / model_img_height) * 100

        print("\nШаг 4: Размер относительно модели")
        print(f"  Ширина сумки: {model_width_pct:.1f}% от ширины модели")
        print(f"  Высота сумки: {model_height_pct:.1f}% от высоты модели")

        return {
            "px_per_mm": px_per_mm,
            "target_size_px": (target_w_px, target_h_px),
            "original_ratio": original_ratio,
            "pixel_ratio": pixel_ratio,
            "model_percentage": (model_width_pct, model_height_pct),
        }

    async def _upload_image(self, data: bytes, filename: str) -> str:
        """Загружает изображение через FileProcessor платформы с публичным доступом"""
        file_record = await self.file_processor.process_file_from_bytes(
            data=data,
            original_name=filename,
            content_type="image/png",
            uploaded_by="fashn_client",
            public=True,
        )
        return file_record.direct_s3_url

    def _place_anchor(
        self, model_w: int, model_h: int, placement: str
    ) -> tuple[int, int]:
        """Определяет базовые точки для размещения продукта"""
        shoulders_y = int(model_h * 0.28)  # линия плеч
        hands_y = int(model_h * 0.70)  # ладони

        if placement == "left_shoulder":
            return int(model_w * 0.36), shoulders_y
        if placement == "right_shoulder":
            return int(model_w * 0.64), shoulders_y
        if placement == "left_hand":
            return int(model_w * 0.38), hands_y
        if placement == "right_hand":
            return int(model_w * 0.62), hands_y
        if placement == "center":
            return model_w // 2, model_h // 2

        # По умолчанию - левое плечо
        return int(model_w * 0.36), shoulders_y

    def _compose_product_on_model(
        self,
        model_img_rgb: Image.Image,
        product_rgba: Image.Image,
        placement: str = "left_shoulder",
        offset_x_pct: float = -6.0,
        offset_y_pct: float = 0.0,
    ) -> Image.Image:
        """Накладывает продукт на модель"""
        model_rgba = model_img_rgb.convert("RGBA")
        W, H = model_rgba.width, model_rgba.height

        cx, cy = self._place_anchor(W, H, placement)
        dx = int((offset_x_pct / 100.0) * W)
        dy = int((offset_y_pct / 100.0) * H)
        cx += dx
        cy += dy

        x = int(cx - product_rgba.width / 2)
        y = int(cy - product_rgba.height / 2)

        model_rgba.paste(product_rgba, (x, y), mask=product_rgba)
        return model_rgba

    async def _fashn_run_product_to_model(
        self, product_image_url: str, model_image_url: str
    ) -> str:
        """Запускает задачу FASHN product-to-model"""
        payload = {
            "model_name": "product-to-model",
            "inputs": {
                "product_image": product_image_url,
                "model_image": model_image_url,
                "output_format": "png",
                "return_base64": False,
            },
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                f"{self.config.base_url}/run", json=payload, headers=headers
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Ошибка FASHN /run: {response.status_code} {response.text}"
            )

        job_id = response.json().get("id")
        if not job_id:
            raise RuntimeError(f"FASHN /run не вернул id: {response.text}")

        return job_id

    async def _fashn_run_model_variation(
        self, model_image_url: str, variation_strength: str = "subtle"
    ) -> str:
        """Запускает задачу FASHN model-variation"""
        payload = {
            "model_name": "model-variation",
            "inputs": {
                "model_image": model_image_url,
                "variation_strength": variation_strength,  # "subtle" или "strong"
                "output_format": "png",
                "return_base64": False,
            },
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                f"{self.config.base_url}/run", json=payload, headers=headers
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Ошибка FASHN model-variation: {response.status_code} {response.text}"
            )

        job_id = response.json().get("id")
        if not job_id:
            raise RuntimeError(f"FASHN model-variation не вернул id: {response.text}")

        return job_id

    async def _fashn_poll(self, job_id: str) -> str:
        """Ожидает завершения задачи FASHN"""
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        url = f"{self.config.base_url}/status/{job_id}"

        logger.info(f"Начинаем polling для job_id: {job_id}")

        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            deadline = asyncio.get_event_loop().time() + self.config.poll_timeout
            poll_count = 0

            while True:
                await asyncio.sleep(self.config.poll_interval)
                poll_count += 1
                logger.info(f"Polling #{poll_count} для job {job_id}")

                try:
                    response = await client.get(url, headers=headers)

                    if response.status_code != 200:
                        logger.error(
                            f"FASHN /status вернул {response.status_code}: {response.text}"
                        )
                        raise RuntimeError(
                            f"Ошибка FASHN /status: {response.status_code} {response.text}"
                        )

                    data = response.json()
                    status = data.get("status")
                    logger.info(f"FASHN status для job {job_id}: {status}")
                    logger.info(f"Полный ответ FASHN: {data}")

                    if status in ("completed", "success", "finished"):
                        output = data.get("output")
                        logger.info(f"FASHN завершен, output: {output}")

                        # Пробуем разные поля для получения результата
                        result_url = None

                        if isinstance(output, list) and output:
                            result_url = output[0]
                            logger.info(
                                f"✅ FASHN результат (из списка output): {result_url}"
                            )
                        elif isinstance(output, str):
                            result_url = output
                            logger.info(
                                f"✅ FASHN результат (строка output): {result_url}"
                            )
                        elif data.get("result"):
                            result_url = data.get("result")
                            logger.info(
                                f"✅ FASHN результат (поле result): {result_url}"
                            )
                        elif data.get("url"):
                            result_url = data.get("url")
                            logger.info(f"✅ FASHN результат (поле url): {result_url}")
                        elif data.get("image_url"):
                            result_url = data.get("image_url")
                            logger.info(
                                f"✅ FASHN результат (поле image_url): {result_url}"
                            )

                        if result_url:
                            return result_url

                        logger.error(
                            f"FASHN завершен, но нет URL результата. Полный ответ: {data}"
                        )
                        raise RuntimeError(
                            f"Задача завершена, но нет URL результата. Данные: {data}"
                        )

                    if status not in ("in_queue", "processing", "starting"):
                        logger.error(
                            f"FASHN провален со статусом {status}. Полный ответ: {data}"
                        )
                        raise RuntimeError(f"Задача FASHN провалена: {data}")

                    if asyncio.get_event_loop().time() > deadline:
                        logger.error(
                            f"Таймаут polling для job {job_id} после {poll_count} попыток"
                        )
                        raise RuntimeError(
                            f"Таймаут ожидания результата FASHN ({self.config.poll_timeout} сек). Job ID: {job_id}"
                        )

                    logger.info(
                        f"FASHN job {job_id} еще в процессе ({status}), ждем {self.config.poll_interval} сек..."
                    )

                except httpx.TimeoutException as e:
                    logger.error(f"Таймаут HTTP запроса при polling job {job_id}: {e}")
                    raise RuntimeError(
                        f"Таймаут HTTP запроса при получении статуса: {e}"
                    )
                except httpx.HTTPStatusError as e:
                    logger.error(
                        f"HTTP статус ошибка при polling job {job_id}: {e.response.status_code} {e.response.text}"
                    )
                    raise RuntimeError(
                        f"HTTP ошибка {e.response.status_code}: {e.response.text}"
                    )
                except httpx.RequestError as e:
                    logger.error(
                        f"HTTP ошибка при polling job {job_id}: {type(e).__name__}: {e}"
                    )
                    raise RuntimeError(
                        f"HTTP ошибка при получении статуса: {type(e).__name__}: {e}"
                    )
                except Exception as e:
                    logger.error(
                        f"Неожиданная ошибка при polling job {job_id}: {type(e).__name__}: {e}"
                    )
                    raise RuntimeError(f"Неожиданная ошибка: {type(e).__name__}: {e}")

    async def try_on(
        self,
        model_image_bytes: bytes,
        product_image_bytes: bytes,
        model_height_cm: float,
        product_width_cm: float = 0,
        product_height_cm: float = 0,
        item_kind: str = "bag",
        placement: str = "left_shoulder",
        offset_x_pct: float = -6.0,
        offset_y_pct: float = 0.0,
        visible_top_pct: float = 0.04,
        visible_bottom_pct: float = 0.98,
        scale_bias: float = 1.0,
    ) -> TryOnResult:
        """
        Выполняет виртуальную примерку

        Args:
            model_image_bytes: Байты изображения модели
            product_image_bytes: Байты изображения продукта
            model_height_cm: Рост модели в см
            product_width_cm: Ширина продукта в см (для сумок, обязательно)
            product_height_cm: Высота продукта в см (для сумок, опционально - если не указана, сохраняются пропорции)
            item_kind: Тип продукта ("bag" или "garment")
            placement: Размещение для сумок
            offset_x_pct: Смещение по X в %
            offset_y_pct: Смещение по Y в %
            visible_top_pct: Верхний срез фигуры
            visible_bottom_pct: Нижний срез фигуры
            scale_bias: Финальный множитель размера

        Returns:
            Результат виртуальной примерки
        """
        logger.info(f"Начинаем виртуальную примерку {item_kind}")

        # Открываем изображения
        model_img = self._pil_open(model_image_bytes, rgba=False)
        product_img = self._pil_open(product_image_bytes, rgba=True)

        # Анализируем реальные пропорции продукта на изображении
        real_aspect_ratio, product_bounds = self._analyze_product_bounds(product_img)

        if item_kind.lower() == "bag":
            # Для сумок: НЕ делаем пред-композицию, позволяем FASHN самому разместить сумку
            # Это предотвращает размещение сумки на голове
            logger.info(
                "Для сумок отключена пред-композиция - FASHN сам разместит сумку"
            )

            # Просто масштабируем сумку для лучшего качества
            px_per_mm = self._compute_px_per_mm_visible(
                model_height_cm=model_height_cm,
                model_img=model_img,
                visible_top_pct=visible_top_pct,
                visible_bottom_pct=visible_bottom_pct,
            )

            # Определяем пропорции для масштабирования
            if real_aspect_ratio is not None:
                # Используем реальные пропорции с изображения
                logger.info(
                    f"Используем реальные пропорции с изображения: {real_aspect_ratio:.3f}"
                )
                effective_aspect_ratio = real_aspect_ratio
            elif product_height_cm > 0:
                # Используем заявленные размеры
                logger.info(
                    f"Используем заявленные размеры: {product_width_cm}×{product_height_cm} см"
                )
                effective_aspect_ratio = product_height_cm / product_width_cm
            else:
                # Сохраняем исходные пропорции изображения
                logger.info("Сохраняем исходные пропорции изображения")
                effective_aspect_ratio = product_img.height / product_img.width

            # Конвертируем см в мм для внутренних вычислений
            product_width_mm = product_width_cm * 10.0
            base_w_px = max(1, int(round(product_width_mm * px_per_mm)))
            initial_target_w_px = max(1, int(round(base_w_px * scale_bias)))

            # Вычисляем высоту на основе выбранных пропорций
            initial_target_h_px = max(
                1, int(round(initial_target_w_px * effective_aspect_ratio))
            )

            # Автоматическая коррекция для сумок
            auto_scale_correction = 1.0
            correction_needed = False

            # Находим минимальный размер для коррекции
            min_dimension = min(initial_target_w_px, initial_target_h_px)
            if min_dimension < 120:  # Увеличиваем порог для лучшего качества
                auto_scale_correction = 120 / min_dimension
                correction_needed = True
                logger.info(
                    f"Применяем автокоррекцию: {auto_scale_correction:.2f}x (было {initial_target_w_px}×{initial_target_h_px}px)"
                )

            if not correction_needed:
                logger.info(
                    f"Автокоррекция не нужна: размер {initial_target_w_px}×{initial_target_h_px}px достаточен"
                )

            # Применяем коррекцию
            target_w_px = max(
                1, int(round(base_w_px * scale_bias * auto_scale_correction))
            )
            target_h_px = max(1, int(round(target_w_px * effective_aspect_ratio)))

            # Масштабируем сумку с правильными пропорциями
            product_scaled = self._resize_product_by_dimensions(
                product_img, target_w_px, target_h_px
            )
            logger.info(
                f"Финальный размер сумки: {target_w_px}×{target_h_px}px (соотношение {target_h_px / target_w_px:.3f})"
            )

            # Загружаем ЧИСТОЕ изображение модели (без пред-композиции)
            m_buf = io.BytesIO()
            model_img.save(m_buf, format="PNG")
            model_url = await self._upload_image(m_buf.getvalue(), "model_clean.png")

            # Загружаем масштабированную сумку
            p_buf = io.BytesIO()
            product_scaled.save(p_buf, format="PNG")
            product_url = await self._upload_image(p_buf.getvalue(), "bag_scaled.png")
        else:
            # Для одежды: не композим, FASHN сам обработает
            m_buf = io.BytesIO()
            model_img.save(m_buf, format="PNG")
            model_url = await self._upload_image(m_buf.getvalue(), "model.png")

            p_buf = io.BytesIO()
            product_img.save(p_buf, format="PNG")
            product_url = await self._upload_image(p_buf.getvalue(), "garment.png")

        # Запускаем FASHN
        logger.info(
            f"Запускаем FASHN product-to-model: product={product_url}, model={model_url}"
        )
        job_id = await self._fashn_run_product_to_model(
            product_image_url=product_url, model_image_url=model_url
        )
        logger.info(f"FASHN job запущен с ID: {job_id}")

        logger.info(f"Ожидаем результат FASHN job: {job_id}")
        fashn_output_url = await self._fashn_poll(job_id)
        logger.info(f"FASHN вернул URL результата: {fashn_output_url}")

        # Скачиваем результат из FASHN и сохраняем в наш S3
        logger.info(f"Скачиваем результат FASHN с URL: {fashn_output_url}")
        try:
            # Увеличиваем таймаут для скачивания результата (может быть большой файл)
            download_timeout = httpx.Timeout(300.0)  # 5 минут
            async with httpx.AsyncClient(timeout=download_timeout) as client:
                logger.info(f"Отправляем GET запрос к: {fashn_output_url}")
                response = await client.get(fashn_output_url)
                logger.info(
                    f"Получен ответ: status={response.status_code}, headers={dict(response.headers)}"
                )

                response.raise_for_status()
                result_bytes = response.content
                logger.info(
                    f"Скачан результат FASHN: {len(result_bytes)} байт, content-type: {response.headers.get('content-type')}"
                )

                # Проверяем, что это действительно изображение
                if len(result_bytes) == 0:
                    raise RuntimeError("FASHN вернул пустой файл")

                # Проверяем заголовки
                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    logger.warning(f"FASHN вернул не изображение: {content_type}")
                    # Но продолжаем, возможно это все равно изображение

        except httpx.TimeoutException as e:
            logger.error(f"Таймаут при скачивании результата FASHN: {e}")
            raise RuntimeError(f"Таймаут при скачивании результата FASHN: {e}")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP ошибка при скачивании результата FASHN: {e.response.status_code} {e.response.text}"
            )
            raise RuntimeError(
                f"HTTP ошибка при скачивании результата: {e.response.status_code} {e.response.text}"
            )
        except Exception as e:
            logger.error(f"Ошибка скачивания результата FASHN: {type(e).__name__}: {e}")
            raise RuntimeError(
                f"Не удалось скачать результат FASHN: {type(e).__name__}: {e}"
            )

        # Загружаем результат в наш S3
        logger.info("Загружаем результат FASHN в наш S3...")
        try:
            our_output_url = await self._upload_image(result_bytes, "fashn_result.png")
            logger.info(f"✅ Результат загружен в наш S3: {our_output_url}")
        except Exception as e:
            logger.error(f"Ошибка загрузки результата в S3: {e}")
            raise RuntimeError(f"Не удалось загрузить результат в S3: {e}")

        logger.info(f"Виртуальная примерка завершена, job_id: {job_id}")
        logger.info(f"Результат сохранен в наш S3: {our_output_url}")

        return TryOnResult(
            status="ok",
            job_id=job_id,
            output_url=our_output_url,  # Теперь ссылка на наш S3
            model_url=model_url,
            product_scaled_url=product_url,
        )


# Глобальный экземпляр клиента
_fashn_client: Optional[FashnClient] = None


def get_fashn_client() -> FashnClient:
    """Возвращает глобальный экземпляр FASHN клиента"""
    global _fashn_client
    if _fashn_client is None:
        _fashn_client = FashnClient()
    return _fashn_client
