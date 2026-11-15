/**
 * Барьер между сканами и переходами сессии ТСД.
 *
 * Коммит и продолжение документа (`scan_commit` → `scan_open`)
 * переписывают session-контекст из run-компонента, а сканы обрабатывает
 * очередь home-страницы — без барьера скан, пришедший посреди перехода,
 * уходил бы в scan_step со старым контекстом (например, `review` уже
 * проведённой строки) и применялся к чужому шагу или терялся с ошибкой.
 * Физически оператор сканирует не глядя на экран, поэтому скан во время
 * перехода — нормальный случай: его надо подержать, а не ронять.
 */

let _transition: Promise<void> | null = null;

/** Оборачивает переход сессии: сканы, пришедшие пока `work` в полёте,
 *  подождут его завершения в `tsdScanIdle`. */
export function tsdScanTransition<T>(work: () => Promise<T>): Promise<T> {
    const result = work();
    const transition = result.then(
        () => undefined,
        () => undefined,
    );
    _transition = transition;
    void transition.finally(() => {
        if (_transition === transition) _transition = null;
    });
    return result;
}

/** Ждёт окончания текущего перехода сессии (no-op, если его нет). */
export async function tsdScanIdle(): Promise<void> {
    await _transition;
}

/**
 * Один повтор идемпотентной ops при отказе транспорта.
 *
 * Таймаут WS-операции не означает, что backend её не выполнил:
 * применять повтор можно только там, где повтор безопасен —
 * claim/bind/commit идемпотентны (`idempotency_key` у commit,
 * повторная привязка ресурса и повторный `scan_open` возвращают то же
 * состояние), а `scan_step` вообще чистая функция контекста без
 * записей — повтор даёт тот же исход без двойного эффекта.
 * Физически это повторный «пип» сканера, который оператор на плохом
 * Wi-Fi склада сделал бы сам — но без потери темпа.
 */
export async function tsdOpRetry<T>(work: () => Promise<T | null>): Promise<T | null> {
    const first = await work();
    if (first !== null) return first;
    return work();
}
