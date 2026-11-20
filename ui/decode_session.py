"""A decode running on a background thread, and the plumbing for taking its updates safely."""

import queue
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from PIL import Image

from live_decoding.events import LiveUpdate

Decoder = Callable[[threading.Event], Iterator[LiveUpdate]]  # makes updates until done or cancelled
_STREAM_END = object()  # put on the queue by the decoder thread when it has nothing more to say


@dataclass
class DrainedUpdates:
    """What was waiting on the update queue: only the newest of each kind of picture matters."""

    latest: LiveUpdate | None = None
    image: Image.Image | None = None
    signal: Image.Image | None = None
    packet_map: Image.Image | None = None
    failure: Exception | None = None
    ended: bool = False


class DecodeSession:
    """One decode in progress: a decoder running on its own thread, feeding updates to the window thread.

    tkinter widgets may only be touched from the window's own thread, so the decoder thread never draws
    anything. It puts updates on a queue, and the window takes them off with `drain`.
    """

    def __init__(self, decoder: Decoder) -> None:
        """Prepare a session for `decoder`; nothing runs until `start`."""
        self.decoder = decoder
        self.cancel = threading.Event()  # set to make the decoder stop at its next piece
        self.updates: queue.Queue = queue.Queue()  # LiveUpdate, Exception or _STREAM_END
        self.stream_ended = False  # the decoder thread has finished
        self.final: LiveUpdate | None = None  # the last update, once received
        self.revealing = False  # the finishing animation is playing

    def start(self) -> None:
        """Run the decoder on a background thread."""
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        """Feed the decoder's updates to the queue, then mark the end."""
        try:
            for update in self.decoder(self.cancel):
                self.updates.put(update)
        except Exception as error:  # passed to the window thread to show the user
            self.updates.put(error)
        self.updates.put(_STREAM_END)

    def drain(self) -> DrainedUpdates:
        """Take everything off the queue, keeping the newest image, signal and packet map."""
        drained = DrainedUpdates()
        while True:
            try:
                item = self.updates.get_nowait()
            except queue.Empty:
                break
            if item is _STREAM_END:
                drained.ended = True
            elif isinstance(item, Exception):
                drained.failure = item
            else:
                drained.latest = item
                drained.image = item.image if item.image is not None else drained.image
                drained.signal = item.signal if item.signal is not None else drained.signal
                drained.packet_map = item.packet_map if item.packet_map is not None else drained.packet_map
        self.stream_ended = self.stream_ended or drained.ended
        return drained
