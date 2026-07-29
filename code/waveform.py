"""
Waveform generator.

Two states:
  - IDLE: near-flatline with tiny organic drift/glitch (never a perfect
    mathematical straight line -- real monitors always have baseline noise).
  - EVENT: a sharp spike (like the football chip's impact pulse) followed
    by a broader rounded hump (like a T-wave / like the yellow oscillation
    trailing into the ball in the reference image), then decays back to idle.

Call `Waveform.step(triggered)` once per sample tick. It returns the next
y-value in normalized units (-1.0 to 1.0). `triggered` should be True only
on the rising edge of a sensor detection (see main.py for debounce logic).
"""

import time
import math
import random


class Waveform:
    def __init__(self, sample_rate_hz=200, event_duration_s=2.2, ramp_duration_s=3.5):
        self.sample_rate_hz = sample_rate_hz
        self.event_duration_s = event_duration_s
        self.ramp_duration_s = ramp_duration_s
        self._event_samples = self._build_event_shape()
        self._event_len = len(self._event_samples)

        self.state = "idle"
        self._event_pos = 0

        # slow-moving idle drift, so the flatline breathes instead of
        # sitting dead-flat
        self._drift_phase = random.uniform(0, math.tau)
        self._noise_seed = random.random()

    def _build_event_shape(self):
        """Builds one full event pulse: a main hump (steep rise, gentler
        fall) followed shortly after by a small dip-then-bump wiggle on
        the way back down to baseline -- matching the reference monitor
        panel's waveform (not a clean symmetric hill).
        """
        n = int(self.sample_rate_hz * self.event_duration_s)
        shape = [0.0] * n

        # --- main hump: steep rise, moderate fall ---
        peak_center = n * 0.33
        peak_height = 1.0
        rise_width = n * 0.03    # steep on the way up
        fall_width = n * 0.08    # a bit gentler on the way down

        for i in range(n):
            if i <= peak_center:
                d = (i - peak_center) / rise_width
            else:
                d = (i - peak_center) / fall_width
            shape[i] = peak_height * math.exp(-0.5 * d * d)

        # --- small "dip then bump" wiggle shortly after the descent ---
        dip_center = peak_center + fall_width * 0.6
        dip_width = n * 0.015
        dip_depth = 0.075
        for i in range(n):
            d = (i - dip_center) / dip_width
            shape[i] -= dip_depth * math.exp(-0.5 * d * d)

        bump_center = dip_center + dip_width * 2
        bump_width = n * 0.028
        bump_height = 0.09
        for i in range(n):
            d = (i - bump_center) / bump_width
            shape[i] += bump_height * math.exp(-0.5 * d * d)

        return shape

    def _ramp(self, t):
        """0 before/at power-on (t<=0), eases smoothly up to 1 over
        ramp_duration_s -- this is what makes the opening dead-flat
        segment blend into the organic jitter instead of snapping on."""
        if t <= 0:
            return 0.0
        if t >= self.ramp_duration_s:
            return 1.0
        x = t / self.ramp_duration_s
        return x * x * (3 - 2 * x)  # smoothstep, gentle ease-in

    def _idle_value(self, t):
        """Tiny organic baseline: slow drift + fine glitch, never a dead line
        once ramped in. Before/around t=0 it stays flat (machine just booted)."""
        ramp = self._ramp(t)
        slow = 0.015 * math.sin(t * 0.5 + self._drift_phase)
        fine_glitch = 0.006 * math.sin(t * 37 + self._noise_seed * 10)
        # occasional tiny random micro-jitter, like real sensor/line noise
        jitter = random.uniform(-0.004, 0.004)
        return (slow + fine_glitch + jitter) * ramp

    def trigger_event(self):
        """Starts (or restarts) the event pulse from the beginning."""
        self.state = "event"
        self._event_pos = 0

    def is_busy(self):
        return self.state == "event"

    def step(self, t):
        """Advance one sample tick and return the next y-value in [-1, 1]."""
        if self.state == "event":
            val = self._event_samples[self._event_pos]
            # blend a little idle noise under the event so it doesn't look
            # like a canned animation
            val += self._idle_value(t) * 0.3
            self._event_pos += 1
            if self._event_pos >= self._event_len:
                self.state = "idle"
            return val
        else:
            return self._idle_value(t)