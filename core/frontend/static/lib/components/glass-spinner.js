/**
 * glass-spinner — совместимый тег единого спиннера платформы.
 * Рендерит вращающийся логотип Linnex через PlatformSpinner.
 */
import { PlatformSpinner } from './platform-spinner.js';

export class GlassSpinner extends PlatformSpinner {}

customElements.define('glass-spinner', GlassSpinner);
