import { registerPlatformExtras } from './extras.js';
import { registerPlatformFeed } from './feed.js';
import { registerPlatformForm } from './form.js';
import { registerPlatformLayout } from './layout.js';
import { registerPlatformText } from './text.js';
import { registerPlatformVoice } from './voice.js';

export function registerPlatformCatalog(register) {
    registerPlatformLayout(register);
    registerPlatformText(register);
    registerPlatformForm(register);
    registerPlatformFeed(register);
    registerPlatformExtras(register);
    registerPlatformVoice(register);
}
