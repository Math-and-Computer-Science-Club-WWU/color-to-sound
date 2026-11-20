"""All the words the window shows: step names, explanations and captions."""

from common.modes import Channel, Mode

STAGES = ("Prepare the image", "Turn it into sound", "Listen and decode", "Rebuild the picture")
STAGE_PREPARE, STAGE_MAKE_SOUND, STAGE_LISTEN, STAGE_REBUILD = range(len(STAGES))
STAGE_NONE = -1  # nothing started yet
STAGE_ALL_DONE = len(STAGES)  # every step finished

IDLE_EXPLANATION = "Pick an image and press Go: it becomes sound, then the sound is turned back into the picture."

ORIGINAL_CAPTION = "The picture being sent."
SIGNAL_CAPTION = (
    "What the sound looks like. Each bright bar is one beep; the higher the bar, "
    "the bigger the number it carries. Newest is on the right."
)
RECONSTRUCTION_CAPTIONS = {
    Mode.FILE: (
        "Each colored square is one data byte arriving. They look like noise because compressed data does. "
        "Once they're all in, they unpack into the picture."
    ),
    Mode.PIXELS: "Rebuilt one pixel at a time from the beeps. Dark means not heard yet.",
}

_PREPARE = {
    Mode.FILE: (
        "The image file is already compressed into a list of numbers (bytes, 0 to 255). "
        "We send those numbers exactly as they are."
    ),
    Mode.PIXELS: "The image is shrunk to a small grid. Every pixel is three numbers: how much red, green and blue.",
}
_PREPARE_OVER_AIR_FILE = " Over the air the file is shrunk to about 3 KB first."

_AIR_PACKETS = (
    "The numbers are cut into packets. Each packet starts with a recognizable pattern and carries "
    "its position and a checksum. The beeps are slow and far apart in pitch so a speaker and "
    "microphone can cope."
)
_MAKE_SOUND = {
    (Channel.CABLE, Mode.FILE): (
        "Each number becomes one short beep: a bigger number is a higher pitch. "
        "The audio file is just those beeps back to back."
    ),
    (Channel.CABLE, Mode.PIXELS): (
        "Every pixel becomes 8 beeps: where it is, then its blue, green and red (with markers in between). "
        "A bigger number is a higher pitch."
    ),
    (Channel.AIR, Mode.FILE): _AIR_PACKETS,
    (Channel.AIR, Mode.PIXELS): _AIR_PACKETS,
}

_LISTEN = {
    Channel.CABLE: (
        "The decoder listens in tiny slices, measures the pitch of each beep and turns it back into a "
        "number. In the Signal panel, each bright bar is one beep."
    ),
    Channel.AIR: (
        "The decoder finds each packet's start pattern, reads its beeps and checks the checksum. "
        "Good packets turn green on the map. Damaged ones are skipped, which is what Repeats is for."
    ),
}

_REBUILD = {
    Mode.FILE: "Every number has arrived and the checksum matched, so the bytes unpack into the original picture.",
    Mode.PIXELS: (
        "Every pixel has been placed, and the small picture is smoothed up to a bigger size. "
        "Detail lost when shrinking can't come back."
    ),
}


def explain(channel: Channel, mode: Mode, stage: int) -> str:
    """Return a plain-language description of what a stage is doing."""
    if stage == STAGE_PREPARE:
        extra = _PREPARE_OVER_AIR_FILE if channel is Channel.AIR and mode is Mode.FILE else ""
        return _PREPARE[mode] + extra
    if stage == STAGE_MAKE_SOUND:
        return _MAKE_SOUND[channel, mode]
    if stage == STAGE_LISTEN:
        return _LISTEN[channel]
    return _REBUILD[mode]


def format_duration(seconds: float) -> str:
    """Show a length of time as 'M min S s', or just 'S s' under a minute."""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes} min {secs} s" if minutes else f"{secs} s"
