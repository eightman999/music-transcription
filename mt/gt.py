"""Ground truth conversion from MIDI files.

This module provides functions for converting MIDI files to ground truth
note representations, including pedal interval detection and sustain extension.
"""

import bisect
from typing import Dict, List


def pedal_intervals(cc64: List[tuple[float, int]], end_time: float, threshold: int = 64) -> List[Dict]:
    """Convert CC64 (sustain pedal) events to intervals.
    
    cc64 = (time, value) pairs. State machine: sort by time; when the state is 'up' 
    and value >= threshold the pedal goes down at that time; when the state is 'down' 
    and value < threshold it goes up at that time and one interval 
    {"onset": down_time, "offset": up_time} is emitted. Repeated values on the same side 
    change nothing.
    If the pedal is still down at the end, close the interval at end_time. 
    Intervals of zero length are dropped.
    
    Args:
        cc64: List of (time, value) tuples for CC64 events
        end_time: End time of the piece (to close any open pedal interval)
        threshold: Threshold for pedal on/off (default 64)
        
    Returns:
        List of pedal interval dicts with "onset" and "offset" keys
    """
    if not cc64:
        return []
    
    # Sort by time
    cc64_sorted = sorted(cc64, key=lambda x: x[0])
    
    intervals = []
    state = 'up'  # 'up' or 'down'
    down_time = None
    last_value = None
    
    for time, value in cc64_sorted:
        # Skip repeated values on the same side
        if last_value is not None:
            if state == 'up' and value >= threshold and last_value >= threshold:
                continue
            if state == 'down' and value < threshold and last_value < threshold:
                continue
        
        last_value = value
        
        if state == 'up' and value >= threshold:
            # Pedal goes down
            state = 'down'
            down_time = time
        elif state == 'down' and value < threshold:
            # Pedal goes up
            state = 'up'
            if down_time is not None and time > down_time:
                intervals.append({"onset": down_time, "offset": time})
            down_time = None
    
    # Close any open interval at end_time
    if state == 'down' and down_time is not None and end_time > down_time:
        intervals.append({"onset": down_time, "offset": end_time})
    
    # Filter out zero-length intervals
    intervals = [iv for iv in intervals if iv["offset"] > iv["onset"]]
    
    return intervals


def midi_to_gt(midi_path: str) -> Dict:
    """Convert a MIDI file to ground truth representation.
    
    Returns a dict with "notes" and "pedal" keys.
    Notes are exactly as recorded: onset = note.start, offset = note.end 
    (key release), velocity = note.velocity, pitch = note.pitch, all instruments 
    merged, sorted by (onset, pitch).
    pedal = pedal_intervals() over the CC64 events of all instruments, 
    end_time = pm.get_end_time().
    
    Args:
        midi_path: Path to the MIDI file
        
    Returns:
        Dict with "notes" and "pedal" keys
    """
    import pretty_midi
    
    pm = pretty_midi.PrettyMIDI(midi_path)
    end_time = pm.get_end_time()
    
    # Collect all notes from all instruments
    all_notes = []
    for instrument in pm.instruments:
        for note in instrument.notes:
            all_notes.append({
                'pitch': int(note.pitch),
                'onset': float(note.start),
                'offset': float(note.end),
                'velocity': int(note.velocity),
            })
    
    # Sort by (onset, pitch)
    all_notes.sort(key=lambda n: (n['onset'], n['pitch']))
    
    # Collect all CC64 events from all instruments
    all_cc64 = []
    for instrument in pm.instruments:
        for cc in instrument.control_changes:
            if cc.number == 64:  # Sustain pedal
                all_cc64.append((float(cc.time), int(cc.value)))
    
    # Get pedal intervals
    pedal = pedal_intervals(all_cc64, end_time)
    
    return {
        "notes": all_notes,
        "pedal": pedal,
    }


def sustain_extended(notes: List[Dict], pedal: List[Dict]) -> List[Dict]:
    """Extend note offsets based on pedal intervals and next note onsets.
    
    Returns a new list in the same order; only "offset" may change. For each note:
    1. off = note["offset"]. If a pedal interval satisfies onset <= off < offset 
       (pedal is down at the key release), off = that interval's offset.
    2. nxt = the onset of the next note of the same pitch with onset > this note's onset. 
       If it exists and nxt < off, off = nxt.
    3. off is never smaller than the raw offset unless rule 2 applied, and never <= 
       the note onset (if it would be, keep the raw offset).
    
    Uses bisect / per-pitch lists for efficiency (O(n log n) instead of O(n^2)).
    
    Args:
        notes: List of note dicts with pitch, onset, offset, velocity
        pedal: List of pedal interval dicts with onset, offset
        
    Returns:
        New list of note dicts with potentially extended offsets
    """
    if not notes:
        return []
    
    # Build per-pitch list of onsets for rule 2
    # pitch -> sorted list of onsets
    pitch_onsets = {}
    for note in notes:
        pitch = note['pitch']
        if pitch not in pitch_onsets:
            pitch_onsets[pitch] = []
        pitch_onsets[pitch].append(note['onset'])
    
    # Sort pedal intervals by onset for bisect
    pedal_sorted = sorted(pedal, key=lambda p: p['onset'])
    pedal_onsets = [p['onset'] for p in pedal_sorted]
    pedal_offsets = [p['offset'] for p in pedal_sorted]
    
    result = []
    
    for note in notes:
        pitch = note['pitch']
        onset = note['onset']
        raw_offset = note['offset']
        velocity = note['velocity']
        
        # Rule 1: Check if pedal is down at key release
        off = raw_offset
        
        # Find pedal intervals that contain the raw offset
        # We want intervals where: onset <= raw_offset < offset
        # Use bisect to find the rightmost pedal onset <= raw_offset
        idx = bisect.bisect_right(pedal_onsets, raw_offset) - 1
        
        # Check all overlapping intervals (there might be multiple)
        # We want the one with the latest offset
        max_pedal_offset = off
        for i in range(idx, -1, -1):
            if pedal_onsets[i] <= raw_offset < pedal_offsets[i]:
                if pedal_offsets[i] > max_pedal_offset:
                    max_pedal_offset = pedal_offsets[i]
            elif pedal_onsets[i] > raw_offset:
                break
        
        # Also check forward for intervals that start before raw_offset
        for i in range(idx + 1, len(pedal_onsets)):
            if pedal_onsets[i] <= raw_offset < pedal_offsets[i]:
                if pedal_offsets[i] > max_pedal_offset:
                    max_pedal_offset = pedal_offsets[i]
            elif pedal_onsets[i] > raw_offset:
                break
        
        if max_pedal_offset > off:
            off = max_pedal_offset
        
        # Rule 2: Check for next note of same pitch
        if pitch in pitch_onsets:
            onsets = pitch_onsets[pitch]
            # Find the first onset > this note's onset
            pos = bisect.bisect_right(onsets, onset)
            if pos < len(onsets):
                nxt = onsets[pos]
                if nxt < off:
                    off = nxt
        
        # Rule 3: Ensure off > onset and off >= raw_offset (unless rule 2 made it smaller)
        if off <= onset:
            off = raw_offset
        
        result.append({
            'pitch': pitch,
            'onset': onset,
            'offset': off,
            'velocity': velocity,
        })
    
    return result
