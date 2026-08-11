"""Vendor-specific adapter implementations (Phase 3B/3C).

Each module here implements one or more of the ABCs in `app.adapters.base`
against one real vendor's documented contract. Nothing outside this
package -- and nothing outside `app.adapters` at all -- may import a vendor
SDK or hardcode a vendor's field names (Volume 2 §8's adapter-isolation
rule, enforced structurally by 3A's shared interface).
"""
