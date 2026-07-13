# The `selftest` CLI — `python3 -m wyred_bench.selftest`

Generates two firmware self-test **stubs** — a C module and a MicroPython-style
module — plus a machine-readable `NOT_IMPLEMENTED` manifest, from a derived
`.testplan.json` and the frozen `.pinmap.json` it was derived against. The stubs
iterate the testplan's checks and write the **same** `.measurements.json` shape
the [`compare` CLI](compare.md) scores: one oracle, two probe routes (bench DMM
vs on-board firmware).

Honesty: hardware access is emitted as **abstract hooks** (`adc_read_mv`,
`i2c_scan`, `read_current_ma`, `measure_signal`, `enter_state`,
`read_board_serial`). Anything not derivable from the artifacts — the ADC
channel-to-pad mapping, the I2C peripheral index, the capture method — is left
abstract and enumerated in the `NOT_IMPLEMENTED` manifest. **The generator never
fabricates a register map.** Probe points are cross-checked against the pinmap's
realized `test_point` components; a probe the board does not carry is refused
(`SELFTEST_UNPROBEABLE`, fail-closed).

## Synopsis

```text
python3 -m wyred_bench.selftest --testplan T.testplan.json --pinmap T.pinmap.json (--out-dir DIR | --target c|micropython|manifest)
```

## Flags

| flag | required | type | meaning |
|---|---|---|---|
| `--testplan` | yes | path | the `<name>.testplan.json` |
| `--pinmap` | yes | path | the `<name>.pinmap.json` the testplan was derived against (probe grounding, fail-closed) |
| `--out-dir` | no | path | write `<name>.selftest.{c,py,NOT_IMPLEMENTED.json}` here |
| `--target` | no | `c` \| `micropython` \| `manifest` | print one artifact to stdout instead of writing the set |

All four flags are greppable in the source:
`grep -n add_argument wyred-bench/src/wyred_bench/selftest.py`. Pass either
`--out-dir` or `--target`; with neither, the tool reports "nothing to do" and
exits 2.

## Exit codes

| exit | meaning |
|---|---|
| 0 | stubs generated |
| 2 | setup error — unreadable input, an unprobeable check (`SELFTEST_UNPROBEABLE`), an unknown check kind, or neither `--out-dir` nor `--target` given |

## The NOT_IMPLEMENTED manifest

Print the manifest for the committed watchy example — its testplan lives in the
bench fixtures, its pinmap in the contract goldens. The manifest enumerates
every abstract hook and unresolved parameter:

<!-- pythonpath: wyred-bench/src -->
<!-- cwd: . -->
```console
$ python3 -m wyred_bench.selftest --testplan wyred-bench/tests/fixtures/watchy_v1_bench.testplan.json --pinmap wyred-contract/goldens/ga019/watchy_v1.pinmap.json --target manifest
# expect: wyred_bench.selftest
# expect: adc_read_mv
```

## The C stub

The same derivation, emitted as a C module whose `wb_*` hooks are declared
`extern` for an integrator to provide:

<!-- pythonpath: wyred-bench/src -->
<!-- cwd: . -->
```console
$ python3 -m wyred_bench.selftest --testplan wyred-bench/tests/fixtures/watchy_v1_bench.testplan.json --pinmap wyred-contract/goldens/ga019/watchy_v1.pinmap.json --target c
# expect: wb_run_selftest
```

`--target micropython` emits the MicroPython module, and `--out-dir DIR` writes
the whole set (`.selftest.c`, `.selftest.py`, `.selftest.NOT_IMPLEMENTED.json`).
Whichever route, the stub's on-device output is a `.measurements.json` — see
[measurement records](measurement-records.md) for that shape and
[the `compare` CLI](compare.md) for scoring it.
