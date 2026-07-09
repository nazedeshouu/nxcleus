"""Shared harness helpers: RFC-6902 patching and deterministic rehydration."""
from app.seats._common import apply_rfc6902, rehydrate_tokens


def test_apply_replace_and_add_and_remove():
    doc = {"modules": [{"id": "m1", "name": "old"}], "risks": ["a"]}
    out = apply_rfc6902(doc, [
        {"op": "replace", "path": "/modules/0/name", "value": "new"},
        {"op": "add", "path": "/risks/-", "value": "b"},
        {"op": "add", "path": "/modules/0/complexity", "value": "L"},
        {"op": "remove", "path": "/risks/0"},
    ])
    assert out["modules"][0]["name"] == "new"
    assert out["modules"][0]["complexity"] == "L"
    assert out["risks"] == ["b"]
    # original untouched (deep copy)
    assert doc["modules"][0]["name"] == "old"


def test_bad_pointer_raises():
    try:
        apply_rfc6902({"a": 1}, [{"op": "replace", "path": "no-slash", "value": 2}])
    except ValueError:
        return
    raise AssertionError("expected ValueError on bad pointer")


def test_rehydrate_counts_and_replaces():
    plan = {"modules": [{"assumptions": ["«TABLE_A» has a key", "join «TABLE_A» to «TABLE_B»"]}],
            "note": "no placeholders here"}
    out, n = rehydrate_tokens(plan, {"«TABLE_A»": "customers", "«TABLE_B»": "accounts"})
    assert n == 3  # «TABLE_A» twice + «TABLE_B» once
    assert out["modules"][0]["assumptions"][1] == "join customers to accounts"
    assert out["note"] == "no placeholders here"
