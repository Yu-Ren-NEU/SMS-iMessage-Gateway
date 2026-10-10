from pathlib import Path
import cadquery as cq
from cadquery import exporters
O=Path(__file__).resolve().parent
def box(l,w,h,r,xyz):return cq.Workplane('XY').box(l,w,h).edges('|Z').fillet(r).translate(xyz)
def ball(r,xyz):return cq.Workplane('XY').sphere(r).translate(xyz)
def limb(a,b,r):
 v=cq.Vector(*b)-cq.Vector(*a)
 return cq.Workplane('XY').newObject([cq.Solid.makeCylinder(r,v.Length,cq.Vector(*a),v.normalized())]).union(ball(r,a)).union(ball(r,b))
def base():
 return box(21,18,1.4,3,(0,0,.7)).union(cq.Workplane('XY').box(4.2,4.2,1.85).translate((0,0,-.725)).edges('<Z').chamfer(.25))
def face_eyes(s,x,z,spacing,r=.85):
 for y in [-spacing,spacing]:s=s.cut(cq.Workplane('YZ').center(y,z).circle(r).extrude(1.8).translate((x,0,0)))
 return s
cat=base().union(box(10,10.5,8,2.5,(-1.4,0,6.2)))
for y in [-3.4,3.4]:cat=cat.union(box(6.6,4.8,3.8,1.5,(3.3,y,3.1)))
cat=cat.union(box(10,13.3,9.5,2.5,(-.6,0,14.8)))
for y in [-4.4,4.4]:
 ear=cq.Workplane('XY').newObject([cq.Solid.makeCone(2.55,.45,4.8,cq.Vector(-.6,y,19.1),cq.Vector(0,0,1))])
 cat=cat.union(ear)
cat=face_eyes(cat,3.2,15.8,2.5)
nose=cq.Workplane('YZ').polyline([(-.9,14.3),(.9,14.3),(0,13.5)]).close().extrude(1.8).translate((3.2,0,0));cat=cat.cut(nose)
# Small W-shaped cat smile, cut 1.2 mm into the face.
import math
smile=[(-1.5,13.2),(-.75,12.65),(0,13.15),(.75,12.65),(1.5,13.2)]
for a,b in zip(smile,smile[1:]):
 dy,dz=b[0]-a[0],b[1]-a[1]
 cutter=(cq.Workplane('XY').box(1.8,math.hypot(dy,dz)+.25,.55)
         .rotate((0,0,0),(1,0,0),math.degrees(math.atan2(dz,dy)))
         .translate((4.0,(a[0]+b[0])/2,(a[1]+b[1])/2)))
 cat=cat.cut(cutter)
for sign in [-1,1]:
 for dz in [-.8,.8]:
  cat=cat.cut(cq.Workplane('XY').box(.65,2.0,.35).rotate((0,0,0),(1,0,0),sign*dz*12).translate((4.15,sign*4.1,14.2+dz)))
# Tail curls around the rear and side, continuously joined to the body/base.
pts=[(-4.7,3,3),(-6.6,4.5,2.7),(-7.3,6,2.4),(-5.7,7.1,2.3),(-2.9,7.0,2.3),(-1.4,5.7,2.4)]
for a,b in zip(pts,pts[1:]):cat=cat.union(limb(a,b,1.2))
tv=base()
for y in [-3.4,3.4]:
 tv=tv.union(box(6.5,4.5,3.0,1.2,(2.1,y,2.7))).union(limb((0,y,3),(0,y,8.6),1.8))
tv=tv.union(box(10.4,14.4,11.5,2.0,(-.8,0,13.8)))
screen=cq.Workplane('XY').box(2.1,10.0,7.0).edges('|X').fillet(1.4).translate((4.4,0,14.2));tv=tv.cut(screen)
tv=face_eyes(tv,2.25,15.1,2.1,.8)
tv=tv.cut(cq.Workplane('XY').box(1.9,3.6,.8).translate((2.9,0,12.6)))
for y in [-1,1]:tv=tv.union(limb((-.4,y*6.9,11),(1.5,y*7.3,7.4),1.25))
for y in [-1,1]:tv=tv.union(limb((-1,y*1.5,19.2),(-1.6,y*4.7,23.0),1.05))
# Rear ventilation engraved on the television shell.
for y in [-3.8,-1.9,0,1.9,3.8]:tv=tv.cut(cq.Workplane('XY').box(.6,.65,4).translate((-5.85,y,14)))
for n,s in [('cat-plugin',cat),('tv-plugin',tv)]:
 assert len(s.solids().vals())==1 and s.val().isValid(),n
 exporters.export(s,str(O/(n+'.stl')),tolerance=.035,angularTolerance=.08)
 b=s.val().BoundingBox();print(n,'valid single solid; size mm',b.xlen,b.ylen,b.zlen)
