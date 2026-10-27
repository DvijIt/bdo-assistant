"""Агент: пасивно слухає трафік гри через bdo-toolkit і пише персонажів, робітників і транспорт у базу.

bdo-toolkit імпортується лише під час старту, тож без нього (чи без Npcap) решта API працює,
а статус агента пояснює, чого бракує.
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


def default_session_factory():
    from bdo_toolkit import LiveCaptureOptions
    from bdo_toolkit.raw import LiveRawSession

    return LiveRawSession(live_options=LiveCaptureOptions(event_queue_size=EVENT_QUEUE_SIZE))


def default_decoder_factory():
    from bdo_toolkit.account import AccountDecoder

    return AccountDecoder()


class Agent:
    def __init__(
        self,
        connect: Callable[[], AbstractContextManager],
        session_factory: Callable = default_session_factory,
        decoder_factory: Callable = default_decoder_factory,
    ) -> None:
        self._connect = connect
        self._session_factory = session_factory
        self._decoder_factory = decoder_factory
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._state = "stopped"
        self._error: str | None = None
        self._started_at: float | None = None
        self._messages = 0
        self._records = 0
        self._last_record_at: float | None = None

    def status(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "error": self._error,
                "started_at": self._started_at,
                "messages": self._messages,
                "records": self._records,
                "last_record_at": self._last_record_at,
            }

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
        return {"state": self._state, "error": self._error, "started_at": self._started_at,
                "messages": self._messages, "records": self._records, "last_record_at": self._last_record_at}

    def _set(self, **fields) -> None:
        with self._lock:
            for key, value in fields.items():
                setattr(self, f"_{key}", value)

    def _run(self) -> None:
        try:
            session = self._session_factory()
            decoder = self._decoder_factory()
            session.start()
        except BaseException as error:  # немає bdo-toolkit, Npcap або прав на захоплення
            self._set(state="error", error=f"Не вдалося запустити захоплення: {error!r}")
            return

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
