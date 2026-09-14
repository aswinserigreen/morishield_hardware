#!/usr/bin/env python3
"""Convert an IPC-2581C file (Flux.ai export) to a KiCad 8+ .kicad_pcb board.

Usage:
    python ipc2581_to_kicad.py <input.ipc2581c> <output.kicad_pcb>

Handles: board outline (Profile), component placements, padstacks,
pads with nets (F.Cu/B.Cu/In1/In2), plated vias, plated slots,
mounting holes, package outlines (F.Fab) and silkscreen graphics.
"""

import math
import sys
import uuid
import xml.etree.ElementTree as ET

NS = "http://webstds.ipc.org/2581"


def T(name):
    return "{%s}%s" % (NS, name)


def fnum(v, nd=6):
    """Format a float, trimming trailing zeros."""
    if v is None:
        return "0"
    s = ("%.*f" % (nd, float(v))).rstrip("0").rstrip(".")
    return s if s not in ("", "-") else "0"


def rot_pt(x, y, ang_deg):
    """Rotate a point by ang_deg degrees (CCW)."""
    a = math.radians(ang_deg)
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


def parse_polygon(elem):
    pts = []
    for child in elem:
        if child.tag == T("PolyBegin"):
            pts.append((float(child.get("x")), float(child.get("y"))))
        elif child.tag == T("PolyStepSegment"):
            x, y = pts[-1]
            pts.append((x + float(child.get("x")), y + float(child.get("y"))))
    return pts


def parse_shape(elem):
    """Parse an EntryStandard / EntryUser / UserSpecial into a shape dict."""
    for child in elem:
        tag = child.tag
        if tag == T("RectCenter"):
            return {"kind": "rect", "w": float(child.get("width")), "h": float(child.get("height"))}
        if tag == T("RectRound"):
            return {"kind": "roundrect", "w": float(child.get("width")),
                    "h": float(child.get("height")), "r": float(child.get("radius"))}
        if tag == T("Oval"):
            return {"kind": "oval", "w": float(child.get("width")), "h": float(child.get("height"))}
        if tag == T("Circle"):
            return {"kind": "circle", "d": float(child.get("diameter"))}
        if tag == T("Contour"):
            poly = child.find(T("Polygon"))
            if poly is not None:
                return {"kind": "custom", "pts": parse_polygon(poly)}
        if tag == T("UserSpecial"):
            return parse_shape(child)
    return {"kind": "rect", "w": 0.5, "h": 0.5}


def parse_padstack(elem):
    hole = None
    layers = {}
    for child in elem:
        if child.tag == T("PadstackHoleDef"):
            hole = {"d": float(child.get("diameter")), "plating": child.get("platingStatus")}
        elif child.tag == T("PadstackPadDef"):
            prim = None
            for sub in child:
                if sub.tag in (T("StandardPrimitiveRef"), T("UserPrimitiveRef")):
                    prim = sub.get("id")
            layers[child.get("layerRef")] = prim
    return {"hole": hole, "layers": layers}


def parse_package(elem):
    outline = None
    silk_lines = []
    silk_prims = []
    for child in elem:
        if child.tag == T("Outline"):
            poly = child.find(T("Polygon"))
            if poly is not None:
                outline = parse_polygon(poly)
        elif child.tag == T("SilkScreen"):
            marking = child.find(T("Marking"))
            if marking is not None:
                us = marking.find(T("UserSpecial"))
                if us is not None:
                    for sub in us:
                        if sub.tag == T("Line"):
                            silk_lines.append((float(sub.get("startX")), float(sub.get("startY")),
                                               float(sub.get("endX")), float(sub.get("endY"))))
                        elif sub.tag in (T("StandardPrimitiveRef"), T("UserPrimitiveRef")):
                            silk_prims.append(sub.get("id"))
    return {"outline": outline, "silk_lines": silk_lines, "silk_prims": silk_prims}


def parse_component(elem):
    refdes = elem.get("refDes")
    comp = {"package": elem.get("packageRef"), "layer": elem.get("layerRef"),
            "part": elem.get("part", ""), "rot": 0.0, "mirror": False, "x": 0.0, "y": 0.0}
    for child in elem:
        if child.tag == T("Xform"):
            comp["rot"] = float(child.get("rotation", 0) or 0)
            comp["mirror"] = child.get("mirror") == "true"
        elif child.tag == T("Location"):
            comp["x"] = float(child.get("x"))
            comp["y"] = float(child.get("y"))
    return refdes, comp


def parse_pad(elem, layer, net):
    pad = {"ps": elem.get("padstackDefRef"), "rot": 0.0, "x": 0.0, "y": 0.0,
           "prim": None, "comp": None, "pin": None, "net": net, "layer": layer}
    for child in elem:
        if child.tag == T("Xform"):
            pad["rot"] = float(child.get("rotation", 0) or 0)
        elif child.tag == T("Location"):
            pad["x"] = float(child.get("x"))
            pad["y"] = float(child.get("y"))
        elif child.tag in (T("StandardPrimitiveRef"), T("UserPrimitiveRef")):
            pad["prim"] = child.get("id")
        elif child.tag == T("PinRef"):
            pad["comp"] = child.get("componentRef")
            pad["pin"] = child.get("pin")
    return pad


def main():
    if len(sys.argv) != 3:
        print("usage: python ipc2581_to_kicad.py <input.ipc2581c> <output.kicad_pcb>")
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]

    prims = {}          # id -> shape dict
    padstacks = {}      # name -> {hole, layers}
    packages = {}       # name -> {outline, silk_lines, silk_prims}
    components = {}     # refdes -> comp dict
    pads = {}           # (refdes, pin) -> {net, ps, prim, x, y, rot, layers:set}
    holes = []          # vias / mounting holes
    slots = []          # plated slots
    silk_graphics = []  # (layer, prim_id, dx, dy)
    profile = None

    context = {}
    for event, elem in ET.iterparse(src, events=("start", "end")):
        tag = elem.tag
        if event == "start":
            if tag == T("LayerFeature"):
                context["layer"] = elem.get("layerRef")
                context["set_net"] = None
                context["set_comp"] = None
            elif tag == T("Set"):
                context["set_net"] = elem.get("net")
                context["set_comp"] = elem.get("componentRef")
                context["set_geometry"] = elem.get("geometry")
            continue

        if tag == T("EntryStandard"):
            prims[elem.get("id")] = parse_shape(elem)
        elif tag == T("EntryUser"):
            prims[elem.get("id")] = parse_shape(elem)
        elif tag == T("PadStackDef"):
            padstacks[elem.get("name")] = parse_padstack(elem)
        elif tag == T("Profile"):
            poly = elem.find(T("Polygon"))
            if poly is not None:
                profile = parse_polygon(poly)
        elif tag == T("Package"):
            packages[elem.get("name")] = parse_package(elem)
        elif tag == T("Component"):
            refdes, comp = parse_component(elem)
            components[refdes] = comp
        elif tag == T("Pad"):
            layer = context.get("layer")
            if layer in ("F.Cu", "B.Cu", "In1.Cu", "In2.Cu"):
                pad = parse_pad(elem, layer, context.get("set_net"))
                if pad["comp"] and pad["pin"]:
                    key = (pad["comp"], pad["pin"])
                    if key not in pads:
                        pad["layers"] = set()
                        pads[key] = pad
                    pads[key]["layers"].add(layer)
                    # keep F.Cu occurrence as the geometry reference
                    if layer == "F.Cu" and pads[key]["layer"] != "F.Cu":
                        pads[key].update({k: pad[k] for k in ("ps", "rot", "x", "y", "prim", "net")})
        elif tag == T("Hole"):
            layer = context.get("layer")
            if layer in ("F.Cu_B.Cu", "F.Cu_B.Cu_1"):
                holes.append({"net": context.get("set_net"),
                              "ps": context.get("set_geometry"),
                              "drill": float(elem.get("diameter")),
                              "plating": elem.get("platingStatus"),
                              "x": float(elem.get("x")), "y": float(elem.get("y"))})
        elif tag == T("SlotCavity"):
            layer = context.get("layer")
            if layer in ("F.Cu_B.Cu", "F.Cu_B.Cu_1"):
                oval = elem.find(T("Oval"))
                loc = elem.find(T("Location"))
                xf = elem.find(T("Xform"))
                rot = float(xf.get("rotation", 0) or 0) if xf is not None else 0.0
                slots.append({"net": context.get("set_net"),
                              "x": float(loc.get("x")), "y": float(loc.get("y")),
                              "rot": rot,
                              "w": float(oval.get("width")), "h": float(oval.get("height"))})
        elif tag == T("Features"):
            layer = context.get("layer")
            if layer in ("F.SilkS", "B.SilkS") and context.get("set_comp"):
                loc = elem.find(T("Location"))
                dx = float(loc.get("x")) if loc is not None else 0.0
                dy = float(loc.get("y")) if loc is not None else 0.0
                for sub in elem:
                    if sub.tag in (T("StandardPrimitiveRef"), T("UserPrimitiveRef")):
                        silk_graphics.append((layer, sub.get("id"), dx, dy))

    # ---------- nets ----------
    net_names = set()
    for pad in pads.values():
        if pad["net"]:
            net_names.add(pad["net"])
    for h in holes:
        if h["net"]:
            net_names.add(h["net"])
    for s in slots:
        if s["net"]:
            net_names.add(s["net"])
    net_list = sorted(net_names)
    net_codes = {name: i + 1 for i, name in enumerate(net_list)}

    # ---------- helpers ----------
    def shape_of(prim_id, padstack_name):
        if prim_id and prim_id in prims:
            return prims[prim_id]
        ps = padstacks.get(padstack_name)
        if ps:
            for layer in ("F.Cu", "B.Cu"):
                p = ps["layers"].get(layer)
                if p and p in prims:
                    return prims[p]
        return {"kind": "rect", "w": 0.5, "h": 0.5}

    def pad_layers(pad, thru):
        if thru:
            return '"F.Cu" "B.Cu"'
        if pad["layer"] == "B.Cu":
            return '"B.Cu" "B.Paste" "B.Mask"'
        return '"F.Cu" "F.Paste" "F.Mask"'

    def shape_sizes(shape):
        if shape["kind"] == "circle":
            return shape["d"], shape["d"]
        if shape["kind"] == "custom":
            xs = [p[0] for p in shape["pts"]]
            ys = [p[1] for p in shape["pts"]]
            return max(xs) - min(xs), max(ys) - min(ys)
        return shape["w"], shape["h"]

    def pad_shape_str(shape, size_w, size_h):
        kind = shape["kind"]
        if kind == "circle":
            return "circle"
        if kind == "roundrect":
            return "roundrect"
        if kind == "oval":
            return "oval"
        if kind == "custom":
            return "custom"
        return "rect"

    def pad_extra(shape, size_w, size_h):
        out = []
        if shape["kind"] == "roundrect":
            r = min(shape.get("r", 0), min(size_w, size_h) / 2)
            ratio = r / min(size_w, size_h) if min(size_w, size_h) > 0 else 0
            out.append("  (roundrect_rratio %s)" % fnum(ratio, 4))
        if shape["kind"] == "custom":
            pts = shape["pts"]
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            out.append("  (zone_connect 2)")
            out.append("  (options (clearance outline) (anchor circle))")
            out.append("  (primitives")
            out.append("    (gr_poly (pts")
            for px, py in pts:
                out.append("      (xy %s %s)" % (fnum(px - cx), fnum(py - cy)))
            out.append("    ) (width 0))")
            out.append("  )")
        return out

    # ---------- footprints ----------
    fp_lines = []
    for refdes, comp in sorted(components.items()):
        if refdes.startswith("NOREF"):
            continue
        comp_pads = [p for k, p in pads.items() if k[0] == refdes]
        pkg = packages.get(comp["package"], {"outline": None, "silk_lines": [], "silk_prims": []})
        side = "B.Cu" if comp["layer"] == "B.Cu" else "F.Cu"
        silk_layer = "B.SilkS" if side == "B.Cu" else "F.SilkS"
        fab_layer = "B.Fab" if side == "B.Cu" else "F.Fab"
        has_thru = any("F.Cu" in p["layers"] and "B.Cu" in p["layers"]
                       and padstacks.get(p["ps"], {}).get("hole") for p in comp_pads)
        attr = "through_hole" if has_thru else "smd"

        lines = []
        lines.append('  (footprint "%s"' % comp["package"])
        lines.append('    (layer "%s")' % side)
        lines.append('    (uuid "%s")' % uuid.uuid4())
        lines.append('    (at %s %s %s)' % (fnum(comp["x"]), fnum(comp["y"]), fnum(comp["rot"])))
        lines.append('    (attr %s)' % attr)
        value = comp["part"].lstrip("_") if comp["part"] else comp["package"]
        lines.append('    (fp_text reference "%s" (at 0 -2.5) (layer "%s")'
                     ' (effects (font (size 1 1) (thickness 0.15))))' % (refdes, silk_layer))
        lines.append('    (fp_text value "%s" (at 0 2.5) (layer "%s")'
                     ' (effects (font (size 1 1) (thickness 0.15))))' % (value, fab_layer))
        # package outline -> F.Fab
        if pkg["outline"]:
            pts = " ".join("(xy %s %s)" % (fnum(x), fnum(y)) for x, y in pkg["outline"])
            lines.append('    (fp_poly (pts %s) (stroke (width 0.1) (type solid)) (layer "%s") (fill none))'
                         % (pts, fab_layer))
        # package silkscreen lines
        for sx1, sy1, sx2, sy2 in pkg["silk_lines"]:
            lines.append('    (fp_line (start %s %s) (end %s %s) (stroke (width 0.12) (type solid)) (layer "%s"))'
                         % (fnum(sx1), fnum(sy1), fnum(sx2), fnum(sy2), silk_layer))
        # package silkscreen primitives
        for pid in pkg["silk_prims"]:
            sh = prims.get(pid)
            if sh and sh["kind"] == "custom":
                pts = " ".join("(xy %s %s)" % (fnum(x), fnum(y)) for x, y in sh["pts"])
                lines.append('    (fp_poly (pts %s) (stroke (width 0.12) (type solid)) (layer "%s") (fill none))'
                             % (pts, silk_layer))
        # pads
        for pad in comp_pads:
            ps = padstacks.get(pad["ps"], {"hole": None, "layers": {}})
            thru = "F.Cu" in pad["layers"] and "B.Cu" in pad["layers"] and ps["hole"] is not None
            dx, dy = pad["x"] - comp["x"], pad["y"] - comp["y"]
            if comp["rot"]:
                dx, dy = rot_pt(dx, dy, -comp["rot"])
            if side == "B.Cu":
                dy = -dy
            prot = pad["rot"] - comp["rot"]
            if side == "B.Cu":
                prot = -prot
            shape = shape_of(pad["prim"], pad["ps"])
            sw, shh = shape_sizes(shape)
            if sw <= 0 or shh <= 0:
                sw, shh = 0.5, 0.5
            ptype = "thru_hole" if thru else "smd"
            lines.append('    (pad "%s" %s %s' % (pad["pin"], ptype, pad_shape_str(shape, sw, shh)))
            lines.append('      (at %s %s %s)' % (fnum(dx), fnum(dy), fnum(prot)))
            lines.append('      (size %s %s)' % (fnum(sw), fnum(shh)))
            if thru and ps["hole"]:
                lines.append('      (drill %s)' % fnum(ps["hole"]["d"]))
            lines.append('      (layers %s)' % pad_layers(pad, thru))
            lines.extend(pad_extra(shape, sw, shh))
            if pad["net"]:
                lines.append('      (net %d "%s")' % (net_codes[pad["net"]], pad["net"]))
            lines.append('      (uuid "%s")' % uuid.uuid4())
            lines.append('    )')
        lines.append('  )')
        fp_lines.append("\n".join(lines))

    # ---------- vias / mounting holes ----------
    pad_positions = {(round(p["x"], 3), round(p["y"], 3)) for p in pads.values()}
    via_lines = []
    mh_lines = []
    for i, h in enumerate(holes):
        if (round(h["x"], 3), round(h["y"], 3)) in pad_positions:
            continue  # THT component pad, already emitted
        ps = padstacks.get(h["ps"], {"hole": None, "layers": {}})
        size = 0.6
        for layer in ("F.Cu", "B.Cu"):
            p = ps["layers"].get(layer)
            if p and p in prims:
                sh = prims[p]
                sw, _ = shape_sizes(sh)
                if sw > 0:
                    size = sw
                    break
        if h["plating"] == "NONPLATED":
            mh_lines.append('  (footprint "MountingHole"')
            mh_lines.append('    (layer "F.Cu")')
            mh_lines.append('    (uuid "%s")' % uuid.uuid4())
            mh_lines.append('    (at %s %s 0)' % (fnum(h["x"]), fnum(h["y"])))
            mh_lines.append('    (attr through_hole)')
            mh_lines.append('    (fp_text reference "" (at 0 -2.5) (layer "F.SilkS")'
                            ' (effects (font (size 1 1) (thickness 0.15))))')
            mh_lines.append('    (fp_text value "" (at 0 2.5) (layer "F.Fab")'
                            ' (effects (font (size 1 1) (thickness 0.15))))')
            mh_lines.append('    (pad "" thru_hole circle')
            mh_lines.append('      (at 0 0 0)')
            mh_lines.append('      (size %s %s)' % (fnum(size), fnum(size)))
            mh_lines.append('      (drill %s)' % fnum(h["drill"]))
            mh_lines.append('      (layers "F.Cu" "B.Cu")')
            mh_lines.append('      (uuid "%s")' % uuid.uuid4())
            mh_lines.append('    )')
            mh_lines.append('  )')
        else:
            via_lines.append('  (via (at %s %s) (size %s) (drill %s) (layers "F.Cu" "B.Cu")%s)'
                             % (fnum(h["x"]), fnum(h["y"]), fnum(size), fnum(h["drill"]),
                                ' (net %d)' % net_codes[h["net"]] if h["net"] else ""))

    # ---------- slots ----------
    slot_lines = []
    for i, s in enumerate(slots):
        slot_lines.append('  (footprint "SLOT_%d"' % (i + 1))
        slot_lines.append('    (layer "F.Cu")')
        slot_lines.append('    (uuid "%s")' % uuid.uuid4())
        slot_lines.append('    (at %s %s 0)' % (fnum(s["x"]), fnum(s["y"])))
        slot_lines.append('    (attr through_hole)')
        slot_lines.append('    (fp_text reference "" (at 0 -2.5) (layer "F.SilkS")'
                          ' (effects (font (size 1 1) (thickness 0.15))))')
        slot_lines.append('    (fp_text value "" (at 0 2.5) (layer "F.Fab")'
                          ' (effects (font (size 1 1) (thickness 0.15))))')
        slot_lines.append('    (pad "" thru_hole oval')
        slot_lines.append('      (at 0 0 %s)' % fnum(s["rot"]))
        slot_lines.append('      (size %s %s)' % (fnum(s["w"]), fnum(s["h"])))
        slot_lines.append('      (drill oval %s %s)' % (fnum(s["w"]), fnum(s["h"])))
        slot_lines.append('      (layers "F.Cu" "B.Cu")')
        if s["net"]:
            slot_lines.append('      (net %d "%s")' % (net_codes[s["net"]], s["net"]))
        slot_lines.append('      (uuid "%s")' % uuid.uuid4())
        slot_lines.append('    )')
        slot_lines.append('  )')

    # ---------- board outline ----------
    outline_lines = []
    if profile:
        n = len(profile)
        for i in range(n):
            x1, y1 = profile[i]
            x2, y2 = profile[(i + 1) % n]
            outline_lines.append('  (gr_line (start %s %s) (end %s %s)'
                                 ' (stroke (width 0.1) (type solid)) (layer "Edge.Cuts"))'
                                 % (fnum(x1), fnum(y1), fnum(x2), fnum(y2)))

    # ---------- silkscreen graphics (absolute) ----------
    silk_lines = []
    for layer, pid, dx, dy in silk_graphics:
        sh = prims.get(pid)
        if sh and sh["kind"] == "custom":
            pts = " ".join("(xy %s %s)" % (fnum(x + dx), fnum(y + dy)) for x, y in sh["pts"])
            silk_lines.append('  (gr_poly (pts %s) (stroke (width 0.12) (type solid)) (layer "%s") (fill none))'
                              % (pts, layer))

    # ---------- assemble ----------
    out = []
    out.append('(kicad_pcb (version 20240108) (generator "ipc2581_to_kicad") (generator_version "1.0")')
    out.append('  (general (thickness 1.6) (legacy_teardrops no))')
    out.append('  (paper "A4")')
    out.append('  (layers')
    out.append('    (0 "F.Cu" signal)')
    out.append('    (1 "In1.Cu" signal)')
    out.append('    (2 "In2.Cu" signal)')
    out.append('    (3 "B.Cu" signal)')
    out.append('    (4 "F.Paste" user)')
    out.append('    (5 "B.Paste" user)')
    out.append('    (6 "F.SilkS" user)')
    out.append('    (7 "B.SilkS" user)')
    out.append('    (8 "F.Mask" user)')
    out.append('    (9 "B.Mask" user)')
    out.append('    (14 "F.CrtYd" user)')
    out.append('    (15 "B.CrtYd" user)')
    out.append('    (16 "F.Fab" user)')
    out.append('    (17 "B.Fab" user)')
    out.append('    (44 "Edge.Cuts" user)')
    out.append('  )')
    out.append('  (net 0 "")')
    for name in net_list:
        out.append('  (net %d "%s")' % (net_codes[name], name))
    out.extend(fp_lines)
    out.extend(mh_lines)
    out.extend(slot_lines)
    out.extend(via_lines)
    out.extend(outline_lines)
    out.extend(silk_lines)
    out.append(')')

    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

    print("components: %d" % len([c for c in components if not c.startswith("NOREF")]))
    print("pads: %d" % len(pads))
    print("nets: %d" % len(net_list))
    print("vias: %d" % len(via_lines))
    print("mounting holes: %d" % (len(mh_lines) // 10))
    print("slots: %d" % len(slots))
    print("silk graphics: %d" % len(silk_lines))
    print("wrote %s" % dst)


if __name__ == "__main__":
    main()
