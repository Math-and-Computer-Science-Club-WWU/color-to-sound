"""Settings shared by the encoder and the decoder, so neither imports the other."""

RATE = 44100  # Samples per second
TONE_SEC = 0.05  # Duration of each tone in seconds
BASE_HZ, STEP_HZ = 400, 40  # Base frequency and step for value -> Hz mapping
SEP_HZ, END_HZ = 200, 300  # Separator and end frequencies
FREQ = [BASE_HZ + STEP_HZ * v for v in range(256)]  # value -> Hz, O(1) lookup
