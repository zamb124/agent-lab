# Receiving serialized devices: one scan, one unit

**Purpose:** electronics and high-value goods are tracked by serial number — every unit is unique and drives warranty and returns.

**Problems solved:** the terminal knows a serial is always exactly one unit: no quantity field at all, entering the number records one instantly. A duplicate serial is rejected — one unit cannot sit on the warehouse twice.

**Result:** three serialized devices received, one scan each — stock holds three single units under their SNs.

## Step 1. Enter the first device serial

For a serialized product the quantity step is a single serial field, no numpad: the system sets quantity 1 itself. The line is recorded right after confirming.

![Enter the first device serial](stock-tsd-serials--01-tsd-serial-entry.png)

## Step 2. Add the remaining serials

Each serial is its own execution line: after recording, scan the product and enter the next number. The lines list shows every SN before commit.

![Add the remaining serials](stock-tsd-serials--02-tsd-serial-lines.png)

## Step 3. Scan the bin — three devices on stock

**Result demonstration.** The bin shows stock «3» — three received devices, each under its own serial. The system recognises the exact unit on shipment and returns.

**Summary.** Serialized stock is received one scan per unit — no quantity field; a duplicate number is rejected.

![Scan the bin — three devices on stock](stock-tsd-serials--03-tsd-serial-bin-contents.png)
