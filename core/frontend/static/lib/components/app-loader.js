/**
 * app-loader — совместимый тег единого спиннера платформы.
 * Полноэкранная и inline загрузка через PlatformSpinner (вращающийся логотип Linnex).
 */
import '../utils/viewport-app-vh.js';
import '../utils/platform-deeplink-init.js';
import { PlatformSpinner } from './platform-spinner.js';

export class AppLoader extends PlatformSpinner {
    constructor() {
        super();
        this.size = 'xl';
    }
}

customElements.define('app-loader', AppLoader);
