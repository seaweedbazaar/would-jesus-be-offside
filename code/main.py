"""
Would Jesus Be Offside? -- monitor display driver.

Reads distance from a VL53L1X. When something/someone crosses the
trigger distance, the flatline erupts into the football-chip-inspired
event waveform, then settles back into the idle flatline.

The trace lives inside a 14-row grid that fills the entire screen
(matching the reference monitor image): horizontal gridlines are
subtly emphasized every 3rd/8th/13th row up from the bottom, and
vertical gridlines every 5th column. The idle flatline sits exactly
on the first emphasized horizontal line (3 rows up from the bottom
edge of the screen).

Controls while testing on a laptop screen (simulate mode):
  SPACE       -- trigger the waveform once (independent of distance)
  UP          -- simulate walking closer (tests real distance-trigger path)
  DOWN        -- simulate walking away again
  F           -- toggle fullscreen
  ESC / Q     -- quit

Real hardware run (on the Pi, with VL53L1X wired up):
  python3 main.py --hardware

Laptop test run (no sensor needed):
  python3 main.py --windowed
"""

import sys
import time
import argparse
import pygame

from sensor_reader import DistanceSensor
from waveform import Waveform

# ---- tunables ----
TRIGGER_DISTANCE_MM = 1000      # closer than this = "detected"
COOLDOWN_S = 1.5               # minimum time between re-triggers
SAMPLE_RATE_HZ = 200           # waveform samples per second
SAMPLE_SPACING_CELL_FRACTION = 0.055    # trace horizontal density, as a fraction of cell_size
TRACE_COLOR = (150, 235, 195)  # lighter mint-green, closer to the reference
BG_COLOR = (5, 8, 6)
GRID_COLOR = (28, 48, 40)       # thin gridlines
GRID_COLOR_THICK = (38, 62, 52)  # emphasized gridlines -- subtly brighter, not loud

# --- panel layout: 14 rows tall, fills the whole screen ---
PANEL_ROWS = 14
PANEL_HEIGHT_RATIO = 1.0        # panel fills the entire screen height
PANEL_WIDTH_RATIO = 1.0         # panel fills the entire screen width
PANEL_BOTTOM_MARGIN_RATIO = 0.0  # no gap -- panel touches the screen edges
THICK_ROW_STEPS = (3, 8, 13)    # counted from the bottom edge upward
THICK_COL_STEP = 5              # every 5th vertical line is emphasized
BASELINE_ROW_FROM_BOTTOM = 3    # flatline sits on this emphasized row
AMPLITUDE_CELLS = 3.5           # how many grid-cells tall the event hump swings


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--hardware", action="store_true",
                   help="use the real VL53L1X instead of a simulated sensor")
    p.add_argument("--windowed", action="store_true",
                   help="start windowed instead of fullscreen")
    return p.parse_args()


def compute_panel(w, h):
    """Returns (panel_x, panel_y_top, panel_width, panel_height, cell_size,
    columns, panel_y_bottom, baseline_y) for the current screen size."""
    panel_height = h * PANEL_HEIGHT_RATIO
    cell_size = panel_height / PANEL_ROWS

    raw_width = w * PANEL_WIDTH_RATIO
    columns = max(1, int(raw_width / cell_size))
    panel_width = columns * cell_size
    panel_x = (w - panel_width) / 2

    panel_bottom_margin = h * PANEL_BOTTOM_MARGIN_RATIO
    panel_y_bottom = h - panel_bottom_margin
    panel_y_top = panel_y_bottom - panel_height

    baseline_y = panel_y_bottom - BASELINE_ROW_FROM_BOTTOM * cell_size

    return panel_x, panel_y_top, panel_width, panel_height, cell_size, columns, panel_y_bottom, baseline_y


def draw_panel_grid(surface, panel_x, panel_y_top, panel_width, panel_height, cell_size, columns, panel_y_bottom):
    # horizontal lines: 15 lines for 14 rows, i = 0 (bottom) .. 14 (top)
    for i in range(PANEL_ROWS + 1):
        y = panel_y_bottom - i * cell_size
        thick = i in THICK_ROW_STEPS
        color = GRID_COLOR_THICK if thick else GRID_COLOR
        pygame.draw.line(surface, color, (panel_x, y), (panel_x + panel_width, y), 1)

    # vertical lines: columns + 1 lines, j = 0 (left) .. columns (right)
    for j in range(columns + 1):
        x = panel_x + j * cell_size
        thick = (j % THICK_COL_STEP == 0)
        color = GRID_COLOR_THICK if thick else GRID_COLOR
        pygame.draw.line(surface, color, (x, panel_y_top), (x, panel_y_top + panel_height), 1)


def prefill_buffer(wave, length, sample_interval, now):
    """Fills the scroll buffer with idle-noise samples as if they'd been
    sampled continuously up to `now`, so there's no dead-straight seam at
    startup or on resize -- the trace looks organic from the first frame."""
    return [wave.step(now - (length - i) * sample_interval) for i in range(length)]


def main():
    args = parse_args()

    pygame.init()
    pygame.mouse.set_visible(False)

    flags = 0 if args.windowed else pygame.FULLSCREEN
    screen = pygame.display.set_mode((0, 0) if not args.windowed else (1000, 500), flags)
    pygame.display.set_caption("Would Jesus Be Offside?")
    w, h = screen.get_size()

    panel_x, panel_y_top, panel_width, panel_height, cell_size, columns, panel_y_bottom, baseline_y = compute_panel(w, h)
    amplitude = AMPLITUDE_CELLS * cell_size

    clock = pygame.time.Clock()

    sensor = DistanceSensor(simulate=not args.hardware).start()
    wave = Waveform(sample_rate_hz=SAMPLE_RATE_HZ)

    pixels_per_sample = cell_size * SAMPLE_SPACING_CELL_FRACTION
    buffer_len = max(2, int(panel_width // pixels_per_sample))
    sample_interval = 1.0 / SAMPLE_RATE_HZ
    buffer = prefill_buffer(wave, buffer_len, sample_interval, 0.0)

    sample_accum = 0.0
    last_trigger_time = -999.0
    was_close = False

    def recompute_layout():
        nonlocal panel_x, panel_y_top, panel_width, panel_height, cell_size
        nonlocal columns, panel_y_bottom, baseline_y, amplitude, buffer_len, buffer
        panel_x, panel_y_top, panel_width, panel_height, cell_size, columns, panel_y_bottom, baseline_y = compute_panel(w, h)
        amplitude = AMPLITUDE_CELLS * cell_size
        buffer_len = max(2, int(panel_width // (cell_size * SAMPLE_SPACING_CELL_FRACTION)))
        buffer = prefill_buffer(wave, buffer_len, sample_interval, now)

    t0 = time.time()
    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        now = time.time() - t0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_f:
                    args.windowed = not args.windowed
                    flags = 0 if args.windowed else pygame.FULLSCREEN
                    screen = pygame.display.set_mode(
                        (1000, 500) if args.windowed else (0, 0), flags)
                    w, h = screen.get_size()
                    recompute_layout()
                elif event.key == pygame.K_SPACE and not args.hardware:
                    # fires one trigger directly, like a single sensor
                    # detection event -- doesn't permanently change the
                    # simulated distance, so pressing it again always works
                    if not wave.is_busy() and (now - last_trigger_time) > COOLDOWN_S:
                        wave.trigger_event()
                        last_trigger_time = now
                elif event.key == pygame.K_UP and not args.hardware:
                    # simulate someone walking closer (tests the real
                    # distance-based rising-edge trigger path below)
                    sensor.set_sim_distance_cm(20)
                elif event.key == pygame.K_DOWN and not args.hardware:
                    # simulate walking away again
                    sensor.set_sim_distance_cm(200)

        # --- read sensor, decide on trigger with debounce ---
        dist_mm = sensor.read_mm()
        is_close = dist_mm is not None and dist_mm < TRIGGER_DISTANCE_MM

        if is_close and not was_close and (now - last_trigger_time) > COOLDOWN_S:
            wave.trigger_event()
            last_trigger_time = now
        was_close = is_close

        # --- advance waveform samples at fixed sample rate,
        # independent of render frame rate ---
        sample_accum += dt
        while sample_accum >= sample_interval:
            sample_accum -= sample_interval
            y = wave.step(now)
            buffer.pop(0)
            buffer.append(y)

        # --- draw ---
        screen.fill(BG_COLOR)
        draw_panel_grid(screen, panel_x, panel_y_top, panel_width, panel_height, cell_size, columns, panel_y_bottom)

        points = []
        for i, y in enumerate(buffer):
            x = panel_x + i * (panel_width / buffer_len)
            py = baseline_y - y * amplitude
            points.append((x, py))
        if len(points) > 1:
            pygame.draw.aalines(screen, TRACE_COLOR, False, points)

        pygame.display.flip()

    sensor.stop()
    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()