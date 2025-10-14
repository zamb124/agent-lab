// Меняем ссылку логотипа на главную страницу приложения
document.addEventListener("DOMContentLoaded", function() {
  const logoLinks = document.querySelectorAll('.md-header__button.md-logo[href], .md-logo[href*="index.html"]');
  logoLinks.forEach(link => {
    link.setAttribute('href', '/');
    link.setAttribute('target', '_blank');
    link.setAttribute('rel', 'noopener noreferrer');
  });
});

