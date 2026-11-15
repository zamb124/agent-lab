# Full warehouse cycle: admin setup → operator shift on the handheld

**Purpose:** a single zero-to-result instruction — from warehouse registration to posted handheld operations.

**Problems solved:** shows the admin needs no programmer — every directory is filled through forms; the operator needs no desktop — all work is done by scans.

**Result:** a warehouse with topology, directories and rules; product received, moved, counted and shipped — all posted to the ledger.

## Step 1. Register the warehouse — topology builds itself

«Settings → Warehouses → Create»: code and name are all you type. The «standard» layout unfolds «Receiving / Stock / Packing / Shipping» zones and «incoming, outgoing, internal» operation types by itself.

![Register the warehouse — topology builds itself](stock-full-lifecycle--01-admin-warehouse-create.png)

## Step 2. Warehouse operation types — ready out of the box

**Result demonstration.** Below the warehouse table are the operation types of the selected warehouse: incoming, outgoing, internal moves. The «auto-validate» toggle and the «default/pack/ship» scan flow are edited inline — they decide which screens the operator gets on the handheld.

![Warehouse operation types — ready out of the box](stock-full-lifecycle--02-admin-warehouse-operations.png)

## Step 3. Create a storage type

«Storage types» are bin classes (rack, floor, cold room): a type carries container, weight and cycle-count limits. A bin then just references a type.

![Create a storage type](stock-full-lifecycle--03-admin-storage-type-form.png)

## Step 4. Create a «pallet» container type

«Container types» are pallets, boxes, carts. A type has a kind (pallet/box/tote/cart), weight and volume limits and a reusable flag. The pallet later becomes a container location and travels the warehouse whole.

![Create a «pallet» container type](stock-full-lifecycle--04-admin-container-type-form.png)

## Step 5. Issue the equipment a barcode badge

«Resources» are equipment and device-people: carts, forklifts, pickers. A resource carries a barcode badge: the operator scans it on the handheld and the equipment binds to the shift — tasks filter to its capabilities.

![Issue the equipment a barcode badge](stock-full-lifecycle--05-admin-resource-form.png)

## Step 6. Add a custom unit of measure

«UoM & packaging»: a custom unit is a name, a category and a factor to the base. «Pack ×12» lets you receive and ship by the box without converting to pieces.

![Add a custom unit of measure](stock-full-lifecycle--06-admin-uom-form.png)

## Step 7. Register the first product

«Products → Create» opens the catalog picker: if the product is already in the shared catalog, attach it in one row; otherwise «Create new». SKU, base UoM and a barcode are the minimum the handheld needs.

![Register the first product](stock-full-lifecycle--07-admin-product-in-table.png)

## Step 8. Bind a package to the product

A package is a «box of 12» with its own barcode: scanning it on the handheld fills product and quantity itself. A dedicated barcode — a dedicated box label.

![Bind a package to the product](stock-full-lifecycle--08-admin-packaging-form.png)

## Step 9. Expand the warehouse on the location map

«Locations» is the warehouse map as a tree: the «standard» preset already made «Receiving / Stock→Pick / Packing / Shipping». Now we add working bins inside the «Stock» zone.

![Expand the warehouse on the location map](stock-full-lifecycle--09-admin-locations-tree.png)

## Step 10. Add a storage bin

«Create child» inside the «Stock» zone: the bin name, its barcode (the shelf sticker) and the storage type — the rack registered a step ago. The barcode is what the operator scans on the floor.

![Add a storage bin](stock-full-lifecycle--10-admin-location-bin-form.png)

## Step 11. Register a pallet as a container location

The same «child» location but «container» usage: a pallet is a movable bin — its contents travel with it. Type — the pallet from the container directory, barcode — the tag on its side.

![Register a pallet as a container location](stock-full-lifecycle--11-admin-location-pallet-form.png)

## Step 12. The map is ready: zone, bins and a pallet

**Result demonstration.** Under «Stock» in the tree — two rack bins and a pallet. Each has a barcode — time for putaway rules.

![The map is ready: zone, bins and a pallet](stock-full-lifecycle--12-admin-locations-ready.png)

## Step 13. Assign a putaway rule

«Putaway rules» answer «where does incoming stock go»: from the receiving zone into a concrete bin. On the handheld this rule becomes the «put into A-01» hint.

![Assign a putaway rule](stock-full-lifecycle--13-admin-putaway-rule-form.png)

## Step 14. Set the bin's min and max stock

«Reorder rules» guard the bin: stock below the minimum — the system suggests a replenishment up to the maximum with the given document kind.

![Set the bin's min and max stock](stock-full-lifecycle--14-admin-reorder-rule-form.png)

## Step 15. Setup complete — the warehouse is shift-ready

**Result demonstration.** Every directory was filled with UI forms only: a warehouse with topology, storage and container types, badged equipment, units and packaging, barcoded products, bins and a pallet, putaway and reorder rules, a route.

**Next** — hand the terminal to the operator.

![Setup complete — the warehouse is shift-ready](stock-full-lifecycle--15-admin-setup-done.png)

## Step 16. Take the handheld and pick the warehouse

The handheld opens with the warehouse list — the operator picks theirs once per shift. It shows only what the admin registered through forms.

![Take the handheld and pick the warehouse](stock-full-lifecycle--16-tsd-warehouse-picked.png)

## Step 17. Badge scan — shift bound to the equipment

The forklift barcode opened the resource card, the «bind» button claimed it for the shift on the server — the equipment chip shows the code. No password needed: the badge IS the credential.

![Badge scan — shift bound to the equipment](stock-full-lifecycle--17-tsd-resource-bound.png)

## Step 18. Product scan — card with photo and actions

Scanning any product from any screen opens its card: photo, per-bin stock and «move / receive / putaway / count» actions. The operator doesn't need to remember where anything is.

![Product scan — card with photo and actions](stock-full-lifecycle--18-tsd-product-card.png)

## Step 19. Receiving: product → bin → qty → slide

The receiving machine walks scan by scan: product barcode, destination bin barcode, quantity on the big keypad — then a left-to-right slide commits. The slide can't fire from an accidental glove touch.

![Receiving: product → bin → qty → slide](stock-full-lifecycle--19-tsd-receive-review.png)

## Step 20. Bin scan — the stock is there

**Result demonstration.** The A-01 bin barcode shows the received coffee ×8 — the receipt is in the ledger. Bin actions are available right here too.

![Bin scan — the stock is there](stock-full-lifecycle--20-tsd-bin-contents.png)

## Step 21. Count right on the spot

The «count» action from the bin card: product scan → actual quantity → commit. A discrepancy would be recorded by the system itself — here books match reality.

![Count right on the spot](stock-full-lifecycle--21-tsd-count-review.png)

## Step 22. Move: from → where → how many

The move flow mirrors the physics: confirm the pick bin by scan, arrive at the target bin — scan it too, enter the quantity. Direction can't flip — source and destination are separate scans.

![Move: from → where → how many](stock-full-lifecycle--22-tsd-move-review.png)

## Step 23. Order scan — the document goes to work

The ERP order resolves into a document card: number and line count. «Start execution» opens a session — the backend picked the «pick» flow itself from the operation type.

![Order scan — the document goes to work](stock-full-lifecycle--23-tsd-document-card.png)

## Step 24. The terminal suggests what to pick

The amber strip is the backend hint from the open order line: bin → product × qty. The operator walks to that bin — no need to hunt for the order.

![The terminal suggests what to pick](stock-full-lifecycle--24-tsd-document-expected.png)

## Step 25. Second line — the document leads itself

After the first line posted, the session did not close — the backend suggested the next order line. No queue round-trip between trips.

![Second line — the document leads itself](stock-full-lifecycle--25-tsd-document-line2.png)

## Step 26. The pallet travels whole — one scan instead of carrying

Scan the pallet tag → «move» → scan the target bin: all contents (coffee ×6) travel with the container in one posting. Real warehouse physics — the container is the unit.

![The pallet travels whole — one scan instead of carrying](stock-full-lifecycle--26-tsd-pallet-move.png)

## Step 27. The shift ran the full cycle

**Result demonstration.** Two products received, a count posted, a bin-to-bin move, a two-line order pick and a pallet move — all with scans and slides, on entities the admin created through forms.

**Summary.** «Set up the warehouse → hand over the terminal → the warehouse runs» — registration to ledger with no code and no paper.

![The shift ran the full cycle](stock-full-lifecycle--27-tsd-shift-done.png)
