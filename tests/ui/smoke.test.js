import { LitElement } from 'lit';
import { expect, fixture, html } from './helpers/render.js';

class SmokeTestElement extends LitElement {
  render() {
    return html`<span class="smoke-marker">ok</span>`;
  }
}

customElements.define('smoke-test-element', SmokeTestElement);

describe('ui runner smoke', () => {
  it('монтирует Lit-элемент и видит shadow DOM', async () => {
    const el = await fixture(html`<smoke-test-element></smoke-test-element>`);
    const marker = el.shadowRoot.querySelector('.smoke-marker');
    expect(marker.textContent.trim()).to.equal('ok');
  });
});
