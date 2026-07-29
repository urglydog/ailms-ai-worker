"""Anti-corruption layer cho dich vu AI ben ngoai.

Moi provider co httpx.AsyncClient RIENG (bulkhead) va tra dataclass hoac
ProviderError — khong bao gio tra dict tho. Xem base.py.
"""
