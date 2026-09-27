#!/usr/bin/env python3
"""
midi_piano_player.py

Reads a MIDI file (any number of tracks/parts) and streams key-state frames
to the piano_driver.ino Arduino over USB serial, using its wire protocol
unchanged:

    0xAA 0x55 <11 payload bytes> <XOR checksum>   @ 250000 baud
    payload bit i (LSB-first within each byte) = key i, 0 = C1 ... 83 = B7

All tracks/parts in the file are merged into one 84-key performance. Because
a physical piano key can only be in one state at a time, overlapping notes
on the same pitch from different parts are turned into explicit
release-then-restrike sequences rather than just being held "on" --
see build_key_timeline() below.

Install deps:
    pip install mido python-rtmidi pyserial

Usage:
    python midi_piano_player.py song.mid --port /dev/ttyACM0
    python midi_piano_player.py song.mid --port COM5 --attack-latency-ms 60 \
        --min-on-ms 40 --release-gap-ms 35
"""

import argparse
import time

import mido
import serial

# --- Protocol constants -- must match piano_driver.ino exactly, unchanged --
SYNC0 = 0xAA
SYNC1 = 0x55
N_KEYS = 84          # C1 (MIDI 24) .. B7 (MIDI 107)
PAYLOAD_BYTES = 11   # ceil(84/8)
BAUD = 250000

MIDI_LOW = 24        # C1
MIDI_HIGH = 107      # B7


def build_frame(active_keys):
    """Pack an iterable of key indices (0..83) into one wire frame. Unchanged."""
    payload = bytearray(PAYLOAD_BYTES)
    for k in active_keys:
        if 0 <= k < N_KEYS:
            payload[k >> 3] |= (1 << (k & 7))
    checksum = 0
    for b in payload:
        checksum ^= b
    return bytes([SYNC0, SYNC1]) + bytes(payload) + bytes([checksum])


def extract_note_intervals(path):
    """
    Merge every track/channel in the MIDI file into one list of
    (key, start_sec, end_sec) intervals -- one per actual musical note.

    note_on/note_off are paired per (channel, note number), so two
    different parts playing overlapping notes on the same pitch stay as
    separate, correctly-timed intervals instead of getting confused with
    each other.
    """
    mid = mido.MidiFile(path)
    open_notes = {}          # (channel, note) -> start_sec
    intervals = []           # (key, start_sec, end_sec)
    t = 0.0

    for msg in mid:  # mido merges all tracks, yielding correct absolute time
        t += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            open_notes[(msg.channel, msg.note)] = t
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            start = open_notes.pop((msg.channel, msg.note), None)
            if start is None:
                continue  # note_off with no matching note_on -- ignore
            note = msg.note
            if MIDI_LOW <= note <= MIDI_HIGH:
                intervals.append((note - MIDI_LOW, start, t))

    return intervals


def build_key_timeline(intervals, attack_latency_ms, min_on_ms,
                        release_gap_ms, onset_merge_ms):
    """
    Turn the raw musical note intervals into physically valid actuator
    segments, one key at a time.

    Because a key can only be in one physical state, several rules apply
    when more than one part wants the same pitch:

      * Two notes starting within `onset_merge_ms` of each other are
        treated as one simultaneous attack (e.g. two parts striking a
        unison chord tone together) -- they share a single strike rather
        than re-triggering.
      * If a new note-on for a key arrives WHILE a previous note on that
        same key is still supposed to be sounding, the previous note is
        force-cut short -- released just long enough before the new
        strike to satisfy `release_gap_ms` -- so the new note gets its
        own attack transient at (approximately) its own notated onset,
        instead of being queued to start only after the held note's full
        duration finishes.
      * Every strike is held for at least `min_on_ms`, regardless of the
        notated musical duration (a mechanical minimum, not a musical one).
        This floor can delay a re-strike past its notated onset if the
        previous note hadn't been held long enough yet to be released.
      * `release_gap_ms` of off-time is always guaranteed between one
        strike's release and the next strike on the same key.

    Returns a flat, time-sorted list of [time_ms, key, is_on] events.
    """
    by_key = {}
    for key, start, end in intervals:
        by_key.setdefault(key, []).append((start * 1000.0, end * 1000.0))

    events = []
    for key, notes in by_key.items():
        notes.sort(key=lambda n: n[0])

        # Merge near-simultaneous onsets (different parts striking the
        # same pitch at effectively the same instant) into one note.
        merged = []
        for on_ms, off_ms in notes:
            if merged and on_ms - merged[-1][0] <= onset_merge_ms:
                merged[-1] = (merged[-1][0], max(merged[-1][1], off_ms))
            else:
                merged.append((on_ms, off_ms))

        cur_on = None          # actual strike time of the held segment
        cur_musical_off = None # its notated (un-adjusted) note-off

        for on_ms, off_ms in merged:
            intended_strike = on_ms - attack_latency_ms

            if cur_on is None:
                cur_on = intended_strike
                cur_musical_off = off_ms
                continue

            # Latest moment the held note could release and still leave a
            # full release_gap before this new note's intended strike.
            required_release_deadline = intended_strike - release_gap_ms

            # Cut the held note off at that deadline -- but never before
            # its own mechanical min-on floor, and never later than its
            # own natural musical end (don't artificially stretch a note
            # that already finished with plenty of gap to spare).
            actual_off = max(
                cur_on + min_on_ms,
                min(required_release_deadline, cur_musical_off),
            )

            # The new strike happens at its own intended time, unless the
            # min-on floor above forced a later release than that allows.
            new_on = max(intended_strike, actual_off + release_gap_ms)

            events.append([cur_on, key, True])
            events.append([actual_off, key, False])

            cur_on = new_on
            cur_musical_off = off_ms

        # Finalize whichever segment is still open at the end.
        final_off = max(cur_on + min_on_ms, cur_musical_off)
        events.append([cur_on, key, True])
        events.append([final_off, key, False])

    events.sort(key=lambda e: (e[0], e[1]))
    return events


def normalize_start_time(events):
    """
    Shift every event time so the earliest one is >= 0, instead of letting
    negative pre-roll times (e.g. attack-latency lead-in for the very first
    note) get clipped away by starting the wall clock at t=0.

    Without this, a note at MIDI time 0 with 50ms of attack latency wants
    to strike at -50ms -- which has already "happened" the instant
    playback starts, so the solenoid gets fired with zero lead time
    instead of the intended 50ms. Shifting the whole timeline by the
    magnitude of the most-negative event gives it that lead time back by
    effectively starting the clock 50ms before the first musical onset.
    """
    if not events:
        return events
    min_t = min(e[0] for e in events)
    if min_t < 0:
        shift = -min_t
        for e in events:
            e[0] += shift
    return events


def stream(path, port, attack_latency_ms, min_on_ms, release_gap_ms,
           onset_merge_ms, send_interval_ms):
    intervals = extract_note_intervals(path)
    if not intervals:
        print("No notes found in range C1-B7 -- nothing to play.")
        return

    events = build_key_timeline(
        intervals, attack_latency_ms, min_on_ms, release_gap_ms, onset_merge_ms
    )
    events = normalize_start_time(events)

    ser = serial.Serial(port, BAUD, timeout=0)
    time.sleep(2)  # let the Mega finish its bootloader reset after port open

    # Reference-counted per key. build_key_timeline() already guarantees a
    # given key's own segments never overlap, so counts should only ever be
    # 0 or 1 in practice -- this just stays defensive against timing ties.
    active_counts = {}
    ev_idx = 0
    n_events = len(events)
    start = time.perf_counter()
    next_keepalive = start

    print(f"Streaming {n_events} actuator events on {port}...")
    try:
        while ev_idx < n_events or any(c > 0 for c in active_counts.values()):
            now_ms = (time.perf_counter() - start) * 1000.0

            if ev_idx < n_events and events[ev_idx][0] <= now_ms:
                # Only events sharing the exact same scheduled time are
                # combined into one frame (a genuine simultaneous attack
                # across keys). Anything else -- in particular a same-key
                # OFF followed shortly after by an ON -- is always sent as
                # its own frame, so a scheduled release can never be
                # silently absorbed into the next strike no matter how
                # short release_gap_ms or send_interval_ms are set.
                batch_time = events[ev_idx][0]
                while ev_idx < n_events and events[ev_idx][0] == batch_time:
                    _, key, is_on = events[ev_idx]
                    if is_on:
                        active_counts[key] = active_counts.get(key, 0) + 1
                    else:
                        active_counts[key] = max(0, active_counts.get(key, 0) - 1)
                    ev_idx += 1

                active = {k for k, c in active_counts.items() if c > 0}
                ser.write(build_frame(active))
                next_keepalive = time.perf_counter() + send_interval_ms / 1000.0

            elif time.perf_counter() >= next_keepalive:
                # No event due right now -- send a keepalive frame at the
                # normal cadence so the Arduino's LINK_TIMEOUT_MS backstop
                # never trips during a musical rest.
                active = {k for k, c in active_counts.items() if c > 0}
                ser.write(build_frame(active))
                next_keepalive += send_interval_ms / 1000.0

            time.sleep(0.001)
    finally:
        ser.write(build_frame(()))  # all-off before closing, always
        time.sleep(0.05)
        ser.close()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Play a MIDI file on the piano actuator.")
    parser.add_argument("midi_file")
    parser.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyACM0 or COM5")
    parser.add_argument("--attack-latency-ms", type=float, default=50.0,
                         help="Strike solenoid this long before the notated onset (default: 50)")
    parser.add_argument("--min-on-ms", type=float, default=30.0,
                         help="Minimum time an actuator stays energized per strike, "
                              "regardless of musical note duration (default: 30)")
    parser.add_argument("--release-gap-ms", type=float, default=30.0,
                         help="Minimum off-time between a key's release and its "
                              "next re-strike (default: 30)")
    parser.add_argument("--onset-merge-ms", type=float, default=3.0,
                         help="Note-on events on the same key within this many ms "
                              "of each other are treated as one simultaneous "
                              "attack instead of a forced re-strike (default: 3)")
    parser.add_argument("--send-interval-ms", type=float, default=5.0,
                         help="Serial frame send rate (default: 5)")
    args = parser.parse_args()

    stream(
        args.midi_file, args.port,
        attack_latency_ms=args.attack_latency_ms,
        min_on_ms=args.min_on_ms,
        release_gap_ms=args.release_gap_ms,
        onset_merge_ms=args.onset_merge_ms,
        send_interval_ms=args.send_interval_ms,
    )
