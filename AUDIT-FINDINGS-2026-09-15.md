# MoriShield V2 — Deep Hardware Audit Findings

**Date:** 2026-09-15
**Files audited:**
- `aswindatha-morishield-v2.edif` (schematic netlist, 1816 lines)
- `morishield-v2.ipc2581c` (PCB manufacturing data, 271,981 lines)
- `aswindatha-morishield-v2-BOM-*/` (8 manufacturer BOM exports)
- `morishield-v2-project-specification.md`
- `morishield-v2-power-budget.md`
- Reference: `FLUX_SCHEMATIC_PROMPT.md` + `FLUX_PCB_PROMPT.md` (design briefs)

**Overall completion: ~85%** — schematic captured, layout exists, BOM exported. But the GSM and IMU subsystems are **completely unwired**, and several parts are wrong. **DO NOT order PCBs until these are fixed.**

---

## 🔴 CRITICAL — Blocking Issues (fix before any manufacturing)

### C1. SIM7600G (U3) is COMPLETELY UNWIRED — the entire GSM subsystem has zero connections

The EDIF netlist contains the U3 instance (line 741) and full 135-pin cell definition, but **no net in the entire netlist references any U3 pin**. Verified missing:

| Subsystem | Components | Status |
|-----------|-----------|--------|
| U3 VBAT (pins 38/39/62/63) | `3V8_SIM_RAIL` net exists but only connects L1, C1, C30 | **U3 not on the net** |
| U3 TXD/RXD | U9 (TXU0202) A1/B1Y/A2Y/B2 | **No signal connections** |
| U3 PWRKEY | Q4, R16, R17, R33 (R_PK) | **No nets at all** |
| SIM card | J14, R20, R21, R22, D14 | **No nets at all** |
| NETLIGHT | D13, R29 | **No nets at all** |
| Antenna | MAIN_ANT → J12 | **No net** |
| UART2 SIM jumpers | R31 P2, R32 P2 | **Dangling** (P1 connected to GPIO 39/40, P2 to nothing) |

In the IPC-2581C, U3's pads are in a `<Set>` with **no net attribute** (line 232678) — confirming unconnected pads. The SIM7600G is placed on the board at (165.95, -133.17) but wired to nothing.

**Impact:** Master variant would have no LTE, no SIM, no power to the module. The 3.8V rail, 1.8V LDO, ferrite bead, and tantalum cap are all built but terminate at nothing.

### C2. MPU6500 (IC1) is COMPLETELY UNWIRED

IC1 is placed at (278.46, -118.94) but its pins are on **auto-generated nets** `Net 1` through `Net 10` — not on `I2C3_SDA`, `I2C3_SCL`, `3V3_RAIL`, or `GND`. The EDIF netlist has **zero references to IC1**.

**Impact:** No accelerometer/IMU — fall detection, theft/tamper alert, and orientation check all dead.

### C3. Duplicate components created during capture

The IPC file contains **8 duplicate instances** with `_1` suffix, placed near IC1:

| Duplicate | Original | Location |
|-----------|----------|----------|
| C1_1, C2_1, C3_1 | C1, C2, C3 | (278.7, -122.7), (282.5, -122.7), (281.2, -122.7) |
| R1_1, R2_1, R3_1, R4_1, R5_1 | R1–R5 | (277.4, -122.7) … (276.6, -115.1) |

These look like an attempt to add MPU6500 support components (decoupling, pull-ups) that created **new instances instead of wiring the existing ones**. The BOM export then shows **C1/C2/C3 in three different BOM lines with three different values** (100µF, 47µF, 0.1µF) — a BOM conflict that will break procurement.

### C4. Board outline does not cover the component placement

The IPC-2581C `Profile` polygon defines a board of **160 × 100 mm** (x: 10–170, y: −110 to −10). But placed components span **x: 10–434, y: −357 to −117**:

| Component | X | Y | Inside outline? |
|-----------|-----|------|-----------------|
| U3 SIM7600G | 165.9 | −133.2 | ❌ (y outside) |
| U1 ESP32-S3 | ~278 | ~−119 | ❌ |
| IC1 MPU6500 | 278.5 | −118.9 | ❌ |
| J14 SIM socket | 60.9 | −168.3 | ❌ |
| Q4 | 11.6 | −120.5 | ❌ |
| J16 RS485 | 430.6 | −249.7 | ❌ |

Either the outline is wrong/placeholder, or components are placed off-board. **Must be verified in Flux before layout can be trusted.**

### C5. U12 is a generic multi-output buck module — NOT the HW-187

Netlist cell: `DC-DC Multi-output Buck Converter (3.3V/5V/9V/12V)` with 8 ports (+IN, −IN, +OUT, −OUT, +OUT_2, −OUT_2, +OUT_3, −OUT_3). The brief specifies **HW-187 (12V→5V, 3A, single output)**. The BOM role says *"Library module substitute for unavailable HW-187; configure 5V output"* — but a multi-output module is a different physical part with different current capability per output. **The 5V rail peak requirement is 2.8A** (per power budget) — verify the substitute module can deliver this on a single output.

### C6. ESD arrays D3–D8 are ALL USBLC6-2SC6 — wrong parts for I2C/UART

| Ref | Brief specifies | Flux used | Function |
|-----|----------------|-----------|----------|
| D2 | USBLC6-2SC6 | USBLC6-2SC6 ✓ | USB-C D+/D− |
| D3, D4 | **ESDA6V8-2U2** | USBLC6-2SC6 ❌ | I2C Bus1 ESD (J2, J3) |
| D5 | **ESDA6V8-2U2** | USBLC6-2SC6 ❌ | I2C Bus2 ESD (J4) |
| D6 | **ESDA6V8-2U2** | USBLC6-2SC6 ❌ | I2C Bus3 ESD (J7) |
| D7 | **ESDA6V8-1U2** | USBLC6-2SC6 ❌ | SPS30 UART ESD (J5) |
| D8 | **ESDA6V8-1U2** | USBLC6-2SC6 ❌ | Wind speed ESD (J7) |

USBLC6-2SC6 is a USB-specific 6-pin array (I/O1, I/O2, VBUS, GND). Its VBUS pin is wired to 3V3_RAIL in this design (netlist lines 1385–1390) — not its intended use. The brief's ESDA6V8-2U2/1U2 are the correct parts for I2C/UART line protection.

### C7. L1 is a 1nH inductor — should be a 600Ω ferrite bead

BOM: `L1 | Inductor, 1nH | Power Filtering | DNF (Slave); ferrite 600Ω@100MHz 2A`. The role text knows it should be a ferrite bead, but the part is a 1nH inductor. A 1nH inductor at 900MHz is ~5.6Ω — useless as a VBAT noise filter. **Must be a ferrite bead (600Ω@100MHz, 2A).**

### C8. C1/C2 are "100µF non-polarized, SMD 0603" — physically wrong

A 100µF ceramic in 0603 has ~90% DC-bias derating at rated voltage — effective capacitance would be ~10µF. The brief requires:
- **C1**: 100µF tantalum, 10V, ESR ≈ 0.7Ω (SIM7600G VBAT bulk, per SIMCom datasheet) — needs C-case/D-case or 1210/1206 ceramic
- **C2**: 100µF electrolytic, **35V** (12V input bulk, solar can exceed 25V)

### C9. J1 (12V input) is a JST-XH 2-pin — should be a Phoenix 3.81mm screw terminal

BOM: `J1,J10,J16,J8,J9 | B2B-XH-A(LF)(SN)` — J1, J16 (RS485), J8/J9/J10 (LEDs/buzzer) are ALL the same JST-XH 2-pin. The brief specifies:
- J1: **Phoenix Contact MC 2-pin, 3.81mm screw terminal** (field wiring for 12V solar/battery)
- J16: RS485 terminal (screw terminal or JST-XH acceptable per brief)

The BOM role admits: *"Library 2-pin connector placeholder; exact 3.81mm Phoenix unavailable"*. A JST-XH is not rated for repeated field wiring of a 12V supply and is a poor choice for the main power input.

---

## 🟠 MAJOR — Should Fix Before Production

### M1. Board is 4-layer — brief specifies 2-layer

IPC stackup: F.Cu / In1.Cu / In2.Cu / B.Cu + 3 dielectrics. The brief says *"Layers: 2 | User preference, bottom = solid GND plane"*. 4-layer is electrically better but costs more. **Confirm this was intentional or revert to 2-layer.**

### M2. MPU6500 designator is IC1, not U5

Firmware documentation references U5. Cosmetic but causes confusion across docs/BOM/firmware.

### M3. R50 — extra 0Ω jumper not in the brief

BOM line: `R31,R32,R33,R34,R35,R50` (6 jumpers). Brief specifies exactly 5 (R31–R35). R50's role is *"GSM antenna series"* — this is the π-match series element, which is legitimate, but it should be documented as a matching placeholder (like C44/C45), not a variant jumper.

### M4. F1 polyfuse is 24V-rated — TVS clamps at 33V

`SMDC300F/24-2` = 3A hold, **24V max**. The SMBJ33A TVS allows transients up to ~33V before clamping. A 24V-rated fuse on a 12V solar input that can see 22V open-circuit + transients is marginal. Polyfuses are self-resetting so failure mode is less severe, but a **30V+ rated fuse** is safer.

### M5. Q5 BOM metadata says "N-channel MOSFET" — AO3401A is P-channel

BOM line 37: `"30V","5A at 25°CA","N-channel MOSFET"` for Q5. The part (AO3401A) is correct (P-channel, −30V, −4A), but the metadata is wrong and could mislead procurement.

### M6. J5 (SPS30) is 5-pin — brief specifies 4-pin JST-GH

J5 uses BM05B-GHS-TBT (5-pin) but only 4 pins are used (5V, GND, TX, RX). The brief specifies BM04B (4-pin). Minor — a 5-pin connector works with a 4-pin cable, but the mating cable must be 5-pin.

### M7. Missing LCSC/JLCPCB part numbers for critical parts

| Part | LCSC # |
|------|--------|
| ESP32-S3-WROOM-1-N16R8 (U1) | ❌ blank |
| SIM7600G-H R2 (U3) | ❌ blank |
| MPU-6500 (IC1) | ❌ blank |
| TXU0202 (U9) | ❌ blank |
| MP2315 (U10) | ❌ blank |
| U12 (buck module) | ❌ blank |
| L1, L2, L3 | ❌ blank |
| C1–C45 (most) | ❌ blank |
| D11, D12, D13, D14 | ❌ blank |
| F1, BT1, SW1/SW2, J11–J15 | ❌ blank |

Only D1, D2–D8, D9, D10, D15, D16, U2, U4, U6, U7, U8, U11, U13, U14, J1–J10, Q1–Q7 have LCSC numbers. **The JLCPCB BOM cannot be ordered as-is.**

### M8. U11 COMP network marked "provisional"

BOM: `R48 | 29.4kΩ | U11 COMP provisional`. The TPS54331D compensation (R48/C28/C29) needs to be validated — the power budget also flags *"Validate U11 compensation and transient response on first articles."* Acceptable for now, but flag it.

---

## 🟡 DOCUMENTED DEVIATIONS — Need Your Approval

These were deliberately changed by Flux.ai and documented in the project spec. Review and approve or reject:

| # | Brief | Flux used | Assessment |
|---|-------|-----------|------------|
| D1 | TXB0108 (auto-direction) | **TXU0202DTTR** (fixed-direction, 2-ch) | ✅ **Reasonable** — UART has known direction; TXB auto-direction is vulnerable to edge/loading problems. TXU0202 is a valid TI part. |
| D2 | SMAJ6.5CA (2-terminal TVS) | **SM712** (3-terminal A/B-to-GND) | ✅ **Better** — SM712 is the industry-standard RS485 protector; doesn't short A to B. |
| D3 | ESDA6V8-4U2 (SIM ESD) | **ESDA6V1BC6** | ⚠️ Verify — ESDA6V1BC6 is a 4-line array (6-pin) with 6.1V standoff vs 6.8V. Functionally similar; check clamping vs SIM voltage levels (1.8V/3V). |
| D4 | MP2315 (2A) for 3.8V rail | **TPS54331D (3A)** | ✅ **Better** — matches the power budget's 2A burst requirement with margin. |
| D5 | HW-187 module | Generic multi-output buck | ❌ **Problem** — see C5. Not an approved alternate. |
| D6 | J1 Phoenix screw terminal | JST-XH 2-pin | ❌ **Problem** — see C9. |
| D7 | DS3231 "SOIC-8" (brief error) | **DS3231S 16-pin SOIC** | ✅ **Correct** — the real DS3231 is 16-pin; the 8-pin DS3231M is a different (less accurate) part. Flux caught a brief error. |
| D8 | AP2152 SOT-23-5 | **AP2152SG-13 SOIC-8** | ✅ Acceptable — same IC, dual-channel package, one channel used. |
| D9 | D16 bootstrap diode | Added 1N4148WS for MP2315 BST | ✅ **Good practice** — needed for high-duty-cycle 5V→3.3V conversion. |
| D10 | C44/C45 0pF | GSM antenna π-match placeholders | ✅ Correct intent. |
| D11 | J5 4-pin | 5-pin BM05B | ⚠️ Minor — see M6. |

---

## ✅ VERIFIED CORRECT — Audit Corrections Were Applied

The following corrections from the 2026-09-14 audit are confirmed present in the netlist:

| Correction | Verified in netlist |
|------------|-------------------|
| MP2315 FB divider R1=40.2K/R2=12.7K | `U10_FB`: R43 (40.2K) + R44 (12.7K) ✓ |
| TPS54331D 3A for GSM rail | U11 = TPS54331D, VSENSE divider R46 (37.4K) + R47 ✓ |
| U13 AP2127K-1.8 dedicated 1.8V LDO | `1V8_RAIL`: U13 VOUT → U9 VCCA + OE ✓ |
| U14 AP2152 + D15 SS54 reverse blocking | `USB_DEBUG_5V`: U14 OUT → D15 A → K → 5V_RAIL ✓ |
| Q6/Q7 auto-program (Espressif topology) | DTR→R40→Q6→EN; RTS→R41→Q7→GPIO0 ✓ |
| Low-side MOSFET outputs | `12V_RAIL` → J8.1/J9.1/J10.1; drain → J8.2/J9.2/J10.2 ✓ |
| DS3231S 16-pin (real TCXO RTC) | U6 = DS3231S#T&R, SOIC-16 ✓ |
| CP2102N RST pull-up + VIO | `CP2102_RST`: R42 + C41; VIO → 3V3_RAIL ✓ |
| GPIO 19/20 NC (native USB unused) | No nets on IO19/IO20 ✓ |
| E22 pin 12+15 NRST tied | `LORA_NRST`: IO21 → U2 NRST + R36 ✓ |
| ESP32-S3 GPIO mapping | IO0-IO47 all match the brief's GPIO table ✓ |
| I2C buses | Bus1 (IO8/9), Bus2 (IO17/18), Bus3 (IO5/6) with correct pull-ups ✓ |
| SPI shared LoRa+SD | MOSI/SCK via R18/R19, MISO direct, separate CS ✓ |
| RS485 | MAX3485 + SM712 + R24 term + R25/R26 series ✓ |
| USB-C | CC1/CC2 5.1K, ESD D2, load switch U14, reverse block D15 ✓ |
| RTC | DS3231 + CR2032 (BT1) + R37 pull-up ✓ |
| Power tree | 12V→U12→5V→U10→3.3V; U11→3.8V→L1→C1 ✓ |

---

## ❓ QUESTIONS FOR FLUX.AI / DECISIONS NEEDED

1. **Why is the SIM7600G subsystem unwired?** U3, U9 signals, Q4, J14, D13, D14, R16/R17/R20–R22, R31/R32 P2, R33 have zero nets. Was the GSM section never captured, or was it lost in an edit?
2. **Why is the MPU6500 (IC1) unwired?** Its pins are on auto-named `Net 1`–`Net 10`. Was it placed but never connected to I2C3/3V3/GND?
3. **What are C1_1/C2_1/C3_1/R1_1–R5_1?** Duplicate instances that break the BOM (C1/C2/C3 appear with 3 different values). Delete them or wire them correctly.
4. **What is the actual board outline?** The 160×100mm Profile doesn't cover any placed component. Is the outline a placeholder, or are components off-board?
5. **Can U12 (generic multi-output buck) deliver 2.8A on the 5V output?** The HW-187 was specified for 3A single-output. If not, replace with a proper 12V→5V 3A module.
6. **Approve the documented deviations?** TXU0202 (D1), SM712 (D2), ESDA6V1BC6 (D3), TPS54331D (D4), AP2152SG SOIC-8 (D8), D16 bootstrap diode (D9).
7. **2-layer or 4-layer?** The brief says 2-layer (user preference); the export is 4-layer. Which is final?
8. **J1 power input connector:** Accept JST-XH, or source a Phoenix 3.81mm screw terminal footprint?
9. **F1 fuse:** Accept 24V-rated SMDC300F/24-2, or switch to a 30V+ rated fuse?
10. **R50:** Keep as GSM antenna π-match series element (documented), or remove?

---

## 📋 RECOMMENDED FIX ORDER

1. **Wire the SIM7600G subsystem** (U3, U9, Q4, J14, D13, D14, R16/R17/R20–R22, R31/R32 P2, R33) — highest priority
2. **Wire the MPU6500** (IC1 → I2C3, 3V3, GND, INT) and delete C1_1–C3_1/R1_1–R5_1 duplicates
3. **Fix parts:** D3–D8 → ESDA6V8-2U2/1U2; L1 → 600Ω ferrite bead; C1 → 100µF tantalum; C2 → 100µF 35V electrolytic
4. **Replace U12** with a proper 12V→5V 3A module (HW-187 or equivalent)
5. **Fix J1** to Phoenix 3.81mm screw terminal
6. **Verify board outline** covers all components
7. **Decide 2-layer vs 4-layer**
8. **Fill LCSC part numbers** for all parts in the JLCPCB BOM
9. **Re-export** EDIF + IPC-2581C + all BOMs after fixes
10. **Run DRC/ERC** and confirm zero unconnected pins before ordering
