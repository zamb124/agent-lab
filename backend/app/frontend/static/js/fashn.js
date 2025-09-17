/**
 * FASHN - JavaScript для управления виртуальной примеркой
 */

class FashnApp {
    constructor() {
        this.userPhotoFile = null;
        this.productData = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadProductFromUrl();
        this.updateGenerateButton();
        this.initFullscreenViewer();
    }
    
    loadProductFromUrl() {
        // Получаем URL товара из параметров страницы
        const urlParams = new URLSearchParams(window.location.search);
        const productUrl = urlParams.get('product_url');
        
        // Также пробуем получить из hash или query string без параметра
        let finalProductUrl = productUrl;
        
        if (!finalProductUrl) {
            // Если нет product_url параметра, пробуем извлечь из полного URL
            const fullUrl = window.location.href;
            const match = fullUrl.match(/https:\/\/thecultt\.com\/product\/[A-Z0-9]+/);
            if (match) {
                finalProductUrl = match[0];
            }
        }
        
        if (finalProductUrl) {
            document.getElementById('productUrl').value = finalProductUrl;
            // Автоматически парсим товар
            setTimeout(() => {
                this.parseProduct();
            }, 500);
        }
    }

    setupEventListeners() {
        // Загрузка фото пользователя
        const photoContainer = document.getElementById('photoContainer');
        const photoInput = document.getElementById('photoInput');
        const removePhotoBtn = document.getElementById('removePhoto');

        // Клик по зоне загрузки
        photoContainer.addEventListener('click', () => {
            photoInput.click();
        });

        // Выбор файла
        photoInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleUserPhotoUpload(e.target.files[0]);
            }
        });

        // Drag & Drop
        photoContainer.addEventListener('dragover', (e) => {
            e.preventDefault();
        });

        photoContainer.addEventListener('drop', (e) => {
            e.preventDefault();
            
            if (e.dataTransfer.files.length > 0) {
                this.handleUserPhotoUpload(e.dataTransfer.files[0]);
            }
        });

        // Удаление фото пользователя
        removePhotoBtn.addEventListener('click', () => {
            this.removeUserPhoto();
        });

        // Парсинг товара
        document.getElementById('parseBtn').addEventListener('click', () => {
            this.parseProduct();
        });

        // Генерация примерки
        document.getElementById('generateBtn').addEventListener('click', () => {
            this.generateTryOn();
        });

        // Обновление состояния кнопки при изменении URL
        document.getElementById('productUrl').addEventListener('input', () => {
            this.updateGenerateButton();
        });
    }

    async handleUserPhotoUpload(file) {
        // Проверка типа файла
        if (!file.type.startsWith('image/')) {
            this.showError('Пожалуйста, выберите изображение');
            return;
        }

        // Проверка размера (макс 10MB)
        if (file.size > 10 * 1024 * 1024) {
            this.showError('Размер файла не должен превышать 10MB');
            return;
        }

        try {
            // Показываем превью
            const reader = new FileReader();
            reader.onload = (e) => {
                const preview = document.getElementById('photoPreview');
                const uploadZone = document.getElementById('uploadZone');
                const removeBtn = document.getElementById('removePhoto');
                const container = document.getElementById('photoContainer');
                
                preview.src = e.target.result;
                uploadZone.style.display = 'none';
                preview.style.display = 'block';
                removeBtn.style.display = 'flex';
                container.classList.add('has-photo');
            };
            reader.readAsDataURL(file);

            // Сохраняем файл
            this.userPhotoFile = file;
            this.updateGenerateButton();
            this.hideError();

        } catch (error) {
            console.error('Ошибка загрузки фото:', error);
            this.showError('Ошибка загрузки фото: ' + error.message);
        }
    }

    removeUserPhoto() {
        this.userPhotoFile = null;
        const preview = document.getElementById('photoPreview');
        const uploadZone = document.getElementById('uploadZone');
        const removeBtn = document.getElementById('removePhoto');
        const container = document.getElementById('photoContainer');
        
        preview.style.display = 'none';
        uploadZone.style.display = 'block';
        removeBtn.style.display = 'none';
        container.classList.remove('has-photo');
        document.getElementById('photoInput').value = '';
        this.updateGenerateButton();
    }

    async parseProduct() {
        const url = document.getElementById('productUrl').value.trim();
        
        if (!url) {
            this.showError('Пожалуйста, введите URL товара');
            return;
        }

        // Проверяем, что это ссылка на thecultt.com
        if (!url.includes('thecultt.com')) {
            this.showError('Поддерживаются только ссылки с thecultt.com');
            return;
        }

        const parseBtn = document.getElementById('parseBtn');
        const originalText = parseBtn.innerHTML;
        
        try {
            parseBtn.innerHTML = '<div class="loading-spinner"></div> Получение информации...';
            parseBtn.disabled = true;

            // Парсим страницу товара
            const productInfo = await this.scrapeProductInfo(url);
            
            if (productInfo) {
                this.productData = productInfo;
                this.displayProductInfo(productInfo);
                this.updateGenerateButton();
                this.hideError();
            } else {
                this.showError('Не удалось получить информацию о товаре');
            }

        } catch (error) {
            console.error('Ошибка парсинга товара:', error);
            this.showError('Ошибка получения информации о товаре: ' + error.message);
        } finally {
            parseBtn.innerHTML = originalText;
            parseBtn.disabled = false;
        }
    }

    async scrapeProductInfo(url) {
        try {
            // Используем наш API для парсинга
            const apiUrl = `/api/v1/admin/parse-product?url=${encodeURIComponent(url)}`;
            const response = await fetch(apiUrl);
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Не удалось получить информацию о товаре');
            }

            const data = await response.json();
            
            if (data.status !== 'success') {
                throw new Error('Ошибка парсинга товара');
            }

            return {
                title: data.title,
                imageUrl: data.image_url,
                dimensions: data.dimensions,
                originalUrl: data.original_url,
                productId: data.product_id
            };

        } catch (error) {
            console.error('Ошибка скрейпинга:', error);
            
            // Fallback: пытаемся извлечь ID товара из URL и использовать предположения
            const idMatch = url.match(/\/([A-Z0-9]+)$/);
            if (idMatch) {
                return {
                    title: `Товар ${idMatch[1]}`,
                    imageUrl: null,
                    dimensions: { length: 30, height: 0 }, // Значения по умолчанию для сумки
                    originalUrl: url,
                    productId: idMatch[1]
                };
            }
            
            throw error;
        }
    }

    displayProductInfo(productInfo) {
        const container = document.getElementById('productInfo');
        const detailsDiv = document.getElementById('productDetails');
        const imageEl = document.getElementById('productImage');

        let infoHtml = `<strong>${productInfo.title}</strong><br>`;
        
        if (productInfo.dimensions.length) {
            infoHtml += `Длина: ${productInfo.dimensions.length} см<br>`;
        }
        if (productInfo.dimensions.width) {
            infoHtml += `Ширина: ${productInfo.dimensions.width} см<br>`;
        }
        if (productInfo.dimensions.height) {
            infoHtml += `Высота: ${productInfo.dimensions.height} см`;
        }

        detailsDiv.innerHTML = infoHtml;

        if (productInfo.imageUrl) {
            imageEl.src = productInfo.imageUrl;
            imageEl.style.display = 'block';
        } else {
            imageEl.style.display = 'none';
        }

        container.style.display = 'block';
    }

    async generateTryOn() {
        if (!this.userPhotoFile || !this.productData) {
            this.showError('Пожалуйста, загрузите фото и укажите товар');
            return;
        }

        if (!this.productData.imageUrl) {
            this.showError('Не удалось получить изображение товара. Попробуйте другую ссылку.');
            return;
        }

        const generateBtn = document.getElementById('generateBtn');
        const originalText = generateBtn.innerHTML;

        try {
            // Скрываем только кнопку, контейнер остается
            generateBtn.style.display = 'none';
            
            // Показываем анимацию загрузки в контейнере результата
            const resultContainer = document.getElementById('resultContainer');
            if (resultContainer) {
                resultContainer.classList.add('loading');
                resultContainer.innerHTML = '<div style="text-align: center; color: #666;"><i class="bi bi-hourglass-split" style="font-size: 24px; margin-bottom: 10px; display: block; color: #666;"></i><p style="color: #666;">Генерация...</p></div>';
            }

            // Загружаем фото пользователя
            const userPhotoUpload = await this.uploadFile(this.userPhotoFile);
            
            if (!userPhotoUpload.success) {
                throw new Error('Не удалось загрузить ваше фото: ' + userPhotoUpload.error);
            }

            // Готовим параметры для API
            const requestData = {
                model_image_url: userPhotoUpload.url,
                product_image_url: this.productData.imageUrl,
                model_height_cm: parseFloat(document.getElementById('height').value),
                product_width_cm: this.productData.dimensions.length || 30,
                product_height_cm: this.productData.dimensions.height || 0,
                item_kind: document.getElementById('itemKind').value,
                placement: document.getElementById('placement').value,
                variations: 0 // Пока без вариаций для простоты
            };

            // Вызываем API виртуальной примерки
            const response = await fetch('/api/v1/fashn/try-on', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });

            if (!response.ok) {
                let errorMessage = 'Ошибка API';
                try {
                    const errorData = await response.json();
                    errorMessage = errorData.detail || errorMessage;
                } catch (e) {
                    // Если не удается распарсить JSON ошибки, не читаем response.text() повторно
                    if (response.status === 500) {
                        errorMessage = 'Ошибка сервера. Попробуйте еще раз или обратитесь к администратору.';
                    } else if (response.status === 400) {
                        errorMessage = 'Неверные данные запроса. Проверьте загруженные файлы и ссылку на товар.';
                    } else {
                        errorMessage = `Ошибка ${response.status}: ${response.statusText}`;
                    }
                }
                throw new Error(errorMessage);
            }

            const result = await response.json();
            
            // Показываем результаты
            this.displayResults(result);
            this.showSuccess('Виртуальная примерка завершена успешно!');

        } catch (error) {
            console.error('Ошибка генерации:', error);
            this.showError('Ошибка генерации: ' + error.message);
        } finally {
            // Показываем кнопку обратно
            generateBtn.style.display = '';
            generateBtn.classList.remove('loading');
            generateBtn.innerHTML = originalText;
            generateBtn.disabled = false;
            this.updateGenerationText();
            
            // Убираем анимацию загрузки из контейнера результата
            const resultContainer = document.getElementById('resultContainer');
            if (resultContainer) {
                resultContainer.classList.remove('loading');
            }
        }
    }

    async uploadFile(file) {
        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/v1/admin/upload', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Ошибка загрузки файла');
            }

            const result = await response.json();
            return {
                success: true,
                url: result.url,
                fileId: result.file_id
            };

        } catch (error) {
            return {
                success: false,
                error: error.message
            };
        }
    }

    displayResults(result) {
        const container = document.getElementById('resultContainer');
        
        // Убираем анимацию загрузки
        container.classList.remove('loading');

        // Основной результат
        if (result.output_urls && result.output_urls.length > 0) {
            const url = result.output_urls[0]; // Берем первый результат
            
            container.innerHTML = `
                <img src="${url}" alt="Результат примерки" class="result-image" style="border-radius: 10px;">
                <a href="${url}" target="_blank" download class="download-btn">
                    <i class="bi bi-download"></i>
                </a>
            `;

            // Добавляем обработчик клика для полноэкранного просмотра
            const resultImage = container.querySelector('.result-image');
            if (resultImage) {
                resultImage.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.openFullscreen(url);
                });
                
                // Добавляем курсор указатель для изображения
                resultImage.style.cursor = 'pointer';
            }
        }
    }

    updateGenerateButton() {
        const generateBtn = document.getElementById('generateBtn');
        const hasPhoto = this.userPhotoFile !== null;
        const hasProduct = this.productData !== null;
        const hasUrl = document.getElementById('productUrl').value.trim() !== '';

        generateBtn.disabled = !hasPhoto || (!hasProduct && !hasUrl);
        this.updateGenerationText();
    }
    
    updateGenerationText() {
        const hasPhoto = this.userPhotoFile !== null;
        const hasProduct = this.productData !== null;
        const hasUrl = document.getElementById('productUrl').value.trim() !== '';
        
        const generateBtn = document.getElementById('generateBtn');
        
        if (hasPhoto && hasProduct) {
            generateBtn.disabled = false;
        } else {
            generateBtn.disabled = true;
        }
    }

    showError(message) {
        const errorDiv = document.getElementById('error');
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
        
        // Скрываем успешное сообщение
        document.getElementById('success').style.display = 'none';
    }

    hideError() {
        document.getElementById('error').style.display = 'none';
    }

    showSuccess(message) {
        const successDiv = document.getElementById('success');
        successDiv.textContent = message;
        successDiv.style.display = 'block';
        
        // Скрываем ошибку
        document.getElementById('error').style.display = 'none';
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    initFullscreenViewer() {
        const fullscreenOverlay = document.getElementById('fullscreenOverlay');
        const fullscreenImage = document.getElementById('fullscreenImage');
        const fullscreenClose = document.getElementById('fullscreenClose');

        // Функция открытия полноэкранного просмотра
        this.openFullscreen = (imageSrc) => {
            fullscreenImage.src = imageSrc;
            fullscreenOverlay.classList.add('active');
            document.body.style.overflow = 'hidden'; // Блокируем скролл
        };

        // Функция закрытия полноэкранного просмотра
        this.closeFullscreen = () => {
            fullscreenOverlay.classList.remove('active');
            document.body.style.overflow = ''; // Восстанавливаем скролл
        };

        // Закрытие по клику на кнопку
        fullscreenClose.addEventListener('click', (e) => {
            e.stopPropagation();
            this.closeFullscreen();
        });

        // Закрытие по клику на фон
        fullscreenOverlay.addEventListener('click', (e) => {
            if (e.target === fullscreenOverlay) {
                this.closeFullscreen();
            }
        });

        // Закрытие по клавише Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && fullscreenOverlay.classList.contains('active')) {
                this.closeFullscreen();
            }
        });
    }
}

// Инициализация приложения
document.addEventListener('DOMContentLoaded', () => {
    new FashnApp();
});
