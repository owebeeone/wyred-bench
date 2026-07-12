# Bench card — watchy_v1_bench

- Stamp: series A; locks external-interface=0, firmware-facing=0
- Ordering: power-off / continuity -> power-on rails -> current -> buses -> signals; then by check id.
- Every check appears exactly once. Record measurements in a `.measurements.json` and score them with `python3 -m wyred_bench.compare`.

## power-on rails

### 1. rail_3v3  (rail)

- Subject: rail +3V3
- Expected: 3.3 V, range [3.135, 3.465] V
- Probe: TP4 pad 1 (net +3V3); ground TP5 pad 1 (net GND)
- Instrument: DMM DC volts on TP4 referenced to TP5
- Provenance: declared by rail_3v3; derived from (none)

## current

### 2. batt_current  (current)

- Subject: current +BATT
- Expected: <= 150 mA (state 'active')
- Probe: no test point — probe method (series ammeter / supply readout) is a bench-card matter
- Instrument: series ammeter / shunt on the +BATT rail; put the board in state 'active'
- Provenance: declared by batt_current; derived from (none)

## buses

### 3. i2c_accel  (i2c_scan)

- Subject: i2c_scan I2C0
- Expected: addresses {0x18} (exact set)
- Probe: TP6 pad 1 (net I2C0_SCL); TP7 pad 1 (net I2C0_SDA)
- Instrument: I2C scan on I2C0 [TP6 (I2C0_SCL), TP7 (I2C0_SDA)]; expect an ACK from each listed address
- Provenance: declared by i2c_accel; derived from (none)

## signals

### 4. prog_signal  (signal)

- Subject: signal debug.prog
- Expected: freq 115200 Hz, range [112896, 117504] Hz
- Probe: TP1 pad 1 (net debug.prog.tx); TP2 pad 1 (net debug.prog.rx)
- Instrument: oscilloscope on TP1 (net debug.prog.tx); measure frequency and duty
- Provenance: declared by prog_signal; derived from (none)
