"""The main window: choose an image, press Go, and watch it become sound and then a picture again."""

import importlib.util
import threading
import time
import tkinter as tk
from collections.abc import Callable
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from air_channel.sender import AirTransmission, send_over_air
from cable_channel.file_mode import send_file
from cable_channel.pixel_mode import send_pixels
from common.modes import Channel, Mode
from common.paths import IMAGE_DIR, OUTPUT_DIR, output_path
from common.wav_files import wav_info
from live_decoding.air import decode_air_file_live, decode_air_microphone_live
from live_decoding.cable import decode_file_live, decode_pixels_live
from live_decoding.events import SIGNAL_SIZE, SIGNAL_VIEWS, LiveUpdate, signal_at
from ui.decode_session import Decoder, DecodeSession, DrainedUpdates
from ui.previews import fit_preview, reveal_frames
from ui.stage_tracker import GREY, StageTracker
from ui.text import (
    ORIGINAL_CAPTION,
    RECONSTRUCTION_CAPTIONS,
    SIGNAL_CAPTION,
    STAGE_ALL_DONE,
    STAGE_LISTEN,
    STAGE_MAKE_SOUND,
    STAGE_NONE,
    STAGE_PREPARE,
    STAGE_REBUILD,
    format_duration,
)

try:
    import winsound  # Windows only; without it Play and the speaker-to-microphone Go are unavailable
except ImportError:
    winsound = None

CHANNEL_LABELS = {
    Channel.CABLE: "Cable / file (fast, clean audio only)",
    Channel.AIR: "Speaker \u2192 microphone (slow, robust)",
}
MODE_LABELS = {
    Mode.FILE: "Full quality (send the image file)",
    Mode.PIXELS: "Pixel mode (raw RGB, blurry)",
}
RESULT_LABELS = {Mode.FILE: "Exact copy", Mode.PIXELS: "Pixel preview"}
WAV_NAMES = {
    (Channel.CABLE, Mode.FILE): "image.wav",
    (Channel.CABLE, Mode.PIXELS): "out.wav",
    (Channel.AIR, Mode.FILE): "air_full.wav",
    (Channel.AIR, Mode.PIXELS): "air_pixels.wav",
}
# how fast the decoder is allowed to listen, as a multiple of the audio's real duration (0 = no limit)
SPEEDS = {"Real time (plays the sound)": 1, "10x": 10, "50x": 50, "Max": 0}
REPEAT_CHOICES = {"Send once": 1, "Send twice (safer)": 2, "Send 3 times": 3}
DEFAULT_PIXEL_SIDE = {Channel.CABLE: 64, Channel.AIR: 32}  # sound over the air is slow, so start smaller
MIN_PIXEL_SIDE, MAX_PIXEL_SIDE = 8, 128

WATCH_SECONDS = 20  # Go decodes fast enough to take about this long, unless "play the sound" is ticked
AIR_TIMEOUT_MARGIN = 6  # seconds of waiting after the audio ends, in case the last packets are late
PANEL_SIZE = (340, 250)  # size of the original and reconstruction previews
MAP_SIZE = (340, 56)  # size of the packet map
REFRESH_MS = 33  # window refresh interval while decoding (about 30 pictures a second)
SOUND_STAGE_DELAY_MS = 1200  # how long "prepare" shows before it becomes "turn it into sound"
PLAYBACK_REFRESH_MS = 100  # how often the spectrogram scrolls while playing


def microphone_available() -> bool:
    """Return True if the sounddevice package is installed."""
    return importlib.util.find_spec("sounddevice") is not None


class MainWindow(tk.Tk):
    """The application window."""

    def __init__(self) -> None:
        """Build the window, with Advanced controls hidden."""
        super().__init__()
        self.title("Color to Sound")

        # what the user has chosen
        self.image_path: Path | None = None
        self.original_rgb: Image.Image | None = None
        self.wav_path: Path | None = None
        self.wav_channel = Channel.CABLE
        self.wav_seconds = 0.0

        # what is happening now
        self.making_audio = False
        self.session: DecodeSession | None = None
        self.current_received: Image.Image | None = None  # what the Reconstruction panel shows, for the final fade
        self.playback_started: float | None = None  # when Play was pressed, while it is playing

        # widget variables
        self.status = tk.StringVar(value="Choose an image, then press Go.")
        self.channel_var = tk.StringVar(value=Channel.CABLE.value)
        self.mode_var = tk.StringVar(value=Mode.FILE.value)
        self.pixel_side = tk.StringVar(value=str(DEFAULT_PIXEL_SIDE[Channel.CABLE]))
        self.speed = tk.StringVar(value="10x")
        self.repeats = tk.StringVar(value="Send once")
        self.realtime = tk.BooleanVar(value=False)
        self.advanced = tk.BooleanVar(value=False)
        self.buttons: dict[str, ttk.Button] = {}
        self.choice_widgets: list[ttk.Radiobutton | ttk.Checkbutton] = []  # disabled while busy

        self._build_simple_bar()
        self._build_advanced_bar()
        self.stage_tracker = StageTracker(self, wraplength=3 * PANEL_SIZE[0])
        self.stage_tracker.pack(fill="x")
        self._build_panels()
        self.progress = ttk.Progressbar(self, maximum=1.0)
        self.progress.pack(fill="x", padx=14)
        ttk.Label(self, textvariable=self.status, padding=8, wraplength=3 * PANEL_SIZE[0]).pack(fill="x")

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.update_controls()

    # ---- the choices the user has made ---------------------------------------------------------

    @property
    def channel(self) -> Channel:
        """The selected channel."""
        return Channel(self.channel_var.get())

    @property
    def mode(self) -> Mode:
        """The selected mode."""
        return Mode(self.mode_var.get())

    @property
    def busy(self) -> bool:
        """True while audio is being made or a decode is running."""
        return self.making_audio or self.session is not None

    # ---- building the window -------------------------------------------------------------------

    def _add_button(self, parent: ttk.Frame, key: str, text: str, command: Callable[[], None],
                    padx: int | tuple[int, int] = 3) -> None:
        """Add a button and remember it under `key`."""
        button = ttk.Button(parent, text=text, command=command)
        button.pack(side="left", padx=padx)
        self.buttons[key] = button

    def _add_radio(self, parent: ttk.Frame, label: str, value: str, variable: tk.StringVar,
                   command: Callable[[], None]) -> None:
        """Add a radio button that is disabled while busy."""
        radio = ttk.Radiobutton(parent, text=label, value=value, variable=variable, command=command)
        radio.pack(side="left", padx=6)
        self.choice_widgets.append(radio)

    def _build_simple_bar(self) -> None:
        """Build the normal controls: choose, result, Go and a few options."""
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        self._add_button(bar, "choose_simple", "Choose image...", self.choose_image)
        self._add_button(bar, "go", "\u25B6  Go", self.go, padx=(8, 12))
        ttk.Label(bar, text="Result:").pack(side="left")
        for mode, label in RESULT_LABELS.items():
            self._add_radio(bar, label, mode.value, self.mode_var, self.on_mode_changed)
        over_air = ttk.Checkbutton(bar, text="Send through the air (speaker \u2192 mic)", variable=self.channel_var,
                                   onvalue=Channel.AIR.value, offvalue=Channel.CABLE.value,
                                   command=self.on_channel_changed)
        over_air.pack(side="left", padx=(12, 4))
        real_time = ttk.Checkbutton(bar, text="Play the sound while decoding", variable=self.realtime)
        real_time.pack(side="left", padx=4)
        self.choice_widgets += [over_air, real_time]
        ttk.Checkbutton(bar, text="Advanced", variable=self.advanced, command=self.toggle_advanced).pack(side="right")
        self.simple_bar = bar

    def _build_advanced_bar(self) -> None:
        """Build the advanced controls (every setting and step as its own control), hidden until asked for."""
        self.advanced_frame = ttk.LabelFrame(self, text="Advanced: run each step yourself", padding=6)
        top = ttk.Frame(self.advanced_frame)
        top.pack(fill="x")
        ttk.Label(top, text="Channel:").pack(side="left")
        for channel, label in CHANNEL_LABELS.items():
            self._add_radio(top, label, channel.value, self.channel_var, self.on_channel_changed)
        ttk.Label(top, text="    Mode:").pack(side="left")
        for mode, label in MODE_LABELS.items():
            self._add_radio(top, label, mode.value, self.mode_var, self.on_mode_changed)

        options = ttk.Frame(self.advanced_frame)
        options.pack(fill="x", pady=4)
        ttk.Label(options, text="Pixel size:").pack(side="left")
        self.size_box = ttk.Spinbox(options, from_=MIN_PIXEL_SIDE, to=MAX_PIXEL_SIDE, increment=8, width=5,
                                    textvariable=self.pixel_side)
        self.size_box.pack(side="left", padx=(2, 12))
        ttk.Label(options, text="Repeats:").pack(side="left")
        self.repeat_box = ttk.Combobox(options, textvariable=self.repeats, values=list(REPEAT_CHOICES),
                                       state="readonly", width=18)
        self.repeat_box.pack(side="left", padx=(2, 12))
        ttk.Label(options, text="Decode speed:").pack(side="left")
        self.speed_box = ttk.Combobox(options, textvariable=self.speed, values=list(SPEEDS), state="readonly", width=24)
        self.speed_box.pack(side="left", padx=2)

        steps = ttk.Frame(self.advanced_frame)
        steps.pack(fill="x")
        for key, text, command in (
            ("choose", "1. Choose image...", self.choose_image),
            ("send", "2. Make audio", self.make_audio),
            ("play", "Play", self.play),
            ("stop", "Stop", self.stop),
            ("load", "Load WAV...", self.choose_wav),
            ("receive", "3. Decode audio", self.decode),
            ("listen", "Listen (mic)", self.listen),
        ):
            self._add_button(steps, key, text, command)

    def _build_panels(self) -> None:
        """Build the three panels (original, signal, reconstruction) with a caption under each."""
        panels = ttk.Frame(self, padding=(8, 0))
        panels.pack()
        self.original_label = self._add_panel(panels, "Original", 0, ORIGINAL_CAPTION)

        signal_frame = ttk.LabelFrame(panels, text="Signal: the sound", width=PANEL_SIZE[0], height=PANEL_SIZE[1])
        signal_frame.grid(row=0, column=1, padx=6)
        signal_frame.pack_propagate(False)
        self.signal_label = ttk.Label(signal_frame, text="(no audio yet)", anchor="center")
        self.signal_label.pack(pady=(4, 0))
        ttk.Label(signal_frame, text="Packets (green = received)").pack(pady=(6, 0))
        self.map_label = ttk.Label(signal_frame, text="(air channel only)", anchor="center")
        self.map_label.pack()
        self._add_caption(panels, SIGNAL_CAPTION, 1)

        self.received_label = self._add_panel(panels, "Reconstruction (live)", 2, "")
        self.received_caption = self._add_caption(panels, "", 2)
        self.update_captions()

    def _add_panel(self, parent: ttk.Frame, title: str, column: int, caption: str) -> ttk.Label:
        """Add a framed panel with a label to hold a picture. Returns that label."""
        frame = ttk.LabelFrame(parent, text=title, width=PANEL_SIZE[0], height=PANEL_SIZE[1])
        frame.grid(row=0, column=column, padx=6)
        frame.pack_propagate(False)
        label = ttk.Label(frame, text="(nothing yet)", anchor="center")
        label.pack(expand=True)
        if caption:
            self._add_caption(parent, caption, column)
        return label

    @staticmethod
    def _add_caption(parent: ttk.Frame, text: str, column: int) -> ttk.Label:
        """Add small grey explanatory text under a panel."""
        caption = ttk.Label(parent, text=text, wraplength=PANEL_SIZE[0], foreground=GREY)
        caption.grid(row=1, column=column, padx=6, sticky="n")
        return caption

    def toggle_advanced(self) -> None:
        """Show or hide the advanced controls."""
        if self.advanced.get():
            self.advanced_frame.pack(fill="x", padx=8, pady=(0, 4), after=self.simple_bar)
        else:
            self.advanced_frame.pack_forget()

    # ---- keeping the controls in step with the state ---------------------------------------------

    def update_controls(self) -> None:
        """Enable and disable controls to match what is possible right now."""
        def state(enabled: bool) -> str:
            return "normal" if enabled and not self.busy else "disabled"

        over_air = self.channel is Channel.AIR
        self.buttons["choose_simple"].configure(state=state(True))
        self.buttons["go"].configure(state=state(True))
        self.buttons["choose"].configure(state=state(True))
        self.buttons["send"].configure(state=state(self.image_path is not None))
        self.buttons["play"].configure(state=state(self.wav_path is not None and winsound is not None))
        self.buttons["stop"].configure(state="normal" if (winsound or self.busy) else "disabled")
        self.buttons["load"].configure(state=state(True))
        self.buttons["receive"].configure(state=state(self.wav_path is not None))
        self.buttons["listen"].configure(state=state(over_air))
        for widget in self.choice_widgets:
            widget.configure(state="disabled" if self.busy else "normal")
        self.size_box.configure(state="normal" if not self.busy and self.mode is Mode.PIXELS else "disabled")
        self.repeat_box.configure(state="readonly" if not self.busy and over_air else "disabled")
        self.speed_box.configure(state="disabled" if self.busy else "readonly")

    def update_captions(self) -> None:
        """Explain the reconstruction panel in terms of the selected mode."""
        self.received_caption.configure(text=RECONSTRUCTION_CAPTIONS[self.mode])

    def on_channel_changed(self) -> None:
        """React to the channel being switched."""
        self.pixel_side.set(str(DEFAULT_PIXEL_SIDE[self.channel]))
        self.update_controls()
        note = " Go will play the sound and listen with the microphone." if self.channel is Channel.AIR else ""
        self.status.set(f"{CHANNEL_LABELS[self.channel]}.{note}")

    def on_mode_changed(self) -> None:
        """React to the mode being switched."""
        self.update_controls()
        self.update_captions()
        self.status.set(f"{MODE_LABELS[self.mode]}.")

    def show_stage(self, stage: int) -> None:
        """Move the step tracker on."""
        self.stage_tracker.show(stage, self.channel, self.mode)

    def pixel_side_value(self) -> int:
        """Return the pixel size typed in, kept within limits (a bad entry falls back to the default)."""
        try:
            return min(MAX_PIXEL_SIDE, max(MIN_PIXEL_SIDE, int(self.pixel_side.get())))
        except ValueError:
            return DEFAULT_PIXEL_SIDE[self.channel]

    @staticmethod
    def show_picture(label: ttk.Label, image: Image.Image, fit: tuple[int, int] = PANEL_SIZE,
                     blocky: bool = False) -> Image.Image:
        """Display a picture in a label, scaled to fit. Returns the picture as shown."""
        preview = fit_preview(image, fit, blocky)
        photo = ImageTk.PhotoImage(preview)
        label.configure(image=photo, text="")
        label.image = photo  # keep a reference, or tkinter drops the picture
        return preview

    @staticmethod
    def clear_picture(label: ttk.Label, text: str) -> None:
        """Replace a label's picture with a short message."""
        label.configure(image="", text=text)
        label.image = None

    # ---- doing work without freezing the window ----------------------------------------------------

    def run_in_thread(self, work: Callable[[], object], done: Callable[[object], None], message: str) -> None:
        """Run `work()` on a thread so the window stays responsive, then call `done(result)` here."""
        self.making_audio = True
        self.status.set(message)
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.update_controls()
        outcome: dict[str, object] = {}

        def target() -> None:
            try:
                outcome["result"] = work()
            except Exception as error:  # reported to the user below, not lost
                outcome["error"] = error

        thread = threading.Thread(target=target, daemon=True)
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                self.after(100, poll)
                return
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
            self.making_audio = False
            self.update_controls()
            if "error" in outcome:
                self.report_failure(outcome["error"])
            else:
                done(outcome["result"])

        poll()

    def report_failure(self, error: object) -> None:
        """Tell the user something went wrong."""
        self.show_stage(STAGE_NONE)
        self.status.set(f"Failed: {error}")
        messagebox.showerror("Color to Sound", str(error))

    # ---- choosing and making audio -----------------------------------------------------------------

    def choose_image(self) -> None:
        """Let the user pick an image file."""
        path = filedialog.askopenfilename(
            initialdir=IMAGE_DIR,
            filetypes=[("Images", "*.webp *.png *.jpg *.jpeg *.gif *.bmp"), ("All files", "*.*")],
        )
        if path:
            self.load_image(Path(path))

    def load_image(self, path: Path) -> None:
        """Show the chosen image in the Original panel."""
        with Image.open(path) as image:
            self.original_rgb = image.convert("RGB")
        self.image_path = path
        self.show_picture(self.original_label, self.original_rgb)
        self.status.set(f"Loaded {path.name} ({path.stat().st_size} bytes). Press Go.")
        self.update_controls()

    def audio_job(self, wav_path: Path) -> tuple[Callable[[], object], Callable[[object], str]]:
        """Return (work, describe) for making audio with the selected channel and mode.

        `work()` makes the audio; `describe(result)` turns what it returns into a sentence.
        """
        image_path = self.image_path
        if self.channel is Channel.AIR:
            side, repeats = self.pixel_side_value(), REPEAT_CHOICES[self.repeats.get()]
            work = partial(send_over_air, image_path, wav_path, self.mode, side, repeats)

            def describe(result: AirTransmission) -> str:
                return (f"Made {wav_path.name}: {result.payload_bytes} bytes in {result.packets} packets, "
                        f"sent {repeats}x")
        elif self.mode is Mode.FILE:
            work = partial(send_file, image_path, wav_path)

            def describe(result: int) -> str:
                return f"Made {wav_path.name} from {result} bytes"
        else:
            side = self.pixel_side_value()
            work = partial(send_pixels, image_path, wav_path, (side, side))

            def describe(result: int) -> str:
                return f"Made {wav_path.name} from {result} pixels"
        return work, describe

    def make_audio(self, then: Callable[[], None] | None = None) -> None:
        """Turn the chosen image into a wav, then call `then()` if given."""
        channel = self.channel
        wav_path = output_path(WAV_NAMES[channel, self.mode])
        work, describe = self.audio_job(wav_path)

        def done(result: object) -> None:
            self.show_stage(STAGE_LISTEN)
            self.load_wav(wav_path, describe(result), channel)
            if then and self.wav_path:
                then()

        self.show_stage(STAGE_PREPARE)
        # the explanation changes once the data is ready and the sound is being written
        self.after(SOUND_STAGE_DELAY_MS, lambda: self.making_audio and self.show_stage(STAGE_MAKE_SOUND))
        self.run_in_thread(work, done, "Preparing the image and making the sound...")

    def choose_wav(self) -> None:
        """Let the user load an existing wav."""
        path = filedialog.askopenfilename(initialdir=OUTPUT_DIR, filetypes=[("WAV audio", "*.wav")])
        if path:
            self.load_wav(Path(path), f"Loaded {Path(path).name}", self.channel)

    def load_wav(self, path: Path, message: str, channel: Channel) -> None:
        """Remember a wav, and show what its beginning looks like."""
        self.wav_path, self.wav_channel = path, channel
        try:
            _, self.wav_seconds = wav_info(path)
            first_moments = SIGNAL_VIEWS[channel].seconds
            self.show_picture(self.signal_label, signal_at(path, first_moments, channel), SIGNAL_SIZE)
        except (OSError, ValueError) as error:
            self.status.set(f"Could not read that audio: {error}")
            self.wav_path = None
        else:
            self.status.set(f"{message}: {format_duration(self.wav_seconds)} of audio.")
        self.update_controls()

    # ---- playing -------------------------------------------------------------------------------------

    def play(self) -> None:
        """Play the wav and scroll the spectrogram along with it."""
        winsound.PlaySound(str(self.wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        self.playback_started = time.perf_counter()
        self.animate_playback()

    def animate_playback(self) -> None:
        """Redraw the spectrogram for the part of the sound that is playing now."""
        if self.playback_started is None or self.session is not None:
            return
        elapsed = time.perf_counter() - self.playback_started
        if elapsed > self.wav_seconds:
            self.playback_started = None
            return
        self.show_picture(self.signal_label, signal_at(self.wav_path, elapsed, self.wav_channel), SIGNAL_SIZE)
        self.after(PLAYBACK_REFRESH_MS, self.animate_playback)

    def stop(self) -> None:
        """Stop playing and cancel any decode in progress."""
        if self.session is not None:
            self.session.cancel.set()  # the decoder notices at its next piece
        self.playback_started = None
        if winsound:
            winsound.PlaySound(None, winsound.SND_PURGE)

    # ---- decoding ------------------------------------------------------------------------------------

    def file_decoder(self, speed: float) -> Decoder:
        """Return a decoder for the loaded wav, using the selected channel and mode."""
        if self.channel is Channel.AIR:
            return partial(decode_air_file_live, self.wav_path, speed)
        if self.mode is Mode.FILE:
            return partial(decode_file_live, self.wav_path, speed)
        return partial(decode_pixels_live, self.wav_path, speed)

    def decode(self) -> None:
        """Decode the loaded wav at the speed chosen in Advanced."""
        speed = SPEEDS[self.speed.get()]
        self.start_decode(self.file_decoder(speed), "Listening...", play_sound=speed == 1)

    def listen(self) -> None:
        """Decode live from the microphone."""
        if not self.microphone_ready():
            return
        self.start_decode(decode_air_microphone_live,
                          "Listening on the microphone... play the audio near it. Press Stop to finish.")

    def microphone_ready(self) -> bool:
        """Check the microphone package is installed, telling the user if not."""
        if microphone_available():
            return True
        messagebox.showerror("Color to Sound",
                             "Microphone support needs the sounddevice package:\n\npip install sounddevice")
        return False

    def go(self) -> None:
        """Do the whole journey in one click: make the sound, then listen to it and rebuild the picture."""
        if self.image_path is None:
            self.choose_image()
            if self.image_path is None:
                return
        self.make_audio(then=self.go_listen)

    def go_listen(self) -> None:
        """Do the second half of Go: decode what was just made (through the air if that was chosen)."""
        if self.channel is Channel.AIR and winsound and self.microphone_ready():
            message = ("Playing the sound through your speaker and listening with the microphone. "
                       "Keep the volume up and the mic close.")
            self.start_decode(decode_air_microphone_live, message, play_sound=True,
                              timeout=self.wav_seconds + AIR_TIMEOUT_MARGIN)
            return
        real_time = self.realtime.get()
        speed = 1 if real_time else max(1.0, self.wav_seconds / WATCH_SECONDS)
        self.start_decode(self.file_decoder(speed), "Listening...", play_sound=real_time)

    def start_decode(self, decoder: Decoder, message: str, play_sound: bool = False,
                     timeout: float | None = None) -> None:
        """Start decoding on a background thread and begin showing its updates."""
        session = DecodeSession(decoder)
        self.session = session
        self.playback_started = None
        self.current_received = None
        self.progress.configure(mode="determinate", value=0)
        self.status.set(message)
        self.show_stage(STAGE_LISTEN)
        self.clear_picture(self.received_label, "(waiting for data...)")
        waiting = "(waiting for packets...)" if self.channel is Channel.AIR else "(only used over the air)"
        self.clear_picture(self.map_label, waiting)
        self.update_controls()
        if play_sound and winsound and self.wav_path:
            # hear the audio while it is being decoded
            winsound.PlaySound(str(self.wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        if timeout:
            self.after(int(timeout * 1000), lambda: session.cancel.set() if self.session is session else None)

        session.start()
        self.pump(session)

    def pump(self, session: DecodeSession) -> None:
        """Show whatever the decoder has produced so far. Runs about 30 times a second while decoding."""
        drained = session.drain()
        if drained.latest is not None:
            self.show_update(session, drained)
        if drained.failure is not None:
            self.finish(session, drained.failure)
        elif session.stream_ended and not session.revealing:
            self.finish(session, None)
        else:
            self.after(REFRESH_MS, self.pump, session)

    def show_update(self, session: DecodeSession, drained: DrainedUpdates) -> None:
        """Put the newest pictures and text on screen."""
        latest = drained.latest
        self.progress["value"] = latest.progress
        if drained.signal is not None:
            self.show_picture(self.signal_label, drained.signal, SIGNAL_SIZE)
        if drained.packet_map is not None:
            self.show_picture(self.map_label, drained.packet_map, MAP_SIZE, blocky=True)

        if latest.final:
            session.final = latest
        if latest.final and latest.is_complete and drained.image is not None:
            self.show_stage(STAGE_REBUILD)
            self.begin_reveal(session, latest)
            return
        if drained.image is not None and not session.revealing:
            self.current_received = self.show_picture(self.received_label, drained.image, blocky=latest.blocky)
        self.status.set(self.describe(latest))

    def begin_reveal(self, session: DecodeSession, final: LiveUpdate) -> None:
        """Bring the reconstruction into focus as the last step, instead of snapping it into place."""
        frames, delay = reveal_frames(final.image, final.mode or self.mode, self.current_received, PANEL_SIZE)
        session.revealing = True
        self.status.set("Unpacking the picture...")

        def step(number: int) -> None:
            if number >= len(frames):
                session.revealing = False
                self.show_picture(self.received_label, final.image)
                return
            self.show_picture(self.received_label, frames[number])
            self.after(delay, step, number + 1)

        step(0)

    def finish(self, session: DecodeSession, failure: Exception | None) -> None:
        """Wrap up a decode that has ended (or failed)."""
        self.session = None
        self.update_controls()
        if failure is not None:
            self.report_failure(failure)
        elif session.final is not None and session.final.is_complete:
            self.show_stage(STAGE_ALL_DONE)
            self.status.set(self.describe(session.final))
        elif session.final is None:
            self.show_stage(STAGE_NONE)
            self.status.set("Stopped.")

    def describe(self, update: LiveUpdate) -> str:
        """Return the status line for an update, with a verdict on the result once it is finished."""
        message = update.text
        if update.final and update.is_complete:
            message += f" ({update.image.width}x{update.image.height})"
            if (update.mode or self.mode) is Mode.PIXELS:
                message += " Pixel mode is lossy: it only carries the shrunken pixels, so it won't match the original."
            elif self.original_rgb is not None:
                identical = (update.image.size == self.original_rgb.size
                             and update.image.tobytes() == self.original_rgb.tobytes())
                message += (" Identical to the original." if identical
                            else " Differs from the original (it was re-compressed to fit).")
        return message

    def close(self) -> None:
        """Stop everything and close the window."""
        self.stop()
        self.destroy()
