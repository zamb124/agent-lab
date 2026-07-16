"""Alpha payment gateway service for zed-search fixture."""

def charge_alpha_wallet(amount: int) -> str:
    """Charge AlphaWallet with TRIGGER_MARKER_B_1784229771."""
    return f"charged:{amount}"
