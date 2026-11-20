"""Tone settings for the cable channel. The sender and the listener both import these."""

from common.tones import ToneFormat

SAMPLE_RATE = 48000

# A tone lasts TONE_SECONDS. For a tone to land exactly on one FFT bin, its pitch must be a whole multiple of
# 1 / TONE_SECONDS Hz, so shorter tones need wider steps between pitches. The top pitch must stay below half
# the sample rate.
TONE_SECONDS = 0.0125
BASE_HZ = 400  # pitch of value 0
STEP_HZ = 80  # extra pitch per unit of value, so value v is sent at BASE_HZ + STEP_HZ * v
SEPARATOR_HZ = 160  # marker between a pixel's colors
END_HZ = 240  # marker at the end of a frame

VALUE_COUNT = 256  # one tone can carry any byte value
VALUE_FREQUENCIES = [BASE_HZ + STEP_HZ * value for value in range(VALUE_COUNT)]  # value -> pitch, O(1) lookup

FORMAT = ToneFormat(SAMPLE_RATE, TONE_SECONDS)
