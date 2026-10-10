#!/usr/bin/env python3
from pathlib import Path
import json
import cadquery as cq
from cadquery import exporters

OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)

P = {
    'pcb_length': 65.15,
    'pcb_width': 56.21,
    'pcb_thickness': 1.5,
    'mount_pitch_x': 58.02,
    'mount_pitch_y': 49.08,
    'mount_hole_diameter': 3.0,
    'case_length': 72.0,
    'case_width': 63.0,
    'base_height': 22.5,
    'lid_height': 11.7,
    'wall': 2.0,
    'floor': 2.4,
    'corner_radius': 5.0,
    'standoff_height': 12.5,
    'standoff_diameter': 5.5,
    'screw_clearance': 2.7,
    'fit_clearance_each_side': 0.425,
    'bottom_vent_count': 6,
    'bottom_vent_width': 3.0,
    'bottom_vent_length': 26.0,
    'board_max_total_thickness': 23.4,
    'antenna_hole_diameter': 6.2,
    'antenna_recess_diameter': 13.0,
    'antenna_recess_floor': 0.9,
    'antenna_side': 'official drawing bottom wall',
    'antenna_side_center_x': 17.0,
    'antenna_side_center_z': 11.4,
    'antenna_recess_location_status': 'relative to former audio center: 3 mm left, 1 mm up',
    'module_usb_center_x': -20.0,
    'module_usb_center_z': 6.5,
    'module_usb_opening_width': 12.0,
    'module_usb_opening_height': 7.0,
    'front_panel_recess_width': 58.0,
    'front_panel_recess_height': 17.0,
    'front_panel_recess_depth': 0.8,
    'front_panel_corner_radius': 3.0,
    'left_service_slot_length': 42.0,
    'left_service_slot_height': 7.0,
}

def rounded_box(l, w, h, r):
    return cq.Workplane('XY').box(l, w, h).edges('|Z').fillet(r)

def ring(l, w, h, r, thickness):
    outer = rounded_box(l, w, h, r)
    inner = rounded_box(l - 2*thickness, w - 2*thickness, h + 0.4, max(0.5, r-thickness))
    return outer.cut(inner)

L,W,H = P['case_length'],P['case_width'],P['base_height']
wall,floor,r = P['wall'],P['floor'],P['corner_radius']

# Main base tub, open at top.
base_outer = rounded_box(L, W, H, r)
cavity_h = H - floor + 0.2
cavity = rounded_box(L-2*wall, W-2*wall, cavity_h, r-wall).translate((0,0,floor/2+0.1))
base = base_outer.cut(cavity)

# Four PCB mounting posts set the board plane; no raised floor platform.
floor_top=-H/2+floor
# Vent slots through the flat center floor; rubber feet will provide airflow clearance.
count=P['bottom_vent_count']; spacing=6.0
for i in range(count):
    x=(i-(count-1)/2)*spacing
    slot=(cq.Workplane('XY').box(P['bottom_vent_width'],P['bottom_vent_length'],floor+0.4)
          .translate((x,0,-H/2+floor/2)))
    base=base.cut(slot)

# Smooth exterior chassis: no perimeter grille or wraparound ribs.

# Official-left service slot: one continuous opening covers PWRKEY, card access and USB TO UART.
left_service_slot=(cq.Workplane('YZ').center(-4.0,P['module_usb_center_z']).workplane(offset=-L/2-0.2)
                   .rect(P['left_service_slot_length'],P['left_service_slot_height'])
                   .extrude(wall+1.0))
base=base.cut(left_service_slot)

# PCB mounting pillars. PCB hole pattern is derived from the official drawing.
for x in (-P['mount_pitch_x']/2, P['mount_pitch_x']/2):
    for y in (-P['mount_pitch_y']/2, P['mount_pitch_y']/2):
        post = (cq.Workplane('XY').center(x,y).workplane(offset=-H/2+floor)
                .circle(P['standoff_diameter']/2).extrude(P['standoff_height']))
        bore = (cq.Workplane('XY').center(x,y).workplane(offset=-H/2+floor-0.1)
                .circle(P['screw_clearance']/2).extrude(P['standoff_height']+0.2))
        base = base.union(post).cut(bore)

# Front is ALWAYS global -Y, the same edge as the internal raised platform.
# Build cutters in world coordinates; do not use workplane offsets for wall selection.
def cylinder_y(x,z,radius,y0,y1):
    return cq.Workplane('XY').newObject([cq.Solid.makeCylinder(radius,y1-y0,cq.Vector(x,y0,z),cq.Vector(0,1,0))])
front_y=-W/2
# Single antenna bore: former headphone center (20, 7.4), shifted left 3 and up 1 mm.
cz=P['antenna_side_center_z']
cx=P['antenna_side_center_x']
base_clip=cq.Workplane('XY').box(120,120,H)
lid_clip=cq.Workplane('XY').box(120,120,11.7).translate((0,0,H/2+5.85))
lid=rounded_box(L,W,11.7,r).translate((0,0,H/2+5.85))
inner=rounded_box(L-4,W-4,10.2,r-2).translate((0,0,H/2+4.1))
lid=lid.cut(inner)
for cx in (P['antenna_side_center_x'],):
    backing=cylinder_y(cx,cz,7.2,front_y,front_y+3.6)
    base=base.union(backing.intersect(base_clip))
    lid=lid.union(backing.intersect(lid_clip))
panel=cq.Workplane('XY').box(58,0.9,17).edges('|Y').fillet(3).translate((0,front_y+0.35,5.0))
base=base.cut(panel)
lid=lid.cut(panel)
for cx in (P['antenna_side_center_x'],):
    recess=cylinder_y(cx,cz,6.5,front_y-0.2,front_y+2.7)
    bore=cylinder_y(cx,cz,3.1,front_y-0.2,front_y+16)
    base=base.cut(recess).cut(bore)
    lid=lid.cut(recess).cut(bore)
module_usb=cq.Workplane('XY').box(12,17,7).translate((-20,front_y+8,P['module_usb_center_z']))
base=base.cut(module_usb)

# Extra underside thickness maintains roof under the steeper shoulder.
roof=cq.Workplane('XY').box(14,63,4.15).translate((29,0,20.875))
lid=lid.union(roof.intersect(rounded_box(L,W,11.7,r).translate((0,0,H/2+5.85))))

# White top and side returns are cut from the SAME outer envelope as dark carrier.
# This gives flush, interlocking color regions rather than a floating stacked slab.
outline=[(-38,-34),(10,-34),(10,-26),(22,-18),(22,0),(28,6),(28,34),(-38,34)]
mask=cq.Workplane('XY').polyline(outline).close().extrude(5).translate((0,0,19.4))
front_return=cq.Workplane('XY').box(20,8,7).translate((-22,-30,19.5))
rear_return=cq.Workplane('XY').box(32,8,6).translate((-12,30,20))
mask=mask.union(front_return).union(rear_return)
cover=lid.intersect(mask)
lid=lid.cut(mask)
# Right shoulder slopes from white-cover height toward outer edge.
slope_cut=(cq.Workplane('XZ').polyline([(22,22.95),(38,19.75),(38,28),(22,28)]).close().extrude(80,both=True))
lid=lid.cut(slope_cut)
# Three straight through-vents. Their upper ends share one Y coordinate;
# lower ends step upward parallel to the diagonal black/white boundary.
vent_top_y=-11.9
for i in range(3):
    x0=10.0+4.0*i
    vent_bottom_y=-21.5+(2.0/3.0)*(x0-10.0)
    vent=(cq.Workplane('XY')
          .polyline([(x0,vent_bottom_y),(x0+1.3,vent_bottom_y),
                     (x0+1.3,vent_top_y),(x0,vent_top_y)])
          .close().extrude(8).translate((0,0,17)))
    cover=cover.cut(vent)

# Four upper PCB hold-down pillars: left pair belongs to white cover,
# right pair belongs to black carrier. Screws enter from underside of base.
def cylz(x,y,rad,z0,z1):
    return cq.Workplane('XY').center(x,y).workplane(offset=z0).circle(rad).extrude(z1-z0)
for x in (-29.01,29.01):
    for y in (-24.54,24.54):
        post=cylz(x,y,2.75,6.25,21.85)
        pin=cylz(x,y,1.25,0.85,6.35)
        tip=cq.Workplane('XY').newObject([cq.Solid.makeCone(0.95,1.25,0.6,cq.Vector(x,y,0.25),cq.Vector(0,0,1))])
        post=post.union(pin).union(tip)
        # Clearance in the other colored component permits vertical assembly.
        clearance=cylz(x,y,2.95,5.15,21.9)
        if x<0:
            lid=lid.cut(clearance)
            cover=cover.union(post)
        else:
            cover=cover.cut(clearance)
            lid=lid.union(post)
        base=base.union(cylz(x,y,1.35,-8.85,3.65))
        base=base.cut(cylz(x,y,1.45,-1.35,3.75))
lid=lid.cut(slope_cut)
# A quiet edge band on white; carrier shoulder has no scored texture.
for i in range(14):
    groove=cq.Workplane('XY').box(7,0.45,0.65).rotate((0,0,0),(0,0,1),35).translate((-27, -9+i*2,22.85))
    cover=cover.cut(groove)
# Tiny script signature beside the vertical part of the white/black seam.
# Rotate +90 degrees so it reads upright from the right-hand side of the case.
script_font='/System/Library/Fonts/Supplemental/Apple Chancery.ttf'
lettering=(cq.Workplane('XY').text('Ben',3.5,0.8,combine=False,
                                  fontPath=script_font,halign='center',valign='center')
           .rotate((0,0,0),(0,0,1),90))
bb=lettering.val().BoundingBox()
lettering=lettering.translate((27.1-bb.xmax,
                               8.0-bb.ymin,22.40))
cover=cover.cut(lettering)
# A separate interchangeable mascot with one square locating peg.
# Blind sockets retain 0.6 mm of cover material below the bottom of each hole.
mascot=(rounded_box(11,9,0.9,2.3).translate((-3,1,23.40)))
for yy in (-1.0,3.0):
    mascot=mascot.union(rounded_box(2.7,2.5,2.9,0.8).translate((-3,yy,24.7)))
mascot=mascot.union(rounded_box(6.0,5.5,4.8,1.5).translate((-3,1,28.1)))
for yy in (-2.25,4.25):
    mascot=mascot.union(rounded_box(1.8,1.6,3.6,0.65).translate((-3,yy,28.0)))
mascot=mascot.union(rounded_box(6.8,6.5,4.8,1.5).translate((-2.8,1,32.4)))
# Shallow face details, recessed into the +X plane.
for yy in (-0.35,2.35):
    eye=cq.Workplane('YZ').center(yy,33.0).circle(0.48).extrude(0.45).translate((0.3,0,0))
    mascot=mascot.cut(eye)
mouth=cq.Workplane('XY').box(0.5,2.4,0.38).translate((0.35,1,31.55))
mascot=mascot.cut(mouth)
# Internal lid pins are diameter 2.5 into 2.9 mm sockets: 0.4 mm total clearance.
# Match that fit in X and Y for the mascot, while changing only this interface.
peg=cq.Workplane('XY').box(4.0,4.0,1.75).translate((-3,1,22.175))
socket=cq.Workplane('XY').box(4.4,4.4,2.15).translate((-3,1,22.125))
mascot=mascot.union(peg)
cover=cover.cut(socket)
P.update({'mascot_peg_size_xy':[4.0,4.0],'mascot_socket_size_xy':[4.4,4.4],
          'mascot_nominal_clearance_total':0.4,'mascot_pin_depth':1.65})
P.update({'right_shoulder_drop':2.8,'upper_post_bottom':6.25,'upper_post_diameter':5.5,'locating_pin_diameter':2.5,'socket_diameter':2.9,'pin_length':6.0,'engagement_depth':3.4,'socket_bottom_clearance':1.6,'pcb_vertical_allowance':1.1})

# Interface/footprint test frame: cheap first print.
test = rounded_box(L, W, 2.4, r)
frame_wall = ring(L, W, 7.0, r, wall).translate((0,0,4.7))
test = test.union(frame_wall)
# Service openings are excluded from the generic footprint test frame in V0.8.
for x in (-P['mount_pitch_x']/2, P['mount_pitch_x']/2):
    for y in (-P['mount_pitch_y']/2, P['mount_pitch_y']/2):
        post = cq.Workplane('XY').center(x,y).workplane(offset=1.2).circle(P['standoff_diameter']/2).extrude(P['standoff_height'])
        bore = cq.Workplane('XY').center(x,y).workplane(offset=1.1).circle(P['screw_clearance']/2).extrude(P['standoff_height']+0.2)
        test = test.union(post).cut(bore)

parts = {'base':base, 'lid-carrier':lid, 'top-cover':cover}
for name, shape in parts.items():
    exporters.export(shape, str(OUT/f'{name}.step'))
    exporters.export(shape, str(OUT/f'{name}.stl'), tolerance=0.05, angularTolerance=0.1)

(OUT/'parameters.json').write_text(json.dumps(P,ensure_ascii=False,indent=2),encoding='utf-8')
print(OUT.resolve())
