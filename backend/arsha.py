"""Клієнт неофіційного API arsha.io: назви й грейди предметів."""

import json
import urllib.error
import urllib.parse
import urllib.request


API_URL = "https://api.arsha.io"
BATCH_SIZE = 100
TIMEOUT_SECONDS = 15


def _get_batched(path: str, item_ids: list[int], lang: str) -> list[dict]:
    entries: list[dict] = []
    for start in range(0, len(item_ids), BATCH_SIZE):
        batch = item_ids[start:start + BATCH_SIZE]
        query = urllib.parse.urlencode([("id", item_id) for item_id in batch] + [("lang", lang)])
        request = urllib.request.Request(
            f"{API_URL}{path}?{query}",
            headers={"User-Agent": "bdo-assistant"},
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.load(response)
        # На один id API відповідає об'єктом, на кілька — списком, а предмети
        # з кількома рівнями заточки на ринку приходять вкладеним списком.
        for entry in data if isinstance(data, list) else [data]:
            entries.extend(entry if isinstance(entry, list) else [entry])
    return [entry for entry in entries if isinstance(entry, dict)]


def fetch_items(item_ids: list[int], lang: str = "en") -> list[dict]:
    """Повертає [{"id", "name", "grade"}] для відомих arsha.io предметів."""
    return [item for item in _get_batched("/util/db", item_ids, lang) if item.get("name")]


def fetch_market(item_ids: list[int], region: str = "eu", lang: str = "en") -> list[dict]:
    """Ринкові записи Central Market: по одному на діапазон заточки (sid).

    Кожен запис має id, minEnhance, maxEnhance, basePrice, lastSoldPrice,
    currentStock. Предмет поза ринком або не повертається, або приходить
    з basePrice 0.
    """
    path = f"/v2/{region}/GetWorldMarketSubList"

    def fetch(batch: list[int]) -> list[dict]:
        try:
            return _get_batched(path, batch, lang)
        except urllib.error.HTTPError as error:
            # Предмет, якого ринок не знає, валить увесь запит з 500,
            # тож ділимо пакет навпіл, доки не відсіємо такі ID.
            if error.code < 500 or len(batch) == 1:
                if len(batch) == 1:
                    return []
                raise
            middle = len(batch) // 2
            return fetch(batch[:middle]) + fetch(batch[middle:])

    entries: list[dict] = []
    for start in range(0, len(item_ids), BATCH_SIZE):
        entries.extend(fetch(item_ids[start:start + BATCH_SIZE]))
    return [entry for entry in entries if "id" in entry and "basePrice" in entry]
