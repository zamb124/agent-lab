/**
 * Строгий доступ к свойству unknown-значения в тестовых assert'ах:
 * throw вместо каста — неудача указывает на отсутствующее поле.
 */
export function prop(it: unknown, key: string): unknown {
    if (typeof it !== 'object' || it === null || !(key in it)) {
        throw new Error(`prop: value has no "${key}"`);
    }
    return Reflect.get(it, key);
}

export function dig(it: unknown, ...path: readonly string[]): unknown {
    let cur = it;
    for (const key of path) {
        cur = prop(cur, key);
    }
    return cur;
}

export function digOr(it: unknown, ...path: readonly string[]): unknown {
    let cur = it;
    for (const key of path) {
        if (typeof cur !== 'object' || cur === null || !(key in cur)) {
            return undefined;
        }
        cur = Reflect.get(cur, key);
    }
    return cur;
}
