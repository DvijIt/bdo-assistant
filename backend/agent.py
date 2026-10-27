"""Агент: пасивно слухає трафік гри через bdo-toolkit і пише в базу персонажів, робітників, транспорт,
знання, а також знімки інвентаря й складів.

bdo-toolkit імпортується лише під час старту, тож без нього (чи без Npcap) решта API працює,
а статус агента пояснює, чого бракує. Інвентар потребує профілю опкодів; без нього агент
знімає все інше.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
import threading
import time

import account


FLUSH_SECONDS = 1.0
POLL_SECONDS = 0.2
# Вхід у світ — тисячі повідомлень за секунду; черга має їх витримати.
EVENT_QUEUE_SIZE = 200_000
# Скільки чекати після даних персонажа, поки дійдуть інвентар і склади.
INVENTORY_SETTLE_SECONDS = 15.0


def default_session_factory():
    from bdo_toolkit import LiveCaptureOptions
    from bdo_toolkit.raw import LiveRawSession

    return LiveRawSession(live_options=LiveCaptureOptions(event_queue_size=EVENT_QUEUE_SIZE))


def default_decoder_factory():
    from bdo_toolkit.account import AccountDecoder

    return AccountDecoder()


def default_inventory_session_factory(profile):
    from bdo_toolkit.item_state import CharacterLoadSession

    return CharacterLoadSession(opcode_profile=profile)


class InventoryCapture:
    """Одна сесія bdo-toolkit на кожен вхід у світ: знімок з кількома входами
    виходить порожнім, бо бібліотека не розрізняє їх між собою."""

    def __init__(self, factory: Callable, profile, import_snapshot: Callable[[dict, str], dict],
                 settle_seconds: float) -> None:
        self._factory = factory
        self._profile = profile
        self._import = import_snapshot
        self._settle = settle_seconds
        self._session = None
        self._login: tuple[str, float] | None = None
        self.snapshots = 0
        self.last: dict | None = None
        self.error: str | None = None

    def start(self) -> None:
        try:
            self._session = self._factory(self._profile)
            self._session.start()
        except BaseException as error:  # профіль не підходить до патча, Npcap тощо
            self._session = None
            self.error = f"Знімок інвентаря недоступний: {error!r}"

    def login(self, nick: str) -> None:
        if self._login is not None:  # новий вхід раніше, ніж попередній встиг осісти
            self._finish()
            self.start()
        self._login = (nick, time.monotonic() + self._settle)

    def tick(self) -> None:
        if self._login is not None and time.monotonic() >= self._login[1]:
            self._finish()
            self.start()

    def close(self) -> None:
        if self._login is not None:
            self._finish()
        elif self._session is not None:
            try:
                self._session.stop()
            except BaseException:
                pass
        self._session = None

    def _finish(self) -> None:
        nick, _ = self._login
        self._login = None
        session, self._session = self._session, None
        if session is None:
            return
        try:
            data = session.stop().to_dict()
        except BaseException as error:
            self.error = f"Знімок інвентаря для {nick} не вдався: {error!r}"
            return
        if not data.get("hydration_detected"):
            self.error = f"Вхід {nick}: інвентар не прийшов у трафіку (можливо, застарів профіль опкодів)"
            return
        try:
            summary = self._import(data, nick)
        except Exception as error:  # дублікат або неочікувана структура знімка
            self.error = f"Знімок {nick} не імпортовано: {error}"
            return
        self.snapshots += 1
        self.error = None
        self.last = {"character": nick, "at": time.time(), **summary}


class Agent:
    def __init__(
        self,
        connect: Callable[[], AbstractContextManager],
        session_factory: Callable = default_session_factory,
        decoder_factory: Callable = default_decoder_factory,
        *,
        inventory_profile: Callable[[], object] = lambda: None,
        import_snapshot: Callable[[dict, str], dict] | None = None,
        inventory_session_factory: Callable = default_inventory_session_factory,
        inventory_settle_seconds: float = INVENTORY_SETTLE_SECONDS,
    ) -> None:
        self._connect = connect
        self._session_factory = session_factory
        self._decoder_factory = decoder_factory
        self._inventory_profile = inventory_profile
        self._import_snapshot = import_snapshot
        self._inventory_session_factory = inventory_session_factory
        self._inventory_settle = inventory_settle_seconds
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._state = "stopped"
        self._error: str | None = None
        self._started_at: float | None = None
        self._messages = 0
        self._records = 0
        self._last_record_at: float | None = None
        self._inventory: InventoryCapture | None = None
        self._inventory_note: str | None = None

    def status(self) -> dict:
        with self._lock:
            return self._status_unlocked()

    def start(self) -> dict:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self._status_unlocked()
            self._stop.clear()
            self._state, self._error = "starting", None
            self._started_at, self._messages, self._records, self._last_record_at = time.time(), 0, 0, None
            self._thread = threading.Thread(target=self._run, name="bdo-agent", daemon=True)
            self._thread.start()
        return self.status()

    def stop(self, timeout: float = 10.0) -> dict:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return self.status()

    def _status_unlocked(self) -> dict:
        inventory = self._inventory
        return {
            "state": self._state,
            "error": self._error,
            "started_at": self._started_at,
            "messages": self._messages,
            "records": self._records,
            "last_record_at": self._last_record_at,
            "inventory": {
                "enabled": inventory is not None,
                "note": self._inventory_note or (inventory.error if inventory else None),
                "snapshots": inventory.snapshots if inventory else 0,
                "last": inventory.last if inventory else None,
            },
        }

    def _set(self, **fields) -> None:
        with self._lock:
            for key, value in fields.items():
                setattr(self, f"_{key}", value)

    def _start_inventory(self) -> InventoryCapture | None:
        profile = self._inventory_profile()
        if profile is None or self._import_snapshot is None:
            self._set(inventory=None, inventory_note="Інвентар не знімається: немає профілю опкодів (opcodes.local)")
            return None
        inventory = InventoryCapture(self._inventory_session_factory, profile, self._import_snapshot,
                                     self._inventory_settle)
        inventory.start()
        self._set(inventory=inventory, inventory_note=None)
        return inventory

    def _run(self) -> None:
        try:
            session = self._session_factory()
            decoder = self._decoder_factory()
            session.start()
        except BaseException as error:  # немає bdo-toolkit, Npcap або прав на захоплення
            self._set(state="error", error=f"Не вдалося запустити захоплення: {error!r}")
            return

        inventory = self._start_inventory()
        self._set(state="running")
        writer = account.AccountWriter()
        pending: list = []
        last_flush = time.monotonic()
        try:
            while not self._stop.is_set() and not session.stopped:
                message = session.poll(timeout=POLL_SECONDS)
                if message is not None:
                    records = decoder.feed(message)
                    pending.extend(records)
                    with self._lock:
                        self._messages += 1
                    if inventory is not None:
                        for record in records:
                            if record.record_type == "character_info":
                                inventory.login(record.nick)
                if inventory is not None:
                    # Зупинка сесії знімка триває секунди; статус читає лічильники без блокування.
                    inventory.tick()
                if pending and time.monotonic() - last_flush >= FLUSH_SECONDS:
                    self._flush(writer, pending)
                    last_flush = time.monotonic()
        except BaseException as error:  # втрата пакетів чи інша помилка захоплення
            self._set(error=f"Захоплення зупинилось: {error!r}")
        finally:
            try:
                session.stop()
            except BaseException as error:
                with self._lock:
                    self._error = self._error or f"Помилка зупинки захоплення: {error!r}"
            if pending:
                self._flush(writer, pending)
            if inventory is not None:
                inventory.close()
            with self._lock:
                self._state = "error" if self._error else "stopped"

    def _flush(self, writer: account.AccountWriter, pending: list) -> None:
        with self._connect() as connection:
            saved = writer.save(connection, pending)
        with self._lock:
            self._records += saved
            if saved:
                self._last_record_at = time.time()
        pending.clear()
