# Minimal MicroPython driver for the AMS/TAOS TCS34725 RGBC color sensor
# Works on ESP32/ESP8266/RP2040 etc. using machine.I2C

from machine import I2C
import time

_DEFAULT_ADDR = 0x29

# Register addresses (with COMMAND bit 0x80 added by writer/reader)
_REG_ENABLE   = 0x00
_REG_ATIME    = 0x01
_REG_WTIME    = 0x03
_REG_AILTL    = 0x04  # ALS interrupt low thresh low byte
_REG_AILTH    = 0x05
_REG_AIHTL    = 0x06  # ALS interrupt high thresh low byte
_REG_AIHTH    = 0x07
_REG_PERS     = 0x0C  # Interrupt persistence
_REG_CONFIG   = 0x0D
_REG_CONTROL  = 0x0F  # Gain
_REG_ID       = 0x12
_REG_STATUS   = 0x13
_REG_CDATAL   = 0x14  # Clear channel, then R,G,B (16-bit each, LSB first)
# R: 0x16/0x17, G: 0x18/0x19, B: 0x1A/0x1B

# ENABLE bits
_ENABLE_PON = 0x01  # Power on
_ENABLE_AEN = 0x02  # RGBC enable
_ENABLE_AIEN = 0x10 # ALS interrupt enable

# COMMAND bit
_CMD = 0x80

# Integration times (ATIME). Key presets from the datasheet/common libs.
# ATIME = 0xFF -> ~2.4ms; 0xF6 -> 24ms; 0xEB -> 50ms; 0xD5 -> 101ms
# 0xC0 -> 154ms; 0x00 -> 700ms
INTEGRATION_2_4MS  = 0xFF
INTEGRATION_24MS   = 0xF6
INTEGRATION_50MS   = 0xEB
INTEGRATION_101MS  = 0xD5
INTEGRATION_154MS  = 0xC0
INTEGRATION_700MS  = 0x00

# Map ATIME to approx milliseconds for convenience/delays
_ATIME_TO_MS = {
    INTEGRATION_2_4MS:  2.4,
    INTEGRATION_24MS:   24.0,
    INTEGRATION_50MS:   50.0,
    INTEGRATION_101MS:  101.0,
    INTEGRATION_154MS:  154.0,
    INTEGRATION_700MS:  700.0,
}

# Gain settings (CONTROL register)
GAIN_1X   = 0x00
GAIN_4X   = 0x01
GAIN_16X  = 0x02
GAIN_60X  = 0x03

_GAIN_MULT = {
    GAIN_1X: 1.0,
    GAIN_4X: 4.0,
    GAIN_16X: 16.0,
    GAIN_60X: 60.0,
}

class TCS34725:
    def __init__(self, i2c: I2C, addr: int = _DEFAULT_ADDR,
                 integration: int = INTEGRATION_154MS, gain: int = GAIN_4X,
                 auto_enable: bool = True):
        """
        i2c: machine.I2C instance
        addr: I2C address (default 0x29)
        integration: one of INTEGRATION_* constants
        gain: one of GAIN_* constants
        auto_enable: if True, power-on + enable RGBC automatically
        """
        self.i2c = i2c
        self.addr = addr
        self.integration = integration
        self.gain = self._normalize_gain_input(gain)
        self.rgb_gains = (1.0, 1.0, 1.0)
        self.presence_threshold = None
        self.presence_hysteresis = 0.9  # when present, allow C to drop to 90% of threshold before switching to none
        self._present = False
        self._ambient_baseline = None
        self._ambient_rgba = None

        # Verify sensor ID (common IDs: 0x44, 0x4D; some variants differ)
        sid = self._read_u8(_REG_ID)
        # Not throwing if unexpected, but you can assert if desired:
        # if sid not in (0x44, 0x4D):
        #     raise RuntimeError("Unexpected TCS34725 ID: 0x%02X" % sid)

        self.set_integration_time(self.integration)
        self.set_gain(self.gain)

        if auto_enable:
            self.enable()

    # ---------- Low-level I2C helpers ----------

    def _write_u8(self, reg: int, val: int):
        self.i2c.writeto_mem(self.addr, _CMD | reg, bytes((val & 0xFF,)))

    def _write_u16(self, reg: int, val: int):
        # LSB first
        self.i2c.writeto_mem(self.addr, _CMD | reg, bytes((val & 0xFF, (val >> 8) & 0xFF)))

    def _read_u8(self, reg: int) -> int:
        return self.i2c.readfrom_mem(self.addr, _CMD | reg, 1)[0]

    def _read_block(self, reg: int, n: int) -> bytes:
        return self.i2c.readfrom_mem(self.addr, _CMD | reg, n)

    # ---------- Configuration ----------

    def _normalize_gain_input(self, gain_val):
        # Accept enum codes (0..3) or numeric multipliers (1,4,16,60)
        if gain_val in (GAIN_1X, GAIN_4X, GAIN_16X, GAIN_60X):
            return gain_val
        if gain_val in (1, 1.0):
            return GAIN_1X
        if gain_val in (4, 4.0):
            return GAIN_4X
        if gain_val in (16, 16.0):
            return GAIN_16X
        if gain_val in (60, 60.0):
            return GAIN_60X
        raise ValueError("Unsupported gain value: {}".format(gain_val))

    def enable(self):
        # Power on, short delay, then enable RGBC
        en = self._read_u8(_REG_ENABLE)
        self._write_u8(_REG_ENABLE, en | _ENABLE_PON)
        time.sleep_ms(3)
        en = self._read_u8(_REG_ENABLE)
        self._write_u8(_REG_ENABLE, en | _ENABLE_AEN)

    def disable(self):
        en = self._read_u8(_REG_ENABLE)
        self._write_u8(_REG_ENABLE, en & ~( _ENABLE_AEN | _ENABLE_PON ))

    def set_integration_time(self, atime: int):
        if atime not in _ATIME_TO_MS:
            raise ValueError("Unsupported integration time (ATIME 0x%02X)" % atime)
        self.integration = atime
        self._write_u8(_REG_ATIME, atime)

    def set_gain(self, gain: int):
        g = self._normalize_gain_input(gain)
        self.gain = g
        self._write_u8(_REG_CONTROL, g)

    def get_gain(self) -> int:
        return self.gain

    def print_gain(self):
        gm = {GAIN_1X: "1x", GAIN_4X: "4x", GAIN_16X: "16x", GAIN_60X: "60x"}
        print("Gain:", gm.get(self.gain, hex(self.gain)))

    def set_interrupts(self, enable: bool, low_thresh: int = None, high_thresh: int = None, persistence: int = 0x01):
        """
        Enable/disable ALS interrupt and optionally set thresholds/persistence.
        Thresholds are 16-bit (0..65535) on the CLEAR channel.
        persistence: number of consecutive out-of-range readings before asserting
                     (see datasheet; 0x01 = every RGBC cycle).
        """
        if enable:
            if low_thresh is not None:
                self._write_u16(_REG_AILTL, low_thresh)
            if high_thresh is not None:
                self._write_u16(_REG_AIHTL, high_thresh)
            self._write_u8(_REG_PERS, persistence & 0x0F)
            en = self._read_u8(_REG_ENABLE)
            self._write_u8(_REG_ENABLE, en | _ENABLE_AIEN)
        else:
            en = self._read_u8(_REG_ENABLE)
            self._write_u8(_REG_ENABLE, en & ~_ENABLE_AIEN)

    # ---------- Reading ----------

    def valid(self) -> bool:
        """True if RGBC data is valid (AVALID set)."""
        status = self._read_u8(_REG_STATUS)
        return bool(status & 0x01)

    def read_raw(self):
        """
        Read a full RGBC sample (blocking until one integration period elapsed).
        Returns: (c, r, g, b) as 16-bit integers.
        """
        # Wait at least one full integration period for new data.
        # Add a small margin (2ms) to be safe.
        ms = _ATIME_TO_MS[self.integration]
        time.sleep_ms(int(ms) + 3)

        # Optionally you can poll STATUS for AVALID; we just delay.
        buf = self._read_block(_REG_CDATAL, 8)
        c = buf[0] | (buf[1] << 8)
        r = buf[2] | (buf[3] << 8)
        g = buf[4] | (buf[5] << 8)
        b = buf[6] | (buf[7] << 8)
        return c, r, g, b

    def read_rgb8(self, apply_white_balance: bool = True):
        c, r, g, b = self.read_raw()
        if c <= 0:
            return 0, 0, 0
        rn = r / c
        gn = g / c
        bn = b / c
        if apply_white_balance and self.rgb_gains:
            rg, gg, bg = self.rgb_gains
            rn *= rg
            gn *= gg
            bn *= bg
        rn = max(0.0, min(1.0, rn))
        gn = max(0.0, min(1.0, gn))
        bn = max(0.0, min(1.0, bn))
        return int(rn * 255 + 0.5), int(gn * 255 + 0.5), int(bn * 255 + 0.5)

    def _rgb8_from_raw(self, c: int, r: int, g: int, b: int, apply_white_balance: bool = True):
        if c <= 0:
            return 0, 0, 0
        rn = r / c
        gn = g / c
        bn = b / c
        if apply_white_balance and self.rgb_gains:
            rg, gg, bg = self.rgb_gains
            rn *= rg
            gn *= gg
            bn *= bg
        rn = max(0.0, min(1.0, rn))
        gn = max(0.0, min(1.0, gn))
        bn = max(0.0, min(1.0, bn))
        return int(rn * 255 + 0.5), int(gn * 255 + 0.5), int(bn * 255 + 0.5)

    # ---------- Convenience computations (approximate) ----------

    def _subtract_ambient(self, c, r, g, b):
        a = getattr(self, "_ambient_rgba", None)
        if not a:
            return c, r, g, b
        c0,r0,g0,b0 = a
        # clamp to zero to avoid negatives
        return max(0,c-c0), max(0,r-r0), max(0,g-g0), max(0,b-b0)
    
    def integration_ms(self) -> float:
        return _ATIME_TO_MS[self.integration]

    def gain_multiplier(self) -> float:
        return _GAIN_MULT[self.gain]

    def _cpl(self, glass_attenuation: float = 1.0) -> float:
        """
        Counts-per-lux scaling factor.
        CPL ≈ (integration_ms * gain) / (60 * GA)
        60 is a common normalization constant from app notes; GA is glass attenuation.
        """
        return (self.integration_ms() * self.gain_multiplier()) / (60.0 * glass_attenuation)

    def lux(self, glass_attenuation: float = 1.0) -> float:
        """
        Approximate lux based on DN40-style coefficients.
        LUX ≈ (0.136*R + 1.000*G - 0.444*B) / CPL
        """
        c, r, g, b = self.read_raw()
        cpl = self._cpl(glass_attenuation)
        if cpl <= 0:
            return 0.0
        # Coefficients are generic; tune for your optical path.
        return max(0.0, (0.136 * r + 1.000 * g - 0.444 * b) / cpl)

    def color_temperature(self) -> int:
        """
        Approximate CCT (Kelvin) using a simple ratio method:
        CCT ≈ 3810 * (B / R) + 1391  (very rough!)
        For better accuracy, implement full IR-comp and CIE xy → CCT mapping with calibration.
        """
        _, r, g, b = self.read_raw()
        if r == 0:
            return 0
        cct = int(3810.0 * (b / (r + 1e-9)) + 1391.0)
        return max(0, cct)

    def normalized_rgb(self):
        """
        Return (rn, gn, bn) normalized to clear channel (0..1).
        Guarded to avoid division-by-zero and clip to [0,1].
        """
        c, r, g, b = self.read_raw()
        if c == 0:
            return (0.0, 0.0, 0.0)
        rn = min(1.0, r / c)
        gn = min(1.0, g / c)
        bn = min(1.0, b / c)
        return (rn, gn, bn)

    def set_rgb_gains(self, rgb_gains):
        if not isinstance(rgb_gains, (list, tuple)) or len(rgb_gains) != 3:
            raise ValueError("rgb_gains must be a 3-tuple")
        self.rgb_gains = (float(rgb_gains[0]), float(rgb_gains[1]), float(rgb_gains[2]))

    def _median(self, arr):
        n = len(arr)
        if n == 0:
            return 0
        s = sorted(arr)
        m = n // 2
        if n % 2 == 1:
            return s[m]
        return (s[m-1] + s[m]) // 2

    def measure_ambient_clear(self, samples: int = 10, method: str = "mean", percentile: float = 0.8) -> int:
        vals = []
        n = max(1, samples)
        for _ in range(n):
            c, _, _, _ = self.read_raw()
            vals.append(int(c))
        if method == "median":
            return int(self._median(vals))
        if method == "percentile":
            if not vals:
                return 0
            s = sorted(vals)
            p = percentile
            if p < 0.0:
                p = 0.0
            if p > 1.0:
                p = 1.0
            idx = int(p * (len(s) - 1) + 0.5)
            return int(s[idx])
        total = 0
        for v in vals:
            total += v
        return total // n


    def auto_calibrate(self, white_samples: int = 5, target_min: int = 8000, target_max: int = 40000):
        best_gain = GAIN_1X
        best_c = -1
        for gsel in (GAIN_1X, GAIN_4X, GAIN_16X, GAIN_60X):
            self.set_gain(gsel)
            total = 0
            saturated = False
            for _ in range(max(1, white_samples)):
                c, r, g, b = self.read_raw()
                if c >= 65500:
                    saturated = True
                total += c
            avg_c = total // max(1, white_samples)
            if not saturated and target_min <= avg_c <= target_max:
                best_gain = gsel
                best_c = avg_c
                break
            if not saturated and avg_c > best_c:
                best_gain = gsel
                best_c = avg_c
        self.set_gain(best_gain)
        rs = 0
        gs = 0
        bs = 0
        cs = 0
        n = max(1, white_samples)
        for _ in range(n):
            c, r, g, b = self.read_raw()
            rs += r
            gs += g
            bs += b
            cs += c
        rs //= n
        gs //= n
        bs //= n
        cs //= n
        if cs <= 0:
            self.rgb_gains = (1.0, 1.0, 1.0)
        else:
            rn = rs / cs
            gn = gs / cs
            bn = bs / cs
            avg = (rn + gn + bn) / 3.0
            rg = avg / rn if rn > 0 else 1.0
            gg = avg / gn if gn > 0 else 1.0
            bg = avg / bn if bn > 0 else 1.0
            self.rgb_gains = (rg, gg, bg)
        self.print_gain()
        return self.gain, self.rgb_gains

    @staticmethod
    def hsv_from_rgb(r, g, b):
        r_ = r / 255.0
        g_ = g / 255.0
        b_ = b / 255.0
        mx = r_ if r_ >= g_ and r_ >= b_ else (g_ if g_ >= b_ else b_)
        mn = r_ if r_ <= g_ and r_ <= b_ else (g_ if g_ <= b_ else b_)
        d = mx - mn
        if d == 0:
            h = 0.0
        elif mx == r_:
            h = (60.0 * ((g_ - b_) / d) + 360.0) % 360.0
        elif mx == g_:
            h = 60.0 * ((b_ - r_) / d) + 120.0
        else:
            h = 60.0 * ((r_ - g_) / d) + 240.0
        s = 0.0 if mx == 0.0 else d / mx
        v = mx
        return h, s, v

    
    def get_hsv_rgb(self, c: int, r: int, g: int, b: int, presence_threshold: int = None):
        c1, r1, g1, b1 = self._subtract_ambient(c, r, g, b)
        r8,g8,b8 = self._rgb8_from_raw(c1, r1, g1, b1, apply_white_balance=True)
        h,s,v = TCS34725.hsv_from_rgb(r8, g8, b8)
        return (h, s, v), (r8, g8, b8)
    

    # ---------- Utility ----------

    def id(self) -> int:
        """Return sensor ID register."""
        return self._read_u8(_REG_ID)

    def status(self) -> int:
        """Return STATUS register."""
        return self._read_u8(_REG_STATUS)

def device_present(i2c: I2C, addr: int = _DEFAULT_ADDR) -> bool:
    try:
        _ = i2c.readfrom_mem(addr, _CMD | _REG_ID, 1)
        return True
    except Exception:
        return False
