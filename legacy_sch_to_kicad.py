#!/usr/bin/env python3
"""Convert legacy KiCad schematic files (.sch + .lib, e2sch.exe output) to
modern KiCad 8+ format (.kicad_sch with embedded lib_symbols).

Usage:
    python legacy_sch_to_kicad.py <dir>
        converts <dir>/morishield_v2.sch -> <dir>/morishield_v2.kicad_sch
        converts <dir>/FluxLibrary.lib -> <dir>/FluxLibrary.kicad_sym
        converts <dir>/Main.lib -> <dir>/Main.kicad_sym
"""

import os
import re
import sys
import uuid

TYPE_MAP = {
    "U": "unspecified", "I": "input", "O": "output", "B": "bidirectional",
    "P": "passive", "W": "power_in", "w": "power_out",
    "C": "open_collector", "E": "open_emitter", "N": "no_connect",
}


def strip_escape(name):
    """Strip EDIF-style leading '&' escape prefix from a name."""
    return name[1:] if name.startswith("&") else name


def parse_lib(path):
    """Parse a legacy EESchema .lib file. Returns {symbol_name: {pins: [...]}}."""
    symbols = {}
    cur = None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith("DEF "):
                parts = line.split()
                cur = parts[1]
                symbols[cur] = {"pins": []}
            elif line.startswith("X ") and cur is not None:
                parts = line.split()
                # X <name> <number> <x> <y> <length> <orient> <size> <unit> <convert> <type>
                # e2sch.exe writes names with spaces ("+ OUT_2") and 4-char truncated
                # numbers, so detect the space-name case by checking the x field.
                if len(parts) >= 13:
                    try:
                        float(parts[3])
                        name, num, x, y = parts[1], parts[2], parts[3], parts[4]
                        length, orient, typ = parts[5], parts[6], parts[10]
                    except ValueError:
                        name = parts[1] + " " + parts[2]
                        x, y = parts[5], parts[6]
                        length, orient, typ = parts[7], parts[8], parts[12]
                    symbols[cur]["pins"].append({
                        "name": strip_escape(name),
                        "number": strip_escape(name),  # truncated numbers are not unique
                        "x": float(x), "y": float(y),
                        "length": float(length),
                        "orient": orient,
                        "type": TYPE_MAP.get(typ, "unspecified"),
                    })
            elif line.startswith("ENDDEF"):
                cur = None
    return symbols


def _pin_lines(pin, indent):
    pad = " " * indent
    return [
        '%s(pin %s line' % (pad, pin["type"]),
        '%s  (at %s %s 270)' % (pad, _fmt(pin["x"] / 1000.0 * 25.4), _fmt(pin["y"] / 1000.0 * 25.4)),
        '%s  (length %s)' % (pad, _fmt(pin["length"] / 1000.0 * 25.4)),
        '%s  (name "%s"' % (pad, pin["name"]),
        '%s    (effects' % pad,
        '%s      (font' % pad,
        '%s        (size 1.27 1.27)' % pad,
        '%s      )' % pad,
        '%s    )' % pad,
        '%s  )' % pad,
        '%s  (number "%s"' % (pad, pin["number"]),
        '%s    (effects' % pad,
        '%s      (font' % pad,
        '%s        (size 1.27 1.27)' % pad,
        '%s      )' % pad,
        '%s    )' % pad,
        '%s  )' % pad,
        '%s)' % pad,
    ]


def write_sym(path, symbols):
    lines = []
    lines.append('(kicad_symbol_lib')
    lines.append('  (version 20220914)')
    lines.append('  (generator "legacy_sch_to_kicad")')
    lines.append('  (generator_version "1.0")')
    for name, sym in symbols.items():
        lines.append('  (symbol "%s"' % name)
        lines.append('    (pin_names (offset 0.254))')
        lines.append('    (exclude_from_sim no)')
        lines.append('    (in_bom yes)')
        lines.append('    (on_board yes)')
        lines.append('    (duplicate_pin_numbers_are_jumpers no)')
        lines.append('    (property "Reference" "U" (at 0 2.54 0) (effects (font (size 1.27 1.27))))')
        lines.append('    (property "Value" "%s" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))' % name)
        lines.append('    (symbol "%s_1_1"' % name)
        for pin in sym["pins"]:
            lines.extend(_pin_lines(pin, 6))
        lines.append('    )')
        lines.append('  )')
    lines.append(')')
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote %s (%d symbols)" % (path, len(symbols)))


def _fmt(v):
    s = ("%.4f" % v).rstrip("0").rstrip(".")
    return s if s not in ("", "-") else "0"


def parse_sch(path):
    """Parse a legacy .sch file. Returns (descr, [components])."""
    comps = []
    cur = None
    for raw in open(path, "r", encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line.startswith("$Comp"):
            cur = {}
        elif line.startswith("L ") and cur is not None:
            parts = line.split()
            cur["lib"] = parts[1]
            cur["ref"] = parts[2]
        elif line.startswith("P ") and cur is not None:
            parts = line.split()
            cur["x"] = float(parts[1])
            cur["y"] = float(parts[2])
        elif line.startswith("$EndComp") and cur is not None:
            comps.append(cur)
            cur = None
    return comps


def write_sch(path, comps, lib_symbols):
    sheet_uuid = str(uuid.uuid4())
    lines = []
    lines.append('(kicad_sch')
    lines.append('  (version 20250610)')
    lines.append('  (generator "legacy_sch_to_kicad")')
    lines.append('  (generator_version "1.0")')
    lines.append('  (uuid "%s")' % sheet_uuid)
    lines.append('  (paper "A4")')
    lines.append('  (lib_symbols')
    for libname, symbols in lib_symbols.items():
        for name, sym in symbols.items():
            lines.append('    (symbol "%s:%s"' % (libname, name))
            lines.append('      (pin_names (offset 0.254))')
            lines.append('      (exclude_from_sim no)')
            lines.append('      (in_bom yes)')
            lines.append('      (on_board yes)')
            lines.append('      (duplicate_pin_numbers_are_jumpers no)')
            lines.append('      (property "Reference" "U" (at 0 2.54 0) (effects (font (size 1.27 1.27))))')
            lines.append('      (property "Value" "%s" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))' % name)
            lines.append('      (symbol "%s_1_1"' % name)
            for pin in sym["pins"]:
                lines.extend(_pin_lines(pin, 8))
            lines.append('      )')
            lines.append('    )')
    lines.append('  )')
    for c in comps:
        lib_id = "%s:%s" % (c["lib"], c["lib"])
        inst_uuid = str(uuid.uuid4())
        lines.append('  (symbol')
        lines.append('    (lib_id "%s")' % lib_id)
        lines.append('    (at %s %s 0)' % (_fmt(c["x"]), _fmt(c["y"])))
        lines.append('    (unit 1)')
        lines.append('    (exclude_from_sim no)')
        lines.append('    (in_bom yes)')
        lines.append('    (on_board yes)')
        lines.append('    (dnp no)')
        lines.append('    (uuid "%s")' % inst_uuid)
        lines.append('    (property "Reference" "%s" (at %s %s 0) (effects (font (size 1.27 1.27))))'
                     % (c["ref"], _fmt(c["x"]), _fmt(c["y"])))
        lines.append('    (property "Value" "%s" (at %s %s 0) (effects (font (size 1.27 1.27))))'
                     % (c["lib"], _fmt(c["x"]), _fmt(c["y"])))
        lines.append('    (property "Footprint" "" (at %s %s 0) (hide yes) (effects (font (size 1.27 1.27))))'
                     % (_fmt(c["x"]), _fmt(c["y"])))
        lines.append('    (property "Datasheet" "" (at %s %s 0) (hide yes) (effects (font (size 1.27 1.27))))'
                     % (_fmt(c["x"]), _fmt(c["y"])))
        sym = lib_symbols.get(c["lib"], {}).get(c["lib"], {"pins": []})
        for pin in sym["pins"]:
            lines.append('    (pin "%s" (uuid "%s"))' % (pin["number"], uuid.uuid4()))
        lines.append('    (instances')
        lines.append('      (project "morishield_v2"')
        lines.append('        (path "/%s"' % sheet_uuid)
        lines.append('          (reference "%s")' % c["ref"])
        lines.append('          (unit 1)')
        lines.append('        )')
        lines.append('      )')
        lines.append('    )')
        lines.append('  )')
    lines.append('  (sheet_instances')
    lines.append('    (path "/"')
    lines.append('      (page "1")')
    lines.append('    )')
    lines.append('  )')
    lines.append(')')
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote %s (%d symbols)" % (path, len(comps)))


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    lib_symbols = {}
    for lib in ("FluxLibrary", "Main"):
        src = os.path.join(d, lib + ".lib")
        if os.path.exists(src):
            syms = parse_lib(src)
            lib_symbols[lib] = syms
            write_sym(os.path.join(d, lib + ".kicad_sym"), syms)
    sch = os.path.join(d, "morishield_v2.sch")
    if os.path.exists(sch):
        comps = parse_sch(sch)
        write_sch(os.path.join(d, "morishield_v2.kicad_sch"), comps, lib_symbols)


if __name__ == "__main__":
    main()
