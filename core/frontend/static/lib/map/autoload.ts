/**
 * Self-contained бандл `<platform-map>` для внешних страниц (витрина shop).
 * Собирается в `core/frontend/embed-dist/map/autoload.js` и отдаётся по
 * `/static/core/lib/map/autoload.js`. MapLibre и PMTiles грузятся lazy
 * самим компонентом — бандл только регистрирует тэг.
 */
import '../components/platform-map.js';
