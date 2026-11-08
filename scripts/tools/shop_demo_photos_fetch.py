"""Скачивает curated-фото для demo-витрин в ``apps/shop/seed/assets/``.

``python -m scripts.tools.shop_demo_photos_fetch [--check-only]``

Манифест ``MANIFEST``: ``(template, filename) -> unsplash CDN id``.
Источник — images.unsplash.com (CDN-публичные фото Unsplash), ширина
1200px, JPEG q80. Итоговые файлы + атрибуция фиксируются в
``apps/shop/seed/assets/CREDITS.md`` (генерируется этим скриптом).
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

ASSETS = (
    Path(__file__).resolve().parent.parent.parent / "apps" / "shop" / "seed" / "assets"
)

# (template, filename) -> (unsplash_id, короткое описание содержимого)
MANIFEST: dict[tuple[str, str], tuple[str, str]] = {
    # ── cafe ──────────────────────────────────────────────────────
    ("cafe", "cover.jpg"): ("1445116572660-236099ec97a0", "coffee shop bar"),
    ("cafe", "espresso.jpg"): ("1510591509098-f4fdc6d0ff04", "espresso cup"),
    ("cafe", "americano.jpg"): ("1509042239860-f550ce710b93", "black coffee"),
    ("cafe", "cappuccino.jpg"): ("1497515114629-f71d768fd07c", "cappuccino"),
    ("cafe", "latte.jpg"): ("1541167760496-1628856ab772", "latte art"),
    ("cafe", "flatwhite.jpg"): ("1572442388796-11668a67e53d", "flat white"),
    ("cafe", "raf.jpg"): ("1512568400610-62da28bc8a13", "raf coffee"),
    ("cafe", "matcha.jpg"): ("1536256263959-770b48d82b0a", "matcha latte"),
    ("cafe", "oolong.jpg"): ("1564890369478-c89ca6d9cde9", "tea cup"),
    ("cafe", "filter.jpg"): ("1442512595331-e89e73853f31", "pour over"),
    ("cafe", "cacao.jpg"): ("1517578239113-b03992dcdd25", "hot chocolate"),
    ("cafe", "cookie.jpg"): ("1499636136210-6f4ee915583e", "cookies"),
    ("cafe", "croissant.jpg"): ("1555507036-ab1f4038808a", "croissant"),
    ("cafe", "cheesecake.jpg"): ("1565958011703-44f9829ba187", "berry dessert"),
    ("cafe", "tiramisu.jpg"): ("1571877227200-a0d98ea607e9", "tiramisu"),
    ("cafe", "syrniki.jpg"): ("1567620905732-2d1ec7ab7445", "pancakes"),
    ("cafe", "avocado.jpg"): ("1541519227354-08fa5d50c44d", "avocado toast"),
    ("cafe", "sandwich.jpg"): ("1528735602780-2552fd46c7af", "sandwich"),
    ("cafe", "bowl.jpg"): ("1546069901-ba9599a7e63c", "salad bowl"),
    ("cafe", "espton.jpg"): ("1556679343-c7306c1976bc", "espresso tonic"),
    ("cafe", "banner_autumn.jpg"): ("1459755486867-b55449bb39ff", "coffee beans"),
    ("cafe", "banner_loyal.jpg"): ("1453614512568-c4024d13c247", "cafe counter"),
    ("cafe", "banner_morning.jpg"): ("1533089860892-a7c6f0a88666", "breakfast"),
    ("cafe", "opt_vanilla.jpg"): ("1563805042-7684c019e1cb", "vanilla dessert"),
    ("cafe", "opt_caramel.jpg"): ("1551024506-0bccd828d307", "caramel pour"),
    ("cafe", "opt_lavender.jpg"): ("1499002238440-d264edd596ec", "lavender"),
    ("cafe", "opt_raspb.jpg"): ("1577069861033-55d04cec4ef5", "raspberries"),
    ("cafe", "opt_espresso.jpg"): ("1510707577719-ae7c14805e3a", "espresso dark"),
    ("cafe", "opt_cream.jpg"): ("1557142046-c704a3adf364", "cream drink"),
    # ── bakery ────────────────────────────────────────────────────
    ("bakery", "cover.jpg"): ("1509440159596-0249088772ff", "bread loaves"),
    ("bakery", "baguette.jpg"): ("1568254183919-78a4f43a2877", "baguettes"),
    ("bakery", "borodino.jpg"): ("1549931319-a545dcf3bc73", "dark bread"),
    ("bakery", "brioche.jpg"): ("1530610476181-d83430b64dcd", "brioche"),
    ("bakery", "campagne.jpg"): ("1589367920969-ab8e050bbb04", "country bread"),
    ("bakery", "almond.jpg"): ("1623334044303-241021148842", "almond croissant"),
    ("bakery", "cinnamon.jpg"): ("1509365465985-25d11c17e812", "cinnamon roll"),
    ("bakery", "eclair.jpg"): ("1774119649906-c82806125e23", "vanilla eclair"),
    ("bakery", "honeycake.jpg"): ("1571115177098-24ec42ed204d", "honey cake"),
    ("bakery", "lemontart.jpg"): ("1519915028121-7d3463d20b13", "lemon tart"),
    ("bakery", "napoleon.jpg"): ("1578985545062-69928b1d9587", "layer cake"),
    ("bakery", "potato.jpg"): ("1583338917451-face2751d8d5", "savory pastry"),
    ("bakery", "cookie.jpg"): ("1558961363-fa8fdf82db35", "cookies"),
    ("bakery", "cacao.jpg"): ("1517578239113-b03992dcdd25", "cacao drink"),
    ("bakery", "lemonade.jpg"): ("1523677011781-c91d1bbe2f9e", "lemonade"),
    ("bakery", "berrycake.jpg"): ("1608830597604-619220679440", "berry cake"),
    ("bakery", "banner_morning.jpg"): ("1517433670267-08bbd4be890f", "bakery case"),
    ("bakery", "banner_evening.jpg"): ("1483695028939-5bb13f8648b0", "croissants"),
    ("bakery", "opt_gift.jpg"): ("1513201099705-a9746e1e201f", "gift box"),
    # ── pizza ─────────────────────────────────────────────────────
    ("pizza", "cover.jpg"): ("1534308983496-4fabb1a015ee", "pizza slice"),
    ("pizza", "margherita.jpg"): ("1574071318508-1cdbab80d002", "margherita"),
    ("pizza", "pepperoni.jpg"): ("1513104890138-7c749659a591", "pepperoni"),
    ("pizza", "fourcheez.jpg"): ("1595854341625-f33ee10dbf94", "cheese pizza"),
    ("pizza", "hawaiian.jpg"): ("1565299624946-b28f40a0ae38", "pizza slice"),
    ("pizza", "meat.jpg"): ("1590947132387-155cc02f3212", "meat pizza"),
    ("pizza", "mushroom.jpg"): ("1604382354936-07c5d9983bd3", "mushroom pizza"),
    ("pizza", "truffle.jpg"): ("1593560708920-61dd98c46a4e", "pizza oven"),
    ("pizza", "burrata.jpg"): ("1595708684082-a173bb3a06c5", "pizza white"),
    ("pizza", "bbq.jpg"): ("1571407970349-bc81e7e96d47", "bbq pizza"),
    ("pizza", "caesar.jpg"): ("1546793665-c74683f339c1", "caesar salad"),
    ("pizza", "combo.jpg"): ("1594007654729-407eedc4be65", "pizza combo"),
    ("pizza", "wings.jpg"): ("1608039755401-742074f0548d", "chicken wings"),
    ("pizza", "fries.jpg"): ("1541592106381-b31e9677c0e5", "french fries"),
    ("pizza", "fondant.jpg"): ("1606313564200-e75d5e30476c", "lava cake"),
    ("pizza", "tiramisu.jpg"): ("1571877227200-a0d98ea607e9", "tiramisu"),
    ("pizza", "lemonade.jpg"): ("1621263764928-df1444c5e859", "lemonade"),
    ("pizza", "cola.jpg"): ("1581636625402-29b2a704ef13", "cola glass"),
    ("pizza", "mors.jpg"): ("1553530666-ba11a7da3888", "berry drink"),
    ("pizza", "garlic.jpg"): ("1540148426945-6cf22a6b2383", "garlic"),
    ("pizza", "hotsauce.jpg"): ("1596040033229-a9821ebd058d", "chili spices"),
    ("pizza", "bbqsauce.jpg"): ("1472476443507-c7a5948772fc", "bbq sauce"),
    ("pizza", "saucerr.jpg"): ("1571212515416-fef01fc43637", "white sauce"),
    ("pizza", "banner_pizza.jpg"): ("1600028068383-ea11a7a101f3", "pizza slices"),
    ("pizza", "banner_promo.jpg"): ("1600628421060-939639517883", "pizza sharing"),
    ("pizza", "banner_season.jpg"): ("1542834369-f10ebf06d3e0", "cheese pull"),
    ("pizza", "opt_pep.jpg"): ("1628840042765-356cda07504e", "pepperoni"),
    ("pizza", "opt_bacon.jpg"): ("1528607929212-2636ec44253e", "bacon pan"),
    ("pizza", "opt_arugula.jpg"): ("1512621776951-a57141f2eefd", "arugula bowl"),
    ("pizza", "opt_parm.jpg"): ("1618164435735-413d3b066c9a", "parmesan"),
    ("pizza", "opt_dorblu.jpg"): ("1626957341926-98752fc2ba90", "blue cheese"),
    # ── market ────────────────────────────────────────────────────
    ("market", "cover.jpg"): ("1542838132-92c53300491e", "produce stand"),
    ("market", "apples.jpg"): ("1560806887-1e4cd0b6cbd6", "red apples"),
    ("market", "bananas.jpg"): ("1571771894821-ce9b6c11b08e", "bananas"),
    ("market", "tomatoes.jpg"): ("1546094096-0df4bcaaa337", "tomatoes"),
    ("market", "potatoes.jpg"): ("1518977676601-b53f82aba655", "potatoes"),
    ("market", "vegmix.jpg"): ("1540420773420-3366772f4999", "vegetables"),
    ("market", "chicken.jpg"): ("1587593810167-a84920ea0781", "roast chicken"),
    ("market", "sausages.jpg"): ("1585325701165-351af916e581", "sausages"),
    ("market", "doktor.jpg"): ("1607623814075-e51df1bdc82f", "deli meats"),
    ("market", "cheese.jpg"): ("1486297678162-eb2a19b0a32d", "cheese plate"),
    ("market", "parmesan.jpg"): ("1618164435735-413d3b066c9a", "parmesan"),
    ("market", "tvorog.jpg"): ("1488477181946-6428a0291777", "curd dessert"),
    ("market", "kefir.jpg"): ("1550583724-b2692b85b150", "milk bottle"),
    ("market", "milk32.jpg"): ("1563636619-e9143da7973b", "milk"),
    ("market", "smetana.jpg"): ("1571212515416-fef01fc43637", "sour cream"),
    ("market", "buns.jpg"): ("1608198093002-ad4e005484ec", "buns"),
    ("market", "darnitsky.jpg"): ("1549931319-a545dcf3bc73", "dark bread"),
    ("market", "rice.jpg"): ("1586201375761-83865001e31c", "rice"),
    ("market", "buckwheat.jpg"): ("1610725664285-7c57e6eeac3f", "grains"),
    ("market", "pasta.jpg"): ("1551462147-ff29053bfc14", "dry pasta"),
    ("market", "pelmeni.jpg"): ("1496116218417-1a781b1c416c", "dumplings"),
    ("market", "honey.jpg"): ("1587049352851-8d4e89133924", "honey jar"),
    ("market", "coffee.jpg"): ("1559056199-641a0ac8b55e", "coffee beans"),
    ("market", "tea.jpg"): ("1544787219-7f47ccb76574", "tea brewing"),
    ("market", "juice.jpg"): ("1600271886742-f049cd451bba", "orange juice"),
    ("market", "cola2.jpg"): ("1554866585-cd94860890b7", "soda bottle"),
    ("market", "water5.jpg"): ("1616118132534-381148898bb4", "water bottle"),
    ("market", "powder.jpg"): ("1583947215259-38e31be8751f", "detergent"),
    ("market", "gel.jpg"): ("1556228720-195a672e8a03", "cosmetic bottle"),
    ("market", "strawberry.jpg"): ("1464965911861-746a04b4bca6", "strawberries"),
    ("market", "banner_delivery.jpg"): ("1588964895597-cfccd6e2dbf9", "grocery bag"),
    ("market", "banner_fresh.jpg"): ("1488459716781-31db52582fe9", "produce stand"),
}

_URL = "https://images.unsplash.com/photo-{uid}?q=80&w=1200&auto=format&fit=crop"
_UA = {"User-Agent": "agent-lab-seed-fetch/1.0"}


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    missing: list[tuple[str, str, str]] = []
    downloaded = skipped = 0
    for (tpl, filename), (uid, desc) in sorted(MANIFEST.items()):
        target = ASSETS / tpl / filename
        if target.exists() and target.stat().st_size > 10_000:
            skipped += 1
            continue
        if args.check_only:
            missing.append((tpl, filename, uid))
            continue
        try:
            data = _fetch(_URL.format(uid=uid))
        except Exception as exc:  # noqa: BLE001
            missing.append((tpl, filename, f"{uid}: {exc}"))
            continue
        if not data.startswith(b"\xff\xd8") or len(data) < 10_000:
            missing.append((tpl, filename, f"{uid}: not-jpeg/{len(data)}B"))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        downloaded += 1
        print(f"ok {tpl}/{filename} <- {uid} ({desc}) {len(data)//1024}KB")

    print(f"downloaded={downloaded} skipped={skipped} problems={len(missing)}")
    for tpl, filename, err in missing:
        print(f"  MISSING {tpl}/{filename} {err}")

    if not args.check_only and not missing:
        lines = [
            "# Demo-фото витрин",
            "",
            "Источник: Unsplash CDN (images.unsplash.com), w=1200 q=80.",
            "Сгенерировано `python -m scripts.tools.shop_demo_photos_fetch`.",
            "",
            "| file | unsplash |",
            "|---|---|",
        ]
        for (tpl, filename), (uid, desc) in sorted(MANIFEST.items()):
            lines.append(
                f"| {tpl}/{filename} | "
                f"[photo-{uid}](https://images.unsplash.com/photo-{uid}) "
                f"({desc}) |"
            )
        (ASSETS / "CREDITS.md").write_text("\n".join(lines) + "\n")
        print("CREDITS.md written")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
