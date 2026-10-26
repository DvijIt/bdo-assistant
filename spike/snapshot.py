import json
import sys
from datetime import datetime
from pathlib import Path

from bdo_toolkit.item_state import CharacterLoadSession, format_item_state

# Профіль і знімки лежать поруч зі скриптом (D:\Projects\bdo-spike).
HERE = Path(__file__).resolve().parent
PROFILE = HERE / "opcodes.local"
OUT = HERE / "snapshots"


def main() -> None:
    if not PROFILE.is_file():
        sys.exit(f"Немає профілю {PROFILE}: спершу виконай bdo-toolkit profile fetch")
    OUT.mkdir(exist_ok=True)

    with CharacterLoadSession(opcode_profile=PROFILE) as session:
        input(
            "Захоплення запущено. Зайди персонажем у світ, дочекайся, "
            "поки все завантажиться, і натисни Enter...\n"
        )
        snapshot = session.stop()

    print(format_item_state(snapshot))
    path = OUT / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nЗбережено: {path}")


if __name__ == "__main__":
    main()
