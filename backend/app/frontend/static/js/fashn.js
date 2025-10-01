/**
 * AI Stylist - JavaScript для управления виртуальной примеркой
 */

class FashnApp {
    constructor() {
        this.userPhotoFile = null;
        this.selectedProduct = null;
        this.products = [];
        this.currentSite = this.getSiteFromUrl();
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadProducts();
        this.updateGenerateButton();
        this.initFullscreenViewer();
    }
    
    getSiteFromUrl() {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('site') || 'default';
    }

    getProductUrlsFromQuery() {
        const urlParams = new URLSearchParams(window.location.search);
        const productUrls = [];
        
        // Получаем все параметры, которые могут содержать URL товаров
        for (const [key, value] of urlParams.entries()) {
            // Ищем параметры типа url, product_url, или параметры, которые выглядят как URL
            if (key === 'url' || key === 'product_url' || key.startsWith('url') || value.startsWith('http')) {
                try {
                    // Простая проверка, что это URL
                    new URL(value);
                    productUrls.push(value);
                } catch (e) {
                    // Не валидный URL, пропускаем
                }
            }
        }
        
        return [...new Set(productUrls)]; // Убираем дубликаты
    }
    
    async loadProducts() {
        try {
            // Инициализируем пустую коллекцию
            this.products = [];
            
            // Проверяем URL параметры для товаров
            const urlsFromQuery = this.getProductUrlsFromQuery();
            if (urlsFromQuery.length > 0) {
                console.log('Найдены URL товаров в параметрах:', urlsFromQuery);
                // Показываем пустую сетку, затем асинхронно добавляем товары
                this.renderProducts(this.products);
                this.loadProductsFromUrls(urlsFromQuery);
            } else {
                // Показываем пустую коллекцию
                this.renderEmptyState();
            }
        } catch (error) {
            console.error('Ошибка загрузки товаров:', error);
            this.showError('Failed to load products: ' + error.message);
        }
    }

    renderEmptyState() {
        const grid = document.getElementById('productsGrid');
        if (!grid) return;

        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-content">
                    <i class="bi bi-bag" style="font-size: 48px; color: #9ca3af; margin-bottom: 16px;"></i>
                    <h3>No products yet</h3>
                    <p>Add product URLs above to start building your collection</p>
                </div>
            </div>
        `;
    }

    async loadProductsFromUrls(urls) {
        // Показываем индикатор загрузки для каждого URL
        urls.forEach((url, index) => {
            this.addLoadingProduct(`loading_${index}`, url);
        });

        // Асинхронно парсим каждый URL
        const parsePromises = urls.map(async (url, index) => {
            try {
                console.log(`Парсинг товара: ${url}`);
                const parsedProduct = await this.parseProductFromUrl(url);
                
                // Удаляем плейсхолдер загрузки
                this.removeLoadingProduct(`loading_${index}`);
                
                // Добавляем распарсенный товар
                this.products.unshift(parsedProduct);
                this.renderProducts(this.products);
                
                console.log(`Product successfully added: ${parsedProduct.name}`);
                return parsedProduct;
            } catch (error) {
                console.error(`Ошибка парсинга товара ${url}:`, error);
                
                // Удаляем плейсхолдер загрузки
                this.removeLoadingProduct(`loading_${index}`);
                
                // Добавляем товар с ошибкой
                this.addErrorProduct(url, error.message);
                return null;
            }
        });

        // Ждем завершения всех парсингов
        const results = await Promise.allSettled(parsePromises);
        const successCount = results.filter(r => r.status === 'fulfilled' && r.value !== null).length;
        
        if (successCount > 0) {
            this.showSuccess(`Added ${successCount} products from URLs`);
        }
    }

    addLoadingProduct(id, url) {
        const loadingProduct = {
            id: id,
            name: 'Loading product...',
            brand: 'LOADING',
            price: '...',
            category: 'tote',
            color: 'Loading',
            image: '/static/img/empty.png',
            imageUrl: '/static/img/empty.png',
            dimensions: { length: 30, height: 20, width: 10 },
            source: 'loading',
            originalUrl: url,
            isLoading: true
        };

        this.products.unshift(loadingProduct);
        this.renderProducts(this.products);
    }

    removeLoadingProduct(id) {
        this.products = this.products.filter(p => p.id !== id);
    }

    addErrorProduct(url, errorMessage) {
        const errorProduct = {
            id: `error_${Date.now()}`,
            name: 'Failed to load',
            brand: 'ERROR',
            price: 'Error',
            category: 'tote',
            color: 'Error',
            image: '/static/img/empty.png',
            imageUrl: '/static/img/empty.png',
            dimensions: { length: 30, height: 20, width: 10 },
            source: 'error',
            originalUrl: url,
            errorMessage: errorMessage,
            isError: true
        };

        this.products.unshift(errorProduct);
        this.renderProducts(this.products);
    }


    renderProducts(products) {
        const grid = document.getElementById('productsGrid');
        if (!grid) return;

        grid.innerHTML = products.map(product => {
            const isLoading = product.isLoading;
            const isError = product.isError;
            
            let selectButtonContent = 'Select for Styling';
            let selectButtonClass = 'select-button';
            let selectButtonAction = `app.selectProduct('${product.id}')`;
            
            if (isLoading) {
                selectButtonContent = '<div class="loading-spinner"></div> Loading...';
                selectButtonClass = 'select-button loading';
                selectButtonAction = 'void(0)'; // Отключаем клик
            } else if (isError) {
                selectButtonContent = 'Failed to load';
                selectButtonClass = 'select-button error';
                selectButtonAction = 'void(0)'; // Отключаем клик
            }

            // Индикатор множественных изображений
            const multipleImagesIndicator = (product.imageUrls && product.imageUrls.length > 1) ? 
                `<div class="multiple-images-indicator">
                    <i class="bi bi-images"></i>
                    <span>${product.imageUrls.length}</span>
                </div>` : '';

            return `
                <div class="product-card ${isLoading ? 'loading' : ''} ${isError ? 'error' : ''}" data-category="${product.category}">
                    <div class="product-image-container">
                        <img src="${product.image}" alt="${product.name}" class="product-image">
                        ${!isLoading && !isError ? `
                            <button class="product-favorite">
                                <i class="bi bi-heart"></i>
                            </button>
                        ` : ''}
                        ${multipleImagesIndicator}
                    </div>
                    <div class="product-info">
                        <div class="product-brand">${product.brand}</div>
                        <div class="product-name">${product.name}</div>
                        <div class="product-price">${product.price}</div>
                        <div class="product-category">${product.category}</div>
                        <button class="${selectButtonClass}" onclick="${selectButtonAction}" ${isLoading || isError ? 'disabled' : ''}>
                            ${selectButtonContent}
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }

    filterProducts(category) {
        const cards = document.querySelectorAll('.product-card');
        cards.forEach(card => {
            if (category === 'all' || card.dataset.category === category) {
                card.style.display = 'block';
            } else {
                card.style.display = 'none';
            }
        });
    }

    selectProduct(productId) {
        // Снимаем выделение с предыдущих товаров
        document.querySelectorAll('.select-button').forEach(btn => {
            btn.classList.remove('selected');
            btn.textContent = 'Select for Styling';
        });

        // Выделяем выбранный товар
        const selectedButton = document.querySelector(`[onclick="app.selectProduct('${productId}')"]`);
        if (selectedButton) {
            selectedButton.classList.add('selected');
            selectedButton.textContent = 'Selected ✓';
        }

        // Сохраняем выбранный товар
        this.selectedProduct = this.products.find(p => p.id === productId);
        document.getElementById('selectedProduct').value = productId;
        
        this.updateGenerateButton();
        this.hideError();
        
        // Прокручиваем к фото, если оно загружено
        if (this.userPhotoFile) {
            document.getElementById('photoContainer').scrollIntoView({ 
                behavior: 'smooth', 
                block: 'center' 
            });
        }
    }

    // Метод для парсинга товара по URL (для интеграции с существующим API)
    async parseProductFromUrl(url) {
        if (!url || !url.trim()) {
            throw new Error('URL товара не указан');
        }

        try {
            const response = await fetch(`/api/v1/admin/parse-product?url=${encodeURIComponent(url)}`);
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Product parsing error');
            }

            const data = await response.json();
            
            if (data.status !== 'success') {
                throw new Error('Failed to get product data');
            }

            // Преобразуем данные в наш формат
            return {
                id: `parsed_${data.product_id || Date.now()}`,
                name: data.title || 'Товар',
                brand: 'PARSED',
                price: 'Price on request',
                category: 'tote', // По умолчанию
                color: 'Unknown',
                image: data.image_url || '/static/img/empty.png',
                imageUrl: data.image_url || '/static/img/empty.png',
                imageUrls: data.image_urls || [], // Все изображения товара
                dimensions: {
                    length: data.dimensions?.length || 30,
                    height: data.dimensions?.height || 20,
                    width: data.dimensions?.width || 10
                },
                source: 'parsed',
                originalUrl: url
            };
        } catch (error) {
            console.error('Ошибка парсинга товара:', error);
            throw error;
        }
    }

    // Метод для добавления распарсенного товара в коллекцию
    async addParsedProduct(url) {
        try {
            const parsedProduct = await this.parseProductFromUrl(url);
            
            // Добавляем товар в начало списка
            this.products.unshift(parsedProduct);
            
            // Перерендериваем товары
            this.renderProducts(this.products);
            
            // Автоматически выбираем добавленный товар
            this.selectProduct(parsedProduct.id);
            
            this.showSuccess(`Product "${parsedProduct.name}" added to collection`);
            
            return parsedProduct;
        } catch (error) {
            this.showError(`Failed to add product: ${error.message}`);
            throw error;
        }
    }

    setupEventListeners() {
        // Загрузка фото пользователя
        const photoContainer = document.getElementById('photoContainer');
        const photoInput = document.getElementById('photoInput');
        const removePhotoBtn = document.getElementById('removePhoto');
        const uploadButton = document.querySelector('.upload-button');

        // Клик по зоне загрузки или кнопке
        if (photoContainer) {
            photoContainer.addEventListener('click', (e) => {
                if (!e.target.closest('.remove-btn') && !e.target.closest('.generate-btn')) {
                    photoInput.click();
                }
            });
        }

        if (uploadButton) {
            uploadButton.addEventListener('click', (e) => {
                e.stopPropagation();
            photoInput.click();
        });
        }

        // Выбор файла
        if (photoInput) {
        photoInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleUserPhotoUpload(e.target.files[0]);
            }
        });
        }

        // Drag & Drop
        if (photoContainer) {
        photoContainer.addEventListener('dragover', (e) => {
            e.preventDefault();
        });

        photoContainer.addEventListener('drop', (e) => {
            e.preventDefault();
            
            if (e.dataTransfer.files.length > 0) {
                this.handleUserPhotoUpload(e.dataTransfer.files[0]);
            }
        });
        }

        // Удаление фото пользователя
        if (removePhotoBtn) {
            removePhotoBtn.addEventListener('click', (e) => {
                e.stopPropagation();
            this.removeUserPhoto();
        });
        }

        // Генерация примерки
        const generateBtn = document.getElementById('generateBtn');
        if (generateBtn) {
            generateBtn.addEventListener('click', (e) => {
                e.stopPropagation();
            this.generateTryOn();
        });
        }

        // Фильтры товаров
        const filterTabs = document.querySelectorAll('.filter-tab');
        filterTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                this.filterProducts(tab.dataset.filter);
                
                // Обновляем активную вкладку
                filterTabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
            });
        });

        // Добавление товара по URL
        const addProductBtn = document.getElementById('addProductBtn');
        const productUrlInput = document.getElementById('productUrl');
        
        if (addProductBtn && productUrlInput) {
            addProductBtn.addEventListener('click', async () => {
                const url = productUrlInput.value.trim();
                if (!url) {
                    this.showError('Please enter product URL');
                    return;
                }

                const originalText = addProductBtn.innerHTML;
                try {
                    addProductBtn.innerHTML = '<div class="loading-spinner"></div> Adding...';
                    addProductBtn.disabled = true;

                    await this.addParsedProduct(url);
                    productUrlInput.value = ''; // Очищаем поле после успешного добавления
                } catch (error) {
                    // Ошибка уже показана в addParsedProduct
                } finally {
                    addProductBtn.innerHTML = originalText;
                    addProductBtn.disabled = false;
                }
            });

            // Добавление товара по Enter
            productUrlInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    addProductBtn.click();
                }
            });
        }
    }

    async handleUserPhotoUpload(file) {
        // Проверка типа файла
        if (!file.type.startsWith('image/')) {
            this.showError('Please select an image');
            return;
        }

        // Проверка размера (макс 10MB)
        if (file.size > 10 * 1024 * 1024) {
            this.showError('File size must not exceed 10MB');
            return;
        }

        try {
            // Показываем превью
            const reader = new FileReader();
            reader.onload = (e) => {
                const photoPreview = document.getElementById('photoPreview');
                const photoImage = document.getElementById('photoImage');
                const uploadZone = document.getElementById('uploadZone');
                const removeBtn = document.getElementById('removePhoto');
                
                if (photoImage && photoPreview && uploadZone) {
                    photoImage.src = e.target.result;
                uploadZone.style.display = 'none';
                    photoPreview.style.display = 'block';
                    if (removeBtn) removeBtn.style.display = 'flex';
                }
            };
            reader.readAsDataURL(file);

            // Сохраняем файл
            this.userPhotoFile = file;
            this.updateGenerateButton();
            this.hideError();

        } catch (error) {
            console.error('Ошибка загрузки фото:', error);
            this.showError('Photo upload error: ' + error.message);
        }
    }

    removeUserPhoto() {
        this.userPhotoFile = null;
        const photoPreview = document.getElementById('photoPreview');
        const uploadZone = document.getElementById('uploadZone');
        const removeBtn = document.getElementById('removePhoto');
        const photoInput = document.getElementById('photoInput');
        
        if (photoPreview) photoPreview.style.display = 'none';
        if (uploadZone) uploadZone.style.display = 'block';
        if (removeBtn) removeBtn.style.display = 'none';
        if (photoInput) photoInput.value = '';
        
        this.updateGenerateButton();
    }


    async generateTryOn() {
        if (!this.userPhotoFile || !this.selectedProduct) {
            this.showError('Please upload photo and select product');
            return;
        }

        if (!this.selectedProduct.imageUrl) {
            this.showError('Failed to get product image.');
            return;
        }

        const generateBtn = document.getElementById('generateBtn');
        const originalText = generateBtn.innerHTML;

        try {
            // Показываем загрузку
            generateBtn.innerHTML = '<div class="loading-spinner"></div> Generating...';
            generateBtn.disabled = true;

            // Загружаем фото пользователя
            const userPhotoUpload = await this.uploadFile(this.userPhotoFile);
            
            if (!userPhotoUpload.success) {
                throw new Error('Failed to upload your photo: ' + userPhotoUpload.error);
            }

            // Готовим параметры для API
            const requestData = {
                model_image_url: userPhotoUpload.url,
                product_image_url: this.selectedProduct.imageUrl, // URL изображения товара для генерации
                product_url: this.selectedProduct.originalUrl || null, // Исходный URL товара с сайта (https://thecultt.com/product/...)
                model_height_cm: parseFloat(document.getElementById('height').value) || 170,
                product_width_cm: this.selectedProduct.dimensions.length || 30,
                product_height_cm: this.selectedProduct.dimensions.height || 0,
                item_kind: document.getElementById('itemKind').value,
                placement: document.getElementById('placement').value,
                variations: 0,
                engine: "nano_banana" // Используем nano_banana по умолчанию для лучшего качества
            };

            // Добавляем дополнительные изображения товара если они есть
            if (this.selectedProduct.imageUrls && this.selectedProduct.imageUrls.length > 1) {
                // Исключаем основное изображение из дополнительных
                const additionalImages = this.selectedProduct.imageUrls.filter(url => url !== this.selectedProduct.imageUrl);
                if (additionalImages.length > 0) {
                    requestData.product_image_urls = additionalImages.slice(0, 3); // Максимум 3 дополнительных
                    console.log(`Отправляем ${additionalImages.length} дополнительных изображений товара`);
                }
            }

            // Вызываем API виртуальной примерки
            const response = await fetch('/api/v1/fashn/try-on', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });

            if (!response.ok) {
                let errorMessage = 'API Error';
                try {
                    const errorData = await response.json();
                    errorMessage = errorData.detail || errorMessage;
                } catch (e) {
                    // Если не удается распарсить JSON ошибки, не читаем response.text() повторно
                    if (response.status === 500) {
                        errorMessage = 'Server error. Please try again or contact administrator.';
                    } else if (response.status === 400) {
                        errorMessage = 'Неверные данные запроса. Проверьте загруженные файлы и ссылку на товар.';
                    } else {
                        errorMessage = `Error ${response.status}: ${response.statusText}`;
                    }
                }
                throw new Error(errorMessage);
            }

            const result = await response.json();
            
            // Показываем результаты
            this.displayResults(result);
            this.showSuccess('Virtual try-on completed successfully!');

        } catch (error) {
            console.error('Ошибка генерации:', error);
            this.showError('Generation error: ' + error.message);
        } finally {
            // Восстанавливаем кнопку
            generateBtn.innerHTML = originalText;
            generateBtn.disabled = false;
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
                throw new Error(errorData.detail || 'File upload error');
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
        const resultsSection = document.getElementById('resultsSection');
        const resultsGrid = document.getElementById('resultsGrid');
        
        if (!resultsSection || !resultsGrid) return;

        // Показываем секцию результатов
        resultsSection.style.display = 'block';

        // Очищаем предыдущие результаты
        resultsGrid.innerHTML = '';

        // Отображаем результаты
        if (result.output_urls && result.output_urls.length > 0) {
            result.output_urls.forEach((url, index) => {
                const resultItem = document.createElement('div');
                resultItem.className = 'result-item';
                resultItem.innerHTML = `
                    <div class="result-image-container">
                        <img src="${url}" alt="Результат примерки ${index + 1}" class="result-image">
                <a href="${url}" target="_blank" download class="download-btn">
                    <i class="bi bi-download"></i>
                </a>
                    </div>
            `;

            // Добавляем обработчик клика для полноэкранного просмотра
                const resultImage = resultItem.querySelector('.result-image');
            if (resultImage) {
                resultImage.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.openFullscreen(url);
                    });
                }

                resultsGrid.appendChild(resultItem);
                });
                
            // Прокручиваем к результатам после генерации
            resultsSection.scrollIntoView({ 
                behavior: 'smooth', 
                block: 'start' 
            });
        }
    }

    updateGenerateButton() {
        const generateBtn = document.getElementById('generateBtn');
        if (!generateBtn) return;

        const hasPhoto = this.userPhotoFile !== null;
        const hasProduct = this.selectedProduct !== null;

        generateBtn.disabled = !hasPhoto || !hasProduct;
    }

    showError(message) {
        const errorDiv = document.getElementById('errorMessage');
        if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
            
            // Автоматически скрываем через 5 секунд
            setTimeout(() => {
                errorDiv.style.display = 'none';
            }, 5000);
        }
        
        // Скрываем успешное сообщение
        this.hideSuccess();
    }

    hideError() {
        const errorDiv = document.getElementById('errorMessage');
        if (errorDiv) {
            errorDiv.style.display = 'none';
        }
    }

    showSuccess(message) {
        const successDiv = document.getElementById('successMessage');
        if (successDiv) {
        successDiv.textContent = message;
        successDiv.style.display = 'block';
            
            // Автоматически скрываем через 5 секунд
            setTimeout(() => {
                successDiv.style.display = 'none';
            }, 5000);
        }
        
        // Скрываем ошибку
        this.hideError();
    }

    hideSuccess() {
        const successDiv = document.getElementById('successMessage');
        if (successDiv) {
            successDiv.style.display = 'none';
        }
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

// Глобальная переменная для доступа к приложению из HTML
let app;

// Функции для управления панелью истории
function closeHistoryPanel() {
    const panel = document.getElementById('historyPanel');
    if (panel) {
        panel.classList.remove('active');
        // Очищаем содержимое через 400ms (после анимации)
        setTimeout(() => {
            panel.innerHTML = '';
        }, 400);
    }
}

function openFullscreen(imageSrc) {
    if (app && app.openFullscreen) {
        app.openFullscreen(imageSrc);
    }
}

// HTMX событие для показа панели после загрузки
document.addEventListener('htmx:afterSwap', function(event) {
    if (event.target.id === 'historyPanel') {
        const panel = document.getElementById('historyPanel');
        if (panel && panel.innerHTML.trim()) {
            panel.classList.add('active');
        }
    }
});

// Инициализация приложения
document.addEventListener('DOMContentLoaded', () => {
    app = new FashnApp();
});
