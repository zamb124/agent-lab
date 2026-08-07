import { registerBasicExtras } from './extras.js';
import { registerBasicForm } from './form.js';
import { registerBasicLayout } from './layout.js';
import { registerBasicMedia } from './media.js';
import { registerBasicText } from './text.js';

export function registerBasicCatalog(register) {
    registerBasicLayout(register);
    registerBasicText(register);
    registerBasicMedia(register);
    registerBasicForm(register);
    registerBasicExtras(register);
}
