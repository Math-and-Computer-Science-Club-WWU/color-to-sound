"""Slowing a stream of items down to a chosen speed."""

import time
from collections.abc import Iterable, Iterator
from threading import Event


def paced[T](items: Iterable[T], seconds_per_item: float, cancel: Event | None = None) -> Iterator[T]:
    """Yield items no faster than one per `seconds_per_item` (0 means as fast as possible).

    Stops early if the `cancel` event is set.
    """
    start = time.perf_counter()
    for number, item in enumerate(items):
        if cancel is not None and cancel.is_set():
            return
        wait = start + number * seconds_per_item - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
        yield item
