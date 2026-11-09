import pytest
from playwright.async_api import Page, ViewportSize
from tests.ui.e2e.stock_e2e_helpers import stock_e2e_nav, stock_e2e_op, stock_e2e_open, stock_e2e_open_transfer, stock_e2e_transfer_action
from tests.ui.harness import AppUI

@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_probe(stock_ui: AppUI, ui_page_system: Page, unique_id: str):
    page = ui_page_system
    await page.set_viewport_size(ViewportSize(width=1440, height=900))
    await stock_e2e_open(page, stock_ui)
    warehouses = await stock_e2e_op(page, "stock/warehouses", "stock/warehouses/list_requested")
    print("WAREHOUSES:", [(w["code"], w["warehouse_id"]) for w in warehouses["items"]])
    codes=[w["code"] for w in warehouses["items"]]
    code=("0"+min(codes)) if codes else "MAIN"
    wh = await stock_e2e_op(page,"stock/warehouse_create","stock/warehouse_create/requested",{"code":code,"name":f"W {unique_id[:4]}"})
    wid=wh["warehouse_id"]; print("WH:",wid,code)
    uoms = await stock_e2e_op(page, "stock/uoms_list", "stock/uoms_list/requested")
    uom=next(u["uom_id"] for u in uoms["items"] if u["name"]=="Units")
    prod = await stock_e2e_op(page,"stock/product_create","stock/product_create/requested",
        {"name":f"P {unique_id[:4]}","sku":f"S-{unique_id[:6]}","uom_id":uom,"valuation_method":"fifo","standard_price":"0","tracking":"none","is_storable":True})
    pid=prod["product_id"]
    ots = await stock_e2e_op(page,"stock/operation_types_list","stock/operation_types_list/requested",{"warehouse_id":wid})
    op_in=next(o["operation_type_id"] for o in ots["items"] if o["code"]=="incoming")
    tr = await stock_e2e_op(page,"stock/transfer_create","stock/transfer_create/requested",
        {"warehouse_id":wid,"operation_type_id":op_in,"moves":[{"product_id":pid,"product_qty":"12","uom_id":uom,"unit_price":"450"}]})
    tid=tr["transfer_id"]; print("TR:",tid,tr["state"])
    await stock_e2e_nav(page,1,page_selector="stock-transfers-page")
    await stock_e2e_open_transfer(page,tid)
    await stock_e2e_transfer_action(page,0,"stock/transfer_confirm","assigned")
    await stock_e2e_transfer_action(page,2,"stock/transfer_validate","done")
    d = await stock_e2e_op(page,"stock/transfer_item","stock/transfer_item/requested",{"transfer_id":tid})
    print("DETAIL STATE:", d["transfer"]["state"])
    print("LINES:", [(l.get("product_id"),l.get("quantity"),l.get("done_quantity")) for l in d.get("lines",[])])
    await stock_e2e_nav(page,0,page_selector="stock-home-page")
    import asyncio; await asyncio.sleep(3)
    pulse = await stock_e2e_op(page,"stock/warehouse_pulse","stock/warehouse_pulse/requested",{"warehouse_id":wid})
    print("PULSE QUANTS:", pulse.get("quants"))
    print("PULSE TRANSFERS:", [(t.get("name"),t.get("state")) for t in pulse.get("transfers",[])])
