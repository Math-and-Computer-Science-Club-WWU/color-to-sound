"""Finding and decoding packets in recorded audio, as it arrives."""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from air_channel.packets import (
    DATA_BYTES,
    FREQUENCIES,
    NIBBLE_BITS,
    NUM_DATA_TONES,
    PREAMBLE,
    TONE_SECONDS,
    TONES_PER_PACKET,
    Packet,
    PayloadKind,
    packet_count,
    parse_packet,
    payload_length,
)

WINDOWS_PER_TONE = 8  # analysis windows start this many times per tone length
MIN_PREAMBLE_SCORE = 0.45  # how clearly the start pattern must stand out (0 to 1)
RECENT_SECONDS = 3.0  # how much audio is kept for the spectrogram
QUIET_AMPLITUDE = 0.01  # tones quieter than this (about -40 dBFS) are treated as silence
BLOCK_WINDOWS = 256  # windows analysed per matrix multiplication
HANN_ENERGY_FACTOR = 4  # a Hann-windowed sine of amplitude A measures about length * A / 4
INITIAL_CAPACITY = 4096  # starting size of the per-window result arrays (they double when full)


class AirReceiver:
    """Finds and decodes packets in audio that is fed in piece by piece.

    A recording can start at any moment and the sound card clocks of sender and receiver may disagree a
    little, so no timing is assumed: every packet is located by its own start pattern.

    How it works:
      1. Slide a window one tone long across the audio, a few times per tone. For each window, measure how
         strongly each of our 18 tones is present (a Fourier sum at just those pitches) and remember the
         loudest one and how clearly it stands out from the rest.
      2. Look for the start pattern: four windows, one tone apart, that hear the two sync tones alternating
         (A, B, A, B). Three out of four matching is enough, to allow for a little noise.
      3. From the best-aligned position, read the next 82 tones as 4-bit values and check the packet's CRC.
    """

    def __init__(self, sample_rate: int) -> None:
        """Prepare to receive audio recorded at `sample_rate`."""
        self.sample_rate = sample_rate
        self.tone_length = round(sample_rate * TONE_SECONDS)  # samples per tone
        self.hop = self.tone_length // WINDOWS_PER_TONE  # samples between window starts
        self.hops_per_tone = self.tone_length / self.hop  # not a whole number in general

        times = np.arange(self.tone_length)
        self.window = np.hanning(self.tone_length).astype(np.float32)
        # column k holds the complex wave at tone k's pitch; multiplying audio by it measures that tone
        self.basis = np.exp(-2j * np.pi * np.outer(times, FREQUENCIES) / sample_rate).astype(np.complex64)
        self.quiet_power = (self.tone_length * QUIET_AMPLITUDE / HANN_ENERGY_FACTOR) ** 2

        self.buffer = np.zeros(0, dtype=np.float32)  # audio not yet analysed
        self.recent = np.zeros(0, dtype=np.float32)  # the last few seconds, for the spectrogram
        self.level = 0.0  # RMS volume of the latest piece of audio
        self.windows_done = 0
        self.loudest_tone = np.zeros(INITIAL_CAPACITY, dtype=np.int8)  # per window: which of our tones is loudest
        self.clarity = np.zeros(INITIAL_CAPACITY, dtype=np.float32)  # per window: that tone's share of the energy
        self.scan_position = 0  # the next window to search for a start pattern

        self.packets: dict[int, bytes] = {}  # sequence number -> that packet's 32 data bytes
        self.kind: PayloadKind | None = None
        self.aux: int | None = None
        self.total: int | None = None  # packets needed in all
        self.damaged = 0  # start patterns found whose packet then failed its CRC

    @property
    def complete(self) -> bool:
        """True once every packet has arrived."""
        return self.total is not None and len(self.packets) == self.total

    def feed(self, samples: np.ndarray) -> int:
        """Add recorded audio (mono floats between -1 and 1). Returns how many new packets were decoded."""
        samples = np.asarray(samples, dtype=np.float32)
        if not len(samples):
            return 0
        self.level = float(np.sqrt(np.mean(samples * samples)))
        self.recent = np.concatenate((self.recent, samples))[-int(RECENT_SECONDS * self.sample_rate):]
        self.buffer = np.concatenate((self.buffer, samples))

        windows = sliding_window_view(self.buffer, self.tone_length)[::self.hop]
        for start in range(0, len(windows), BLOCK_WINDOWS):
            self._analyse(windows[start:start + BLOCK_WINDOWS])
        self.buffer = self.buffer[len(windows) * self.hop:]  # keep only what hasn't had a window start in it
        return self._find_packets()

    def _analyse(self, block: np.ndarray) -> None:
        """Measure our tones in each window of the block and store the loudest and its clarity."""
        power = np.abs((block * self.window) @ self.basis) ** 2  # shape: (windows, tones)
        loudest = power.max(axis=1)
        share = np.where(loudest > self.quiet_power, loudest / (power.sum(axis=1) + 1e-12), 0)

        end = self.windows_done + len(block)
        if end > len(self.loudest_tone):  # out of room: grow both arrays
            extra = max(end, 2 * len(self.loudest_tone)) - len(self.loudest_tone)
            self.loudest_tone = np.concatenate((self.loudest_tone, np.zeros(extra, dtype=np.int8)))
            self.clarity = np.concatenate((self.clarity, np.zeros(extra, dtype=np.float32)))
        self.loudest_tone[self.windows_done:end] = power.argmax(axis=1)
        self.clarity[self.windows_done:end] = share
        self.windows_done = end

    def _window_of_tone(self, start: int, tone_number: int) -> int:
        """Return the window that sits at the start of tone `tone_number`, for a packet starting at window `start`."""
        return round(start + tone_number * self.hops_per_tone)

    def _preamble_score(self, start: int) -> float:
        """How well a start pattern begins at window `start` (0 if fewer than 3 of its 4 tones match)."""
        score = 0.0
        matches = 0
        for number, expected in enumerate(PREAMBLE):
            window = self._window_of_tone(start, number)
            if self.loudest_tone[window] == expected:
                matches += 1
                score += self.clarity[window]
        return score / len(PREAMBLE) if matches >= len(PREAMBLE) - 1 else 0.0

    def _find_packets(self) -> int:
        """Search the analysed windows for start patterns and decode the packets after them."""
        found = 0
        windows_needed = self._window_of_tone(0, TONES_PER_PACKET) + 2  # from a packet's start to its last tone
        position = self.scan_position
        while self._window_of_tone(position, len(PREAMBLE)) < self.windows_done:
            if self._preamble_score(position) < MIN_PREAMBLE_SCORE:
                position += 1
                continue
            latest_start = position + int(self.hops_per_tone)
            if latest_start + windows_needed >= self.windows_done:
                break  # the rest of this packet hasn't been heard yet
            start = max(range(position, latest_start), key=self._preamble_score)  # best alignment
            raw = self._read_packet_bytes(start)
            packet = parse_packet(raw) if raw is not None else None
            if packet is None:
                self.damaged += 1
                position = start + int(self.hops_per_tone)
                continue
            found += self._store(packet)
            # resume one tone early: the estimate of where the next packet starts can drift by a few windows,
            # and the search only looks forwards
            position = self._window_of_tone(start, TONES_PER_PACKET - 1)
        self.scan_position = position
        return found

    def _read_packet_bytes(self, start: int) -> bytes | None:
        """Read a packet's tones, starting at window `start`, as bytes. None if a tone isn't a data tone."""
        nibbles = []
        for number in range(len(PREAMBLE), TONES_PER_PACKET):
            centre = self._window_of_tone(start, number)
            # a window one step either side may be better aligned if the clocks have drifted a little
            best = max((centre - 1, centre, centre + 1), key=lambda window: self.clarity[window])
            if self.loudest_tone[best] >= NUM_DATA_TONES:
                return None
            nibbles.append(int(self.loudest_tone[best]))
        high, low = nibbles[::2], nibbles[1::2]
        return bytes(h << NIBBLE_BITS | lo for h, lo in zip(high, low, strict=True))

    def _store(self, packet: Packet) -> int:
        """Keep a decoded packet if it belongs to this transmission and is new. Returns 1 if kept, else 0."""
        if self.kind is None:  # the first good packet tells us what is being sent
            self.kind, self.aux = packet.kind, packet.aux
            self.total = packet_count(packet.kind, packet.aux)
        belongs = (packet.kind, packet.aux) == (self.kind, self.aux) and packet.seq < self.total
        if not belongs or packet.seq in self.packets:
            return 0
        self.packets[packet.seq] = packet.data
        return 1

    def missing(self) -> list[int]:
        """Sequence numbers of the packets that haven't arrived yet."""
        if self.total is None:
            return []
        return [seq for seq in range(self.total) if seq not in self.packets]

    def assemble_payload(self) -> tuple[np.ndarray, np.ndarray]:
        """Return (bytes, known): the payload so far, and which of its bytes have actually arrived."""
        length = payload_length(self.kind, self.aux)
        data = np.zeros(self.total * DATA_BYTES, dtype=np.uint8)
        known = np.zeros(self.total * DATA_BYTES, dtype=bool)
        for seq, chunk in self.packets.items():
            data[seq * DATA_BYTES:(seq + 1) * DATA_BYTES] = np.frombuffer(chunk, dtype=np.uint8)
            known[seq * DATA_BYTES:(seq + 1) * DATA_BYTES] = True
        return data[:length], known[:length]
