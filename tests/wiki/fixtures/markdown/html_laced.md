# Файл с сырым HTML

Реальные выгрузки полны HTML: так его пишут генераторы и так правят руками.

<div class="callout-wrapper">
  <p>Абзац внутри <b>div</b> с <i>курсивом</i> и <code>кодом</code>.</p>
  <p>Второй абзац с переносом<br>после тега br.</p>
</div>

<details>
  <summary>Свёрнутый раздел</summary>
  <p>Содержимое раздела.</p>
  <ul>
    <li>первый пункт</li>
    <li>второй пункт</li>
  </ul>
</details>

Строка с <mark>подсветкой</mark>, <s>зачёркиванием</s> и <a href="https://example.com/html">ссылкой</a>.

<img src="https://example.com/from-html.png" alt="Из HTML" title="Подпись">

<table>
  <thead>
    <tr><th>Ключ</th><th>Значение</th></tr>
  </thead>
  <tbody>
    <tr><td>один</td><td>1</td></tr>
  </tbody>
</table>

<blockquote>Цитата из HTML</blockquote>

<hr>

<h3>Заголовок тегом</h3>

<script>alert('этого в документе быть не должно')</script>
<style>.x { color: red }</style>
<iframe src="https://example.com/embed"></iframe>

<span style="color: red">Текст в span</span> остаётся текстом.

<sup>верхний индекс</sup> и <sub>нижний</sub> схема не знает.
