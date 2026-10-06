import bpy,os,json,bmesh
P=os.path.join(os.path.dirname(__file__),'Pebble_Penguin')
bpy.ops.wm.open_mainfile(filepath=os.path.join(P,'Pebble_Penguin.blend'))
s=bpy.context.scene;o=bpy.data.objects['SK_Pebble']
bm=bmesh.new();bm.from_mesh(o.data)
audit={'nonmanifold_edges':sum(not e.is_manifold for e in bm.edges),'loose_vertices':sum(not v.link_edges for v in bm.verts),'zero_area_faces':sum(f.calc_area()<1e-8 for f in bm.faces),'connected_surface_islands':None,'note':'One skinned object contains intersecting closed surface pieces for eyes, bill, feathers and limbs. These are intentionally not welded to the continuous torso/head.'}
bm.free()
seen=set();islands=0;adj={v.index:[] for v in o.data.vertices}
for e in o.data.edges:a,b=e.vertices;adj[a].append(b);adj[b].append(a)
for v in adj:
 if v in seen:continue
 islands+=1;stack=[v];seen.add(v)
 while stack:
  for n in adj[stack.pop()]:
   if n not in seen:seen.add(n);stack.append(n)
audit['connected_surface_islands']=islands
open(os.path.join(P,'topology_audit.json'),'w').write(json.dumps(audit,indent=2))
s.cycles.samples=24;s.render.resolution_x=800;s.render.resolution_y=800;s.frame_set(9);s.render.filepath=os.path.join(P,'Preview_Crouch.png');bpy.ops.render.render(write_still=True)
s.render.resolution_x=520;s.render.resolution_y=520;s.cycles.samples=12;s.camera.data.ortho_scale=260
from mathutils import Vector
s.camera.location=(265,-470,250);s.camera.rotation_euler=(Vector((0,0,101))-s.camera.location).to_track_quat('-Z','Y').to_euler()
frames=os.path.join(P,'animation_frames');os.makedirs(frames,exist_ok=True)
for f in range(1,49,3):
 s.frame_set(f);s.render.filepath=os.path.join(frames,f'{f:03d}.png');bpy.ops.render.render(write_still=True)
print('EXTRAS_COMPLETE',json.dumps(audit),flush=True)
