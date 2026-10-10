from pathlib import Path
import cadquery as cq
from cadquery import exporters
O=Path(__file__).resolve().parent;O.mkdir(parents=True,exist_ok=True)
def box(l,w,h,r,xyz):return cq.Workplane('XY').box(l,w,h).edges('|Z').fillet(r).translate(xyz)
def ball(r,xyz):return cq.Workplane('XY').sphere(r).translate(xyz)
def limb(a,b,r):
 v=cq.Vector(*b)-cq.Vector(*a)
 return cq.Workplane('XY').newObject([cq.Solid.makeCylinder(r,v.Length,cq.Vector(*a),v.normalized())]).union(ball(r,a)).union(ball(r,b))
# Local z=0 is the existing top-cover seating plane.
s=box(21,18,1.4,3,(0,0,.7))
peg=cq.Workplane('XY').box(4.2,4.2,1.85).translate((0,0,-.725)).edges('<Z').chamfer(.25)
s=s.union(peg)
# Seated boots, bent legs, rounded suit and backpack.
for y in [-3.9,3.9]:
 s=s.union(box(8,5.5,3.6,1.6,(3.8,y,2.8)))
 s=s.union(limb((-1,y,5),(3.5,y,4),2.25))
s=s.union(box(8.5,9.4,9,2.2,(-1.8,0,8.6)))
s=s.union(box(3.5,7.0,7,1.1,(-6.2,0,8.5)))
s=s.union(ball(6.4,(-1.3,0,17.4)))
# Recessed visor on the face toward +X.
visor=cq.Workplane('XY').box(4.8,8.7,5.6).edges('|X').fillet(2.2).translate((5.65,0,17.7))
s=s.cut(visor)
for y in [-1.8,1.8]:
 eye=cq.Workplane('YZ').center(y,18.1).circle(.8).extrude(1.6).translate((2.15,0,0))
 s=s.cut(eye)
s=s.cut(cq.Workplane('XY').box(1.8,3.0,.8).translate((2.8,0,16.8)))
# Both arms embrace a planet; ring is thick enough to read in a small print.
for y in [-1,1]:
 s=s.union(limb((-.4,y*5.1,10.3),(4.1,y*3.0,9.8),1.55))
 s=s.union(ball(1.65,(5.2,y*2.5,9.8)))
s=s.union(ball(3.15,(6.0,0,10)))
ring=cq.Workplane('XY').circle(4.1).circle(2.7).extrude(1.0,both=True).rotate((0,0,0),(0,1,0),-22).translate((6,0,10))
s=s.union(ring)
# Shallow seam across boots and backpack, away from the plug.
for y in [-3.9,3.9]:s=s.cut(cq.Workplane('XY').box(.55,4.7,.4).translate((5,y,4.5)))
assert len(s.solids().vals())==1 and s.val().isValid()
exporters.export(s,str(O/'astronaut-plugin.stl'),tolerance=.035,angularTolerance=.08)
b=s.val().BoundingBox();print('valid single solid; size mm',b.xlen,b.ylen,b.zlen,'peg 4.2x4.2; insertion 1.65')
