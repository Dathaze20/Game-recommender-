"""Background work helpers.

Kivy's widget tree is not thread-safe, so every network call runs on a worker
thread and every resulting UI mutation is marshalled back through
:class:`~kivy.clock.Clock`.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from kivy.clock import Clock

log = logging.getLogger(__name__)


def run_async(
    work: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[BaseException], None] | None = None,
    name: str = "gamerec-worker",
) -> threading.Thread:
    """Run ``work`` off the UI thread and deliver the outcome back on it.

    ``on_success`` / ``on_error`` are always invoked on the main thread, so
    they may touch widgets freely.
    """

    def _worker() -> None:
        try:
            result = work()
        except BaseException as exc:  # noqa: BLE001 - reported, never swallowed
            # Bind the exception as a default argument: Python clears the name
            # bound by `except ... as` when the block exits, so a plain closure
            # over `exc` would raise NameError by the time the Clock fires.
            log.debug("Background task failed", exc_info=True)
            if on_error is not None:
                Clock.schedule_once(lambda _dt, e=exc: on_error(e), 0)
        else:
            Clock.schedule_once(lambda _dt, r=result: on_success(r), 0)

    thread = threading.Thread(target=_worker, name=name, daemon=True)
    thread.start()
    return thread


def guarded(generation, token: int, callback: Callable[..., None]) -> Callable[..., None]:
    """Wrap ``callback`` so it only runs while ``token`` is still current.

    This is what keeps a slow response for an abandoned search — or for a
    screen the user has already navigated away from — from overwriting what is
    now on screen.
    """

    def _wrapped(*args, **kwargs) -> None:
        if generation.is_current(token):
            callback(*args, **kwargs)

    return _wrapped
