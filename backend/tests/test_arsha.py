import urllib.error

import arsha


def test_fetch_market_skips_ids_that_break_the_batch(monkeypatch):
    unknown = {6, 1000114}
    calls = []

    def fake_get_batched(path, item_ids, lang):
        calls.append(list(item_ids))
        if unknown & set(item_ids):
            raise urllib.error.HTTPError(path, 500, "Internal Server Error", {}, None)
        return [{"id": item_id, "basePrice": 100} for item_id in item_ids]

    monkeypatch.setattr(arsha, "_get_batched", fake_get_batched)

    entries = arsha.fetch_market([6, 44195, 752021, 1000114, 10010])

    assert sorted(entry["id"] for entry in entries) == [10010, 44195, 752021]
    assert [6] in calls and [1000114] in calls


def test_fetch_market_propagates_client_errors(monkeypatch):
    def fake_get_batched(path, item_ids, lang):
        raise urllib.error.HTTPError(path, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(arsha, "_get_batched", fake_get_batched)

    try:
        arsha.fetch_market([44195, 10010])
    except urllib.error.HTTPError as error:
        assert error.code == 429
    else:
        raise AssertionError("429 має дійти до виклику")
