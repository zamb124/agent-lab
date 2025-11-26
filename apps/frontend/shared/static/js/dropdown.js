/**
 * Простой dropdown без Bootstrap
 */

document.addEventListener('DOMContentLoaded', function() {
    // Обработка клика на кнопку dropdown
    document.addEventListener('click', function(e) {
        const dropdownToggle = e.target.closest('[data-dropdown-toggle]');
        if (dropdownToggle) {
            e.preventDefault();
            const dropdown = dropdownToggle.closest('.dropdown');
            const menu = dropdown?.querySelector('.dropdown-menu');
            
            if (menu) {
                // Закрываем все открытые dropdown
                document.querySelectorAll('.dropdown-menu.show').forEach(openMenu => {
                    if (openMenu !== menu) {
                        openMenu.classList.remove('show');
                        openMenu.previousElementSibling?.classList.remove('active');
                    }
                });
                
                // Переключаем текущий dropdown
                menu.classList.toggle('show');
                dropdownToggle.classList.toggle('active');
                dropdownToggle.setAttribute('aria-expanded', menu.classList.contains('show'));
            }
        } else {
            // Закрываем все dropdown при клике вне их
            if (!e.target.closest('.dropdown')) {
                document.querySelectorAll('.dropdown-menu.show').forEach(menu => {
                    menu.classList.remove('show');
                    menu.previousElementSibling?.classList.remove('active');
                    const toggle = menu.parentElement.querySelector('[data-dropdown-toggle]');
                    if (toggle) {
                        toggle.setAttribute('aria-expanded', 'false');
                    }
                });
            }
        }
    });
    
    // Закрытие dropdown при клике на пункт меню
    document.addEventListener('click', function(e) {
        const dropdownItem = e.target.closest('.dropdown-item');
        if (dropdownItem && !dropdownItem.hasAttribute('data-keep-open')) {
            const dropdown = dropdownItem.closest('.dropdown');
            const menu = dropdown?.querySelector('.dropdown-menu');
            if (menu) {
                menu.classList.remove('show');
                const toggle = dropdown.querySelector('[data-dropdown-toggle]');
                if (toggle) {
                    toggle.classList.remove('active');
                    toggle.setAttribute('aria-expanded', 'false');
                }
            }
        }
    });
});

