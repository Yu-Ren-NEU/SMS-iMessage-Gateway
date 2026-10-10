# V0.32 enclosure

Print `base.stl`, `lid-carrier.stl`, and `top-cover.stl` at 100% scale in millimeters. Use black PETG for the base and carrier, and limestone-white PETG for the top. STEP files are editable geometry; JSON records dimensions, PNG is a preview, and Python is CAD source. Only the STL files need printing.

The original robot is a separate part in `../plugins/`. Its 4.0 × 4.0 mm square peg fits a 4.4 × 4.4 mm blind lid socket in four orientations. Peg length is 1.65 mm, bottom clearance 0.25 mm, and remaining roof thickness 0.6 mm. The original nominal width difference of 0.4 mm matches the internal 2.5 mm pin / 2.9 mm socket difference. Replacement V2 figurines use a larger 4.2 mm peg; internal enclosure pillars remain unchanged.

Regeneration with `generate_enclosure.py` requires CadQuery and macOS Apple Chancery for the engraving. Fonts are not redistributed; substitute a licensed font on other platforms and review its geometry.

## Physical results and print records

The owner confirmed the final enclosure assembles well, remains stable in daily use, and supports automatic module/SMS recovery after power reconnection. The new 4.2 mm figurine pegs do not fit their first print; a reprint is planned. The cause is unconfirmed. Do not force them.

Final slicer projects, measured weight, filament brand, exact print settings, and temperature measurements are not recorded. Nominal CAD clearance is not a guarantee of printed fit. Ask the shop to choose supports and orientation for its machine.

| Check | Record |
|---|---|
| Printing | Printer, nozzle, filament, layer height, walls, infill, orientation, supports, total sliced weight including supports |
| Fit | Measured pin/socket dimensions, insertion force, looseness, cracking, removability |
| Enclosure | Four-post support, lid closure, USB clearance, card access, antenna fastening; no PCB/pin pressure |
| Figurine | Four orientations, stability, readable facial details |
| Use | Temperature, deformation, changes after repeated insertion |

Test one figurine before ordering more. Adjust only the peg/socket geometry to tune fit; do not scale the entire model or change internal mounting posts. V2 nominal per-side clearance is 0.1 mm.
