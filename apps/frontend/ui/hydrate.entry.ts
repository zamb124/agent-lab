// Бутстрап гидратации DSD-снапшотов — отдельная entry-сборка.
// lit-element читает globalThis.litElementHydrateSupport при эвалюации своего
// модуля, а тело index.js исполняется после всех импортов чанков — импорт
// патча из тела index.js опаздывал бы. Файл подключается
// <script type="module"> до index.js и делает патч shared-чанком,
// исполняемым первым импортом index.js.
import '@lit-labs/ssr-client/lit-element-hydrate-support.js';
