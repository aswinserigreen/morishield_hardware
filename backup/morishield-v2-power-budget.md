# Power Budget

## Assumptions
- Nominal input: 12 V; design electronics are evaluated at worst-case simultaneous radio/storage activity.
- 5 V module efficiency: 90%; 3.3 V buck: 90%; 3.8 V buck: 90%.
- External probes include SPS30 at 5 V and up to 300 mA aggregate on 3.3 V sensor connectors.
- GSM rail allows a 2.0 A burst with local low-ESR energy storage.
- External 12 V LED/buzzer loads are installation-dependent and are budgeted separately.

## Rail Loads
| Rail | Load | Typical | Peak |
|---|---:|---:|---:|
| 3.3 V | ESP32-S3 | 150 mA | 500 mA |
| 3.3 V | E22 LoRa | 20 mA | 140 mA |
| 3.3 V | SD card | 20 mA | 200 mA |
| 3.3 V | FDC/IMU/RTC/RS485/CP2102 | 35 mA | 90 mA |
| 3.3 V | external probes allowance | 100 mA | 300 mA |
| **3.3 V total** |  | **325 mA** | **1.23 A** |
| 5 V | SPS30 | 80 mA | 100 mA |
| 3.8 V | SIM7600G-H | 500 mA | 2.0 A burst |

## Reflected Source Current
- 3.3 V peak reflected to 5 V: `(3.3 × 1.23)/(5 × 0.90) = 0.90 A`.
- GSM peak reflected to 5 V: `(3.8 × 2.0)/(5 × 0.90) = 1.69 A`.
- Add SPS30 and margin: 5 V module peak requirement is approximately **2.8 A**.
- Reflected to 12 V through a 90% 12-to-5 V module: `(5 × 2.8)/(12 × 0.90) = 1.30 A` for board electronics.

## Sizing Decisions
- 5 V module: minimum 3 A continuous with thermal margin and low-resistance connectors.
- U10 3.3 V buck: 3 A-capable MP2315 implementation; inductor saturation rating should be at least 3.5 A despite the original 2 A suggestion.
- U11 GSM buck: TPS54331D 3 A; 4.7 µH inductor with at least 3.5 A saturation/current rating, low DCR; output ceramics plus 100 µF local SIM bulk.
- Input fuse: 3 A hold/fast-blow class. This supports approximately 1.3 A board-electronics peak plus limited 12 V external loads. Combined external continuous load should remain below roughly 1.0–1.2 A unless the fuse, reverse-protection FET, connector, module, and thermal design are upgraded.
- Reverse-polarity FET and J1: target at least 4 A electrical rating; verify SOT-23 thermal loss at final maximum load.
- USB debug path: current-limited by AP2152 and source advertisement; intended for programming/debug and light-load operation only, not guaranteed GSM bursts.
- Ceramic capacitance must be selected with DC-bias derating; populate enough nominal capacitance for at least twice the required effective value on switching-rail outputs.

## Validation Items for Layout
- Keep GSM regulator hot loop compact; wide VBAT copper and local capacitor bank at all VBAT pins.
- Validate U11 compensation and transient response on first articles.
- Confirm actual external-load current before production release; it is the dominant uncertainty in fuse/FET/connector thermal margin.
