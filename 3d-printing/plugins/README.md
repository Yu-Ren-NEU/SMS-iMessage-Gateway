# Interchangeable figurines

- `robot-original.stl` / `.step`: original V0.32 robot; its 4.0 mm square peg was loose in a physical sample.
- `astronaut-plugin.stl`, `cat-plugin.stl`, `tv-plugin.stl`: V2 astronaut, square-headed cat, and retro television character. Each uses a 4.2 mm square peg, 1.65 mm insertion length, and a 0.25 mm lead-in chamfer for the existing 4.4 mm socket.
- `review.png`: individual and assembled previews.
- `generate_astronaut.py`, `generate_cat_tv.py`: CadQuery source. Units are millimeters; body height is approximately 24 mm and the base is 21 × 18 mm.

Send STL files to the print shop. Source and preview files need no printing. A new lid is not required. Distributed meshes were cleaned of zero-area faces and checked for watertightness.

## Fit status

The first V2 prints do **not** fit; the owner plans a reprint. The cause is not established. Do not force the peg. Print one replacement first, check all four orientations, stability, and facial detail, then decide whether to print the others.

The original 4.0 mm peg was loose; V2 increases it to 4.2 mm while retaining the 4.4 mm lid socket, giving 0.1 mm nominal clearance per side. Change only peg/socket geometry if adjustment is necessary, not whole-model scale or internal enclosure posts.

## Printing and acceptance

Record printer, nozzle, filament, layer height, walls, infill, orientation, supports, and sliced weight including supports. These final settings and measured weights are currently unrecorded. Ask the shop to review overhangs and supports; nominal CAD dimensions cannot guarantee printed fit.

Check measured peg/socket sizes, gentle insertion and removal, cracking or looseness, stability in all four orientations, readable eyes/mouth, and changes after repeated use. Use the existing PETG enclosure; figurine color is optional. The final enclosure assembly and stable daily operation are owner-confirmed, but dedicated temperature measurements and fault-injection tests are unrecorded.
