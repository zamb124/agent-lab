/**
 * modal-registry: единственный источник правды kind -> tagName.
 */

import { expect } from '../helpers/render.js';
import { registerModalKind, getModalTag, hasModalKind, listModalKinds } from '@platform/lib/utils/modal-registry.js';

describe('modal-registry', () => {
    it('kind должен соответствовать <scope>.<name> snake_case', () => {
        expect(() => registerModalKind('Bad', 'tag')).to.throw(/pattern/);
        expect(() => registerModalKind('foo', 'tag')).to.throw(/pattern/);
        expect(() => registerModalKind('foo.bar.baz', 'tag')).to.throw(/pattern/);
        expect(() => registerModalKind('Foo.bar', 'tag')).to.throw(/pattern/);
    });

    it('tagName обязателен', () => {
        expect(() => registerModalKind('platform.t1', '')).to.throw(/tagName/);
    });

    it('повторная регистрация того же kind с тем же tag — идемпотентна', () => {
        registerModalKind('platform.t_idempotent', 'frontend-core-tag-x');
        expect(() => registerModalKind('platform.t_idempotent', 'frontend-core-tag-x')).not.to.throw();
    });

    it('повторная с другим tag — throw', () => {
        registerModalKind('platform.t_collision', 'frontend-core-tag-a');
        expect(() => registerModalKind('platform.t_collision', 'frontend-core-tag-b')).to.throw(/already registered/);
    });

    it('hasModalKind / getModalTag', () => {
        registerModalKind('platform.t_lookup', 'frontend-core-tag-y');
        expect(hasModalKind('platform.t_lookup')).to.be.true;
        expect(getModalTag('platform.t_lookup')).to.equal('frontend-core-tag-y');
    });

    it('getModalTag для незарегистрированного — throw', () => {
        expect(() => getModalTag('platform.never_registered')).to.throw(/not registered/);
    });

    it('listModalKinds возвращает отсортированный массив', () => {
        const list = listModalKinds();
        expect(Array.isArray(list)).to.be.true;
        const sorted = [...list].sort();
        expect(list).to.deep.equal(sorted);
    });
});
