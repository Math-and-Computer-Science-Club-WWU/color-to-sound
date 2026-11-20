"""The two ways sound can travel, and the two things that can be sent."""

from enum import Enum


class Channel(Enum):
    """How the sound gets from the sender to the receiver."""

    CABLE = "cable"  # a clean audio file: fast, but one wrong tone can ruin the result
    AIR = "air"  # speaker to microphone: slow, but built to survive noise and echo


class Mode(Enum):
    """What is being sent."""

    FILE = "file"  # the compressed image file itself: arrives as an exact copy
    PIXELS = "pixels"  # the red, green and blue values of a shrunken copy: a blurry preview
