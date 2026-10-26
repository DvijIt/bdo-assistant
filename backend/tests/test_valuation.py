import arsha
from conftest import destination, inventory_item, item, snapshot


MARKET = {
    44195: [{"minEnhance": 0, "maxEnhance": 0, "basePrice": 2_000_000}],  # Memory Fragment
    # Зброя: +0..+7 продається однією позицією, PEN — окремою.
    10010: [
        {"minEnhance": 0, "maxEnhance": 7, "basePrice": 30_000_000},
        {"minEnhance": 20, "maxEnhance": 20, "basePrice": 1_700_000_000},
    ],
    752021: [{"minEnhance": 0, "maxEnhance": 0, "basePrice": 0}],  # не продається
}


def make_fake_market(calls):
    def fake_fetch_market(item_ids, region="eu", lang="en"):
        calls.append(list(item_ids))
        return [
            {"id": item_id, **entry}
            for item_id in item_ids
            for entry in MARKET.get(item_id, [])
        ]

    return fake_fetch_market


def import_account(client):
    data = snapshot(
        inventory_items=[
            inventory_item(10010 | (20 << 24), 1, "0x01", 0, "Main Inventory"),  # PEN
            inventory_item(752021, 13, "0x02", 11, "Enhancement Inventory"),
        ],
        currencies=[item(1, 5_000_000, "0x03", container_code=0, container_name="Global Currencies")],
        destinations=[
            destination(202, "Altinova", [item(44195, 10, "0x04"), item(10010 | (3 << 24), 1, "0x05")]),
            destination(1, "Velia", [item(44195, 5, "0x06"), item(999999, 1, "0x07")]),
            # Два окремі екземпляри в одному місті — це не дублікат між складами.
            destination(5, "Heidel", [item(10010, 1, "0x08"), item(10010, 1, "0x09"), item(999999, 1, "0x0A")]),
        ],
    )
    assert client.post("/api/snapshots", json=data).status_code == 201


def test_account_value_uses_enhancement_ranges_and_silver(client, monkeypatch):
    monkeypatch.setattr(arsha, "fetch_market", make_fake_market([]))
    import_account(client)

    assert client.post("/api/prices/refresh").status_code == 200
    account = client.get("/api/account").json()

    # PEN 1.7B + (+3 у діапазоні 0..7) 30M + два +0 у Heidel 60M + 15 × 2M
    assert account["items_value"] == 1_700_000_000 + 30_000_000 + 60_000_000 + 15 * 2_000_000
    assert account["silver"] == 5_000_000
    assert account["total_value"] == account["items_value"] + 5_000_000
    # Black Stone поза ринком, 999999 (двічі) ринок не знає
    assert account["unpriced_stacks"] == 3
    assert account["top_items"][0]["value"] == 1_700_000_000
    assert account["by_container"][0]["name"] == "Main Inventory"


def test_duplicates_across_towns(client, monkeypatch):
    monkeypatch.setattr(arsha, "fetch_market", make_fake_market([]))
    import_account(client)
    client.post("/api/prices/refresh")

    duplicates = client.get("/api/account").json()["duplicates"]

    assert [(d["item_id"], d["quantity"], d["value"]) for d in duplicates] == [
        (44195, 15, 30_000_000),
        (999999, 2, None),  # поза ринком, але все одно в двох містах
    ]
    assert {p["container"] for p in duplicates[0]["places"]} == {"Altinova", "Velia"}


def test_off_market_items_are_not_refetched_unless_full(client, monkeypatch):
    calls = []
    monkeypatch.setattr(arsha, "fetch_market", make_fake_market(calls))
    import_account(client)

    client.post("/api/prices/refresh")
    client.post("/api/prices/refresh")
    client.post("/api/prices/refresh?full=true")

    assert calls[0] == [10010, 44195, 752021, 999999]
    assert calls[1] == [10010, 44195]
    assert calls[2] == calls[0]


def test_holdings_include_unit_price_and_value(client, monkeypatch):
    monkeypatch.setattr(arsha, "fetch_market", make_fake_market([]))
    import_account(client)
    client.post("/api/prices/refresh")

    containers = {c["name"]: c for c in client.get("/api/holdings").json()["containers"]}
    fragment = next(i for i in containers["Altinova"]["items"] if i["item_id"] == 44195)

    assert (fragment["unit_price"], fragment["value"]) == (2_000_000, 20_000_000)
    assert containers["Enhancement Inventory"]["items"][0]["value"] is None


def test_price_refresh_reports_arsha_outage(client, monkeypatch):
    def offline(item_ids, region="eu", lang="en"):
        raise OSError("timeout")

    monkeypatch.setattr(arsha, "fetch_market", offline)
    import_account(client)

    response = client.post("/api/prices/refresh")

    assert response.status_code == 502
    assert client.get("/api/account").json()["prices_fetched_at"] is None
