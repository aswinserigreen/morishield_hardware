# Project Specification

## Project Overview
- **Status:** Review
- Production-intent MoriShield V2 controller for outdoor agricultural pesticide-drift detection.
- One schematic supports **Master** and **Slave** BOM variants; no display.

## Intended Use
- Outdoor Indian agricultural deployment, nominal 0–50 °C, humidity/dust exposure, three nodes per field (one Master, two Slaves).

## What the Device Should Do
- Acquire external environmental probes, capacitive electrode data, wind speed/direction, and motion.
- Timestamp and log data locally.
- Exchange field data over LoRa; Master additionally uploads by LTE or Wi-Fi.
- Drive two 12 V LED loads and one 12 V buzzer/load using corrected low-side switches.
- Provide USB-C debug/programming and optional RS485.

## Main Features
- ESP32-S3-WROOM-1-N16R8; E22-900M22S LoRa; SIM7600G-H Master option.
- FDC1004, MPU-6500, DS3231, microSD, CP2102N, MAX3485.
- Protected 12 V input; 5 V module; 3.3 V and 3.8 V switching rails; USB debug-power OR path.

## System Architecture
```text
12V input -> protection -> 12V_RAIL -> 12V loads
                              -> 5V module -> 5V_RAIL -> 3.3V buck -> logic/sensors
                                                     -> 3.8V 3A buck -> SIM7600 (Master)
USB-C VBUS -> current-limited switch + reverse-blocking diode -> 5V_RAIL (debug only)
ESP32 <-> LoRa / sensors / RTC / SD / RS485 / CP2102N / LTE UART
```

## Hardware Subsystems
- Input protection; 12 V-to-5 V module; 3.3 V buck; 3.8 V GSM buck.
- MCU/debug; LoRa; GSM/SIM/level shifting; FDC sensing; motion; RTC; RS485; microSD; external sensors; low-side outputs.

## Interfaces and Connections
- Exact inter-block net names follow the supplied brief where electrically valid.
- J8/J9/J10: pin 1 = `12V_RAIL`; pin 2 = switched drain (`LED_GREEN_SW`, `LED_RED_SW`, `BUZZ_SW`).
- USB is a self-powered USB 2.0 device interface. USB VBUS may power debug/light-load operation through a current-limited, reverse-blocked path; it is not specified to power GSM burst operation.

## Power and Runtime Expectations
- Primary source is an external nominal 12 V supply/solar subsystem. No battery-runtime target is specified.

## Power Tree and Power Budget
- See the separate **Power Budget** project file.

## Manufacturing and Assembly Expectations
- SMD production assembly, real footprints, outdoor-rated enclosure/coating to be addressed during layout/mechanical design.
- PCB layout is explicitly out of scope for this task.

## Firmware-Relevant Hardware Requirements
- Preserve semantic net names independent of GPIO remapping.
- CP2102N automatic boot/reset must use the Espressif proven interlocked DTR/RTS transistor topology.
- Shared SPI bus for LoRa and microSD with separate chip selects.
- Three independent I2C buses as specified.

## Final GPIO Mapping
- GPIO0 BOOT; GPIO1 SIM_PWRKEY; GPIO2 LED_GREEN_GATE; GPIO4 LED_RED_GATE.
- GPIO5/6 I2C3 SDA/SCL; GPIO7 LORA_BUSY; GPIO8/9 I2C1 SDA/SCL.
- GPIO10 LORA_NSS; GPIO11/12/13 SPI MOSI/SCK/MISO; GPIO14 LORA_DIO1.
- GPIO15/16 UART1 TX/RX; GPIO17/18 I2C2 SDA/SCL; GPIO19/20 NC (native USB unused); GPIO21 LORA_NRST.
- GPIO38 BUZZ_GATE; GPIO39/40 UART2 RX/TX; GPIO41 RS485_DE_RE; GPIO42 WIND_SPEED; GPIO43/44 UART0 TX/RX; GPIO47 SD_CS.
- N16R8 octal-memory reserved GPIO35–37 are not assigned. Strapping pins are limited to intentional GPIO0 boot usage; requested GPIO3 pull-up is retained only if the selected module guidance confirms it is harmless.

## Variants
- **Slave DNF:** LTE module and antenna/SIM path, GSM regulator/filter/bulk, 1.8 V LDO, UART translator, PWRKEY drive, SIM ESD/support, LTE indicators, and SIM-side jumpers.
- **Master DNF:** RS485 UART-selection jumpers. RS485 termination remains install-only-at-bus-end.
- Affected components carry explicit `DNF (Slave)` or `DNF (Master)` metadata.

## Important Design Decisions
- U11 uses TPS54331D (3 A) rather than MP2315; feedback and compensation are TPS54331-specific.
- U9 design intent is retained but TXB0108 is replaced by fixed-direction TXU0202 because UART has known direction and TXB auto-direction devices are vulnerable to edge/loading problems.
- RS485 protection uses an SM712 three-terminal line protector rather than one two-terminal TVS shorting A to B.
- DS3231 is the real 16-pin TCXO RTC, not the incompatible 8-pin DS3231M pin table.
- AP2152 is used in an available valid SOIC-8 variant; a series Schottky provides explicit reverse blocking to USB VBUS.

## Assumptions and Sourcing Notes
- HW-187, exact Phoenix 3.81 mm terminal, and exact requested micro-SIM mechanics may require approved alternates because exact library entries are unavailable. Electrical intent and verified production footprints take priority.
- External 12 V LED/buzzer current is not specified; connector and fuse margin assumes combined external continuous load is limited as described in the Power Budget.

## Change Notes
- Applied the correction file over the original brief, including low-side output topology, 3 A GSM regulator, U13/U14/Q6/Q7, ESD additions, complete regulator stages, valid UART translation, USB reverse-current control, and corrected RS485 TVS topology.
