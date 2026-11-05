/**
 * Геодезические утилиты виджета карты.
 *
 * Сферическая площадь полигона (формула Льюилье/Чемберлена) — достаточна
 * для метрик на зонах городского масштаба (погрешность <0.5%).
 * Периметр — haversine по рингу без замыкающей точки-дубля.
 */

export type LngLatRing = [number, number][];

const R_EARTH = 6_371_008.8;

export function ringAreaM2(ring: LngLatRing): number {
    let sum = 0;
    for (let i = 0; i < ring.length; i++) {
        const [lng1, lat1] = ring[i]!;
        const [lng2, lat2] = ring[(i + 1) % ring.length]!;
        sum += (lng2 - lng1) * (Math.PI / 180) * (2 + Math.sin(lat1 * Math.PI / 180) + Math.sin(lat2 * Math.PI / 180));
    }
    return Math.abs((sum * R_EARTH * R_EARTH) / 2);
}

export function haversineM(a: [number, number], b: [number, number]): number {
    const dLat = ((b[1] - a[1]) * Math.PI) / 180;
    const dLng = ((b[0] - a[0]) * Math.PI) / 180;
    const s =
        Math.sin(dLat / 2) ** 2 +
        Math.cos((a[1] * Math.PI) / 180) * Math.cos((b[1] * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
    return 2 * R_EARTH * Math.asin(Math.min(1, Math.sqrt(s)));
}

export function ringPerimeterM(ring: LngLatRing): number {
    let perim = 0;
    for (let i = 0; i < ring.length - 1; i++) {
        perim += haversineM(ring[i]!, ring[i + 1]!);
    }
    return perim;
}

/** `1200` → `'1.2'` (км), `340` → `'340'` (м). */
export function fmtKm(m: number): string {
    return m >= 1000 ? `${(m / 1000).toFixed(1)}` : `${Math.round(m)}`;
}

/** `1_240_000` → `'1.24'` (км²). */
export function fmtArea(m2: number): string {
    return `${(m2 / 1_000_000).toFixed(2)}`;
}
