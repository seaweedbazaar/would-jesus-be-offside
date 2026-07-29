"""
VL53L1X distance sensor reader.
Runs in its own background thread so the render loop never blocks on I2C timing.
"""

import time
import threading


class DistanceSensor:
    """Wraps the VL53L1X and exposes the latest distance (mm) thread-safely.

    If real hardware/library isn't available (e.g. testing on a laptop),
    pass simulate=True and it will fake a distance you can override with
    keyboard keys in the display test (see main.py).
    """

    def __init__(self, timing_budget_ms=50, distance_mode="long", simulate=False):
        self.simulate = simulate
        self.latest_mm = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._sim_override = None  # for manual testing without hardware

        if not simulate:
            import board
            import busio
            import adafruit_vl53l1x

            i2c = busio.I2C(board.SCL, board.SDA)
            self.vl53 = adafruit_vl53l1x.VL53L1X(i2c)
            # 1 = short (<1.3m, most immune to ambient light)
            # 2 = long  (<4m, better for a walk-up-to-the-installation distance)
            self.vl53.distance_mode = 1 if distance_mode == "short" else 2
            self.vl53.timing_budget = timing_budget_ms
            self.vl53.start_ranging()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        while self._running:
            if self.simulate:
                # default: nothing there (far away), stays perfectly idle
                # until the test harness explicitly moves it closer
                d = self._sim_override if self._sim_override is not None else 200.0
                with self._lock:
                    self.latest_mm = d * 10.0
                time.sleep(0.02)
            else:
                if self.vl53.data_ready:
                    d_cm = self.vl53.distance  # float cm, or None if out of range
                    with self._lock:
                        self.latest_mm = None if d_cm is None else d_cm * 10.0
                    self.vl53.clear_interrupt()
                time.sleep(0.01)

    def set_sim_distance_cm(self, value):
        """For keyboard-driven testing without hardware."""
        self._sim_override = value

    def read_mm(self):
        with self._lock:
            return self.latest_mm

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        if not self.simulate:
            self.vl53.stop_ranging()