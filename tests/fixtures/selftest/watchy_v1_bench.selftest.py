"""watchy_v1_bench.selftest.py -- GENERATED firmware self-test stub (MicroPython).

Iterates every testplan check, calls the abstract hardware hooks on the
injected ``hooks`` object, and returns a .measurements.json-shaped
record that wyred_bench.compare scores. DO NOT EDIT BY HAND -- regenerate.

NOT IMPLEMENTED (see watchy_v1_bench.selftest.NOT_IMPLEMENTED.json): every method on
``Hooks`` is abstract. Subclass it for the target board; nothing here
fabricates a register map.
"""

try:
    import ujson as json
except ImportError:
    import json

ARTIFACT = "watchy_v1_bench"
# Embedded verbatim so the record stamp matches the testplan's own
# stamp (else wyred_bench.compare refuses the measurement as stale).
STAMP = json.loads('{"locks":{"external-interface":0,"firmware-facing":0},"series":"A"}')
# Per-rail ADC channel is NOT derivable; sentinel until an integrator
# fills it in. TODO (channel-to-pad mapping, NOT IMPLEMENTED):
#   check rail_3v3 -> ADC channel for net +3V3 (test point TP4)
ADC_CHANNEL_UNSET = None


class Hooks(object):
    """Abstract hardware access. Subclass and implement each method for
    the target MCU; every method here is in the NOT_IMPLEMENTED manifest.
    """

    def enter_state(self, state):
        raise NotImplementedError("NOT_IMPLEMENTED: enter_state")

    def read_board_serial(self):
        raise NotImplementedError("NOT_IMPLEMENTED: read_board_serial")

    def adc_read_mv(self, check_id, channel):
        raise NotImplementedError("NOT_IMPLEMENTED: adc_read_mv")

    def read_current_ma(self, check_id, rail, state):
        raise NotImplementedError("NOT_IMPLEMENTED: read_current_ma")

    def i2c_scan(self, check_id, bus):
        raise NotImplementedError("NOT_IMPLEMENTED: i2c_scan")

    def measure_signal(self, check_id, tp):
        raise NotImplementedError("NOT_IMPLEMENTED: measure_signal")


def run_selftest(hooks):
    """Run every check via ``hooks`` and return the measurement record
    dict (the .measurements.json shape wyred_bench.compare scores)."""
    results = {}

    # [power-on rails] check rail_3v3 (rail) subject +3V3
    # declared by rail_3v3; derived from (none)
    cid = "rail_3v3"
    mv = hooks.adc_read_mv(cid, ADC_CHANNEL_UNSET)
    results[cid] = {"unit": "V", "value": mv / 1000.0}

    # [current] check batt_current (current) subject +BATT
    # declared by batt_current; derived from (none)
    cid = "batt_current"
    hooks.enter_state('active')
    ma = hooks.read_current_ma(cid, '+BATT', 'active')
    results[cid] = {"state": 'active', "unit": "mA", "value": ma}

    # [buses] check i2c_accel (i2c_scan) subject I2C0
    # declared by i2c_accel; derived from (none)
    cid = "i2c_accel"
    addrs = hooks.i2c_scan(cid, 'I2C0')
    results[cid] = {"addrs": [int(_a) for _a in addrs]}

    # [signals] check prog_signal (signal) subject debug.prog
    # declared by prog_signal; derived from (none)
    cid = "prog_signal"
    sig = hooks.measure_signal(cid, 'debug.prog.tx')
    results[cid] = {"values": {"freq": sig['freq']}}

    return {
        "artifact": ARTIFACT,
        "board_serial": hooks.read_board_serial(),
        "results": results,
        "testplan_stamp": STAMP,
    }


def main(argv=None):
    """Abstract-hook default run: prints the record as JSON. A real
    integrator calls run_selftest(MyHooks()) on-device instead."""
    import sys
    record = run_selftest(Hooks())
    sys.stdout.write(json.dumps(record))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
