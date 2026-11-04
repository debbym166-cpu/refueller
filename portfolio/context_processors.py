from .services import wallet_balance


def litrevault(request):
    """Gives every page the logged-in user's name, initials and litre balance
    (used by the sidebar), so the templates never show hard-coded demo data."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    name = user.get_full_name().strip() or user.username.split("@")[0]
    parts = [p for p in name.replace(".", " ").replace("_", " ").split() if p]
    initials = "".join(p[0] for p in parts[:2]).upper() or name[:2].upper()
    return {
        "lv_name": name,
        "lv_initials": initials,
        "lv_balance": wallet_balance(user),
    }
