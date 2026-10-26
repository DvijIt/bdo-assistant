"""Клієнт неофіційного API arsha.io: назви й грейди предметів."""

import json
import urllib.parse
import urllib.request


API_URL = "https://api.arsha.io"
BATCH_SIZE = 100
TIMEOUT_SECONDS = 15


def fetch_items(item_ids: list[int], lang: str = "en") -> list[dict]:
    """Повертає [{"id", "name", "grade"}] для відомих arsha.io предметів."""
    items: list[dict] = []
    for start in range(0, len(item_ids), BATCH_SIZE):
        batch = item_ids[start:start + BATCH_SIZE]
        query = urllib.parse.urlencode([("id", item_id) for item_id in batch] + [("lang", lang)])
        request = urllib.request.Request(
            f"{API_URL}/util/db?{query}",
            headers={"User-Agent": "bdo-assistant"},
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.load(response)
        # На один id API відповідає об'єктом, на кілька — списком.
        items.extend(data if isinstance(data, list) else [data])
    return [item for item in items if isinstance(item, dict) and item.get("name")]
