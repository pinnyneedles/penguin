# Brown king-penguin-chick variant of the Pebble character: same skeleton, weights scheme and
# animation set. Geometry (pear body, down tufts, bill, eyes, feet) comes from chick_geometry.py.
# Run:  python3 tools/build_pebble_chick.py --out pebble/Pebble_Chick
import bpy, math, os, json, sys
import numpy as np
from scipy.ndimage import zoom
from mathutils import Vector
from math import sin, cos, pi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chick_geometry as G
V3 = set(filter(None, os.environ.get('CHICK_V3', '').split(',')))     # iteration-3 candidates: shape, surface
print('CHICK_V3', sorted(V3), flush=True)
PROF = G.Profile(G.CTRL_V3 if 'shape' in V3 else G.CTRL)
FIELD = G.TuftField(PROF, soft='surface' in V3)
FINE = G.TuftField(PROF, seed=23, size_fn=G.fine_tuft_size, soft=True) if 'surface' in V3 else None

argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
OUT=os.path.abspath(argv[argv.index('--out')+1]) if '--out' in argv else os.path.join(os.getcwd(),'pebble','Pebble_Chick')
os.makedirs(OUT,exist_ok=True)
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
for block in list(bpy.data.collections):
    if block.name!='Collection': bpy.data.collections.remove(block)
scene=bpy.context.scene
scene.unit_settings.system='METRIC'; scene.unit_settings.scale_length=0.01
scene.render.fps=30
CHAR=bpy.data.collections.new('CHARACTER • export mesh + skeleton'); scene.collection.children.link(CHAR)
STUDIO=bpy.data.collections.new('STUDIO • excluded from FBX'); scene.collection.children.link(STUDIO)
parts=[]
def move_collection(o,c):
    for col in list(o.users_collection): col.objects.unlink(o)
    c.objects.link(o)
def mat(name,color,rough=.45):
    m=bpy.data.materials.new(name); m.diffuse_color=(*color,1); m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF'); bs.inputs['Base Color'].default_value=(*color,1); bs.inputs['Roughness'].default_value=rough
    return m
def fluffy(m):
    bs=m.node_tree.nodes.get('Principled BSDF')
    for k,v in ([('Sheen Weight',.22),('Sheen Roughness',.6),('Sheen Tint',(.55,.38,.24,1))] if 'surface' in V3 else [('Sheen Weight',.15),('Sheen Roughness',.7),('Sheen Tint',(.35,.22,.12,1))]):
        if k in bs.inputs: bs.inputs[k].default_value=v
    return m
navy=fluffy(mat('M_Chick_DownDark',(0.024,0.011,0.004),.85))      # flippers, tail
charcoal=mat('M_Chick_Bill',(0.022,0.019,0.021),.32)            # glossy near-black upper bill
billlow=mat('M_Chick_BillLower',(0.05,0.043,0.043),.38)
orange=mat('M_Chick_Foot',(0.052,0.050,0.053),.70) if 'surface' in V3 else mat('M_Chick_Foot',(0.04,0.034,0.034),.65)   # feet, legs, eyelids
sole=mat('M_Chick_Claw',(0.075,0.07,0.065),.35)
cream=mat('M_Chick_Iris',(0.030,0.016,0.009),.12)               # dark brown-black glossy eye                   # small dark eye
black=mat('M_Chick_Pupil',(0.009,0.008,0.01),.19)
white=mat('M_Chick_Glint',(1,.98,.9),.2)
skin=fluffy(mat('M_Chick_Body',(1,1,1),.8))
# A portable painted base-color map; UV seam is on the back.
def smooth(v): return max(0,min(1,v))**2*(3-2*max(0,min(1,v)))
N=1024
img=bpy.data.images.new('T_Chick_Body_BaseColor',width=N,height=N,alpha=False)
if 'surface' in V3:
    rgb,ngl,ndx=G.body_texture_v3(PROF,FIELD,FINE,N=N)
else:
    rgb=G.body_texture(PROF,FIELD,N=N); ngl=None
pixels=np.concatenate([rgb,np.ones((N,N,1))],axis=2).ravel().tolist()
img.pixels.foreach_set(pixels); img.filepath_raw=os.path.join(OUT,'T_Chick_Body_BaseColor.png'); img.file_format='PNG'; img.save(); img.pack()
tex=skin.node_tree.nodes.new('ShaderNodeTexImage'); tex.image=img
skin.node_tree.links.new(tex.outputs['Color'],skin.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
if ngl is not None:
    from PIL import Image as _PI
    nimg=bpy.data.images.new('T_Chick_Body_Normal',width=N,height=N,alpha=False)
    nimg.colorspace_settings.name='Non-Color'     # set before writing pixels; changing it later clears them
    nimg.pixels.foreach_set(np.concatenate([ngl,np.ones((N,N,1))],axis=2).ravel().tolist())
    nimg.filepath_raw=os.path.join(OUT,'T_Chick_Body_Normal_GL.png'); nimg.file_format='PNG'; nimg.save(); nimg.pack()
    _PI.fromarray((np.flipud(ndx)*255+.5).astype(np.uint8)).save(os.path.join(OUT,'T_Chick_Body_Normal_DX.png'))
    nt=skin.node_tree; ntex=nt.nodes.new('ShaderNodeTexImage'); ntex.image=nimg
    nmap=nt.nodes.new('ShaderNodeNormalMap'); nmap.inputs['Strength'].default_value=1.0
    nt.links.new(ntex.outputs['Color'],nmap.inputs['Color']); nt.links.new(nmap.outputs['Normal'],nt.nodes.get('Principled BSDF').inputs['Normal'])

def weights(o,fn):
    for v in o.data.vertices:
        w=fn(v.co/100)
        for name,value in w.items():
            if value>1e-6:
                g=o.vertex_groups.get(name) or o.vertex_groups.new(name=name); g.add([v.index],value,'REPLACE')
DOWN_TEX=bpy.data.textures.new('Down lumps','CLOUDS'); DOWN_TEX.noise_scale=3.0; DOWN_TEX.noise_depth=2
def finish(o,m,fn,sub=0,disp=0):
    move_collection(o,CHAR); o.data.materials.append(m)
    bpy.context.view_layer.objects.active=o
    if sub:
        mod=o.modifiers.new('Rounded surface','SUBSURF'); mod.levels=sub
        bpy.ops.object.modifier_apply(modifier=mod.name)
    if disp:
        mod=o.modifiers.new('Down','DISPLACE'); mod.texture=DOWN_TEX; mod.strength=disp; mod.mid_level=.5
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in o.data.polygons:p.use_smooth=True
    weights(o,fn); parts.append(o)
    return o
def mesh(name,verts,faces,m,fn,sub=0,uvs=None,disp=0):
    me=bpy.data.meshes.new(name); me.from_pydata([Vector(v)*100 for v in verts],[],faces); me.update()
    ob=bpy.data.objects.new(name,me); scene.collection.objects.link(ob)
    if uvs:
        uv=me.uv_layers.new(name='UVMap')
        for p,coords in zip(me.polygons,uvs):
            for li,co in zip(p.loop_indices,coords):uv.data[li].uv=co
    else:
        uv=me.uv_layers.new(name='UVMap')
        for p in me.polygons:
            for li in p.loop_indices:
                v=me.vertices[me.loops[li].vertex_index].co/100
                uv.data[li].uv=((v.x+1)/2,(v.z+.1)/2)
    return finish(ob,m,fn,sub,disp)
def rigid(b):return lambda p:{b:1}
def ell(name,loc,scale,m,bone,rot=(0,0,0),seg=24,rings=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg,ring_count=rings,location=Vector(loc)*100)
    o=bpy.context.object; o.name=name; o.scale=Vector(scale)*100; o.rotation_euler=rot
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    # Weight by world position to match generated geometry helpers.
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=False)
    return finish(o,m,rigid(bone))
def body_w(p):
    h=smooth((p.z-.96)/.23); b=smooth((p.z-.38)/.38)
    return {'pelvis':(1-b)*(1-h),'body':b*(1-h),'head':h}
# Pear-shaped body, neck and head as one continuous surface, displaced by real down tufts.
verts,faces,uvs,info=G.body_mesh(PROF,FIELD,amp_scale=0.62 if 'surface' in V3 else 1.0)
print('BODY',info,flush=True)
body=mesh('Body • continuous head and torso, tufted down',verts,faces,skin,body_w,0,uvs)

def leaf(name,centers,widths,thickness,m,fn,sub=1,flat_x=False,disp=0):
    vs=[]; fs=[]; n=12
    for c,w in zip(centers,widths):
        for j in range(n):
            a=2*pi*j/n
            vs.append((c[0]+thickness*w*cos(a),c[1]+w*sin(a),c[2]) if flat_x else (c[0]+w*cos(a),c[1]+thickness*w*sin(a),c[2]))
    for i in range(len(centers)-1):
        for j in range(n): fs.append((i*n+j,i*n+(j+1)%n,(i+1)*n+(j+1)%n,(i+1)*n+j))
    fs.extend([tuple(reversed(range(n))),tuple((len(centers)-1)*n+j for j in range(n))])
    return mesh(name,vs,fs,m,fn,sub,disp=disp)

def torus(name,center,normal,major,minor,m,bone):
    bpy.ops.mesh.primitive_torus_add(major_radius=major*100,minor_radius=minor*100,major_segments=28,minor_segments=8,
        location=Vector(center)*100,rotation=Vector(normal).to_track_quat('Z','Y').to_euler())
    o=bpy.context.object; o.name=name
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    return finish(o,m,rigid(bone))

_,EYES=G.anchors(PROF)
for s,label in [(1,'L'),(-1,'R')]:
    centers,widths=(G.flipper_centres_v3 if 'shape' in V3 else G.flipper_centres)(PROF,s)
    def fw(p,L=label):
        t=smooth((.87-p.z)/.24); return {'flipper.'+L:1-t,'flipper_tip.'+L:t}
    leaf('Flipper.'+label,[tuple(c) for c in centers],widths,.40 if 'shape' in V3 else .30,skin,fw,1,flat_x=True,disp=1.5 if 'shape' in V3 else 1.2)   # same down material as the body
    # Feet: three splayed toes with knuckles, hooked claws and scalloped webbing.
    def footw(p,L=label):
        t=.7*smooth((-.10-p.y)/.18); return {'foot.'+L:1-t,'toe.'+L:t}
    toes,claws,webs=G.foot_parts(s)
    for k,(vs,fs) in enumerate(toes): mesh(f'Toe {k+1}.'+label,vs,fs,orange,footw,1)
    for k,(vs,fs) in enumerate(claws): mesh(f'Claw {k+1}.'+label,vs,fs,sole,footw,0)
    for k,(vs,fs) in enumerate(webs): mesh(f'Web {k+1}.'+label,vs,fs,orange,footw,1)
    ell('Foot pad.'+label,(s*.226,-.045,.045),(.080,.090,.042),orange,'foot.'+label,seg=16,rings=10)
    if 'shape' in V3:
        vs,fs=G.tarsus(s)
        def legw(p,L=label):
            t=smooth((.12-p.z)/.07); return {'leg.'+L:1-t,'foot.'+L:t}
        mesh('Leg.'+label,vs,fs,orange,legw,1)
    else:
        ell('Ankle.'+label,(s*.226,.0,.17),(.075,.08,.12),orange,'leg.'+label,seg=16,rings=10)
    # Small dark eye set into the head under a lid of bare skin.
    P,n=EYES[label]; P=Vector(P); n=Vector(n).normalized()
    up=Vector((0,0,1)); side=n.cross(up).normalized()
    # Dark, glossy eye set a little deeper, round pupil, and a thin low lid of bare skin.
    E=P-n*.014
    ell('Eye.'+label,tuple(E),(.030,.030,.030),cream,'head',seg=20,rings=14)
    ell('Pupil.'+label,tuple(E+n*.018),(.017,.017,.017),black,'head',seg=16,rings=10)
    ell('Eye glint.'+label,tuple(E+n*.0302+up*.009+side*.006*s),(.0034,.0034,.0034),white,'head',seg=12,rings=8)
    torus('Eyelid.'+label,tuple(P-n*.004),tuple(n),.0312,.0048,orange,'head')

# Long, slender, slightly decurved bill in two mandibles.
(uv_,uf_),(lv_,lf_)=G.bill(PROF)
mesh('Bill upper',uv_,uf_,charcoal,rigid('head'),1)
mesh('Bill lower',lv_,lf_,billlow,rigid('head'),1)

# No crest on a chick; the 'crest' bone is kept so the skeleton matches Pebble's clips.
leaf('Tail tuft',[(0,.36,.30),(0,.40,.32),(0,.44,.35)],[.07,.06,.002],.5,skin,rigid('tail'),1,disp=.6)

# Correct face winding/normals and consolidate to one skinned mesh.
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=body; bpy.ops.object.join(); char=body; char.name='SK_Pebble_Chick'; char.data.name='PebbleChick_DeformMesh'
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.mesh.normals_make_consistent(inside=False); bpy.ops.object.mode_set(mode='OBJECT')
# Skeleton: root stays on ground, all animated transforms are relative to rest.
arm=bpy.data.armatures.new('Pebble_Skeleton'); rig=bpy.data.objects.new('Pebble_Rig',arm); CHAR.objects.link(rig)
bpy.context.view_layer.objects.active=rig; char.select_set(False); rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
def bone(n,h,t,parent=None):
    b=arm.edit_bones.new(n); b.head=Vector(h)*100; b.tail=Vector(t)*100
    if parent:b.parent=arm.edit_bones[parent]
    return b
bone('root',(0,0,0),(0,0,.15))
bone('pelvis',(0,0,.32),(0,0,.64),'root'); bone('body',(0,0,.64),(0,0,1.04),'pelvis'); bone('head',(0,0,1.04),(0,0,1.46),'body')
bone('crest',(0,0,1.46),(0,.1,1.65),'head'); bone('tail',(0,.23,.34),(0,.47,.48),'pelvis')
for s,L in [(1,'L'),(-1,'R')]:
    bone('flipper.'+L,(s*.32,0,1.0),(s*.50,-.035,.80),'body')
    bone('flipper_tip.'+L,(s*.50,-.035,.80),(s*.61,-.05,.53),'flipper.'+L)
    bone('leg.'+L,(s*.226,0,.34),(s*.226,0,.13),'pelvis')
    bone('foot.'+L,(s*.226,0,.13),(s*.226,-.18,.08),'leg.'+L)
    bone('toe.'+L,(s*.226,-.18,.08),(s*.226,-.32,.06),'foot.'+L)
bpy.ops.object.mode_set(mode='OBJECT'); rig.show_in_front=True; arm.display_type='OCTAHEDRAL'
char.parent=rig; mod=char.modifiers.new('Deform • Pebble_Skeleton','ARMATURE'); mod.object=rig; mod.use_deform_preserve_volume=False
for p in rig.pose.bones:p.rotation_mode='XYZ'
rig['Design']='PEBBLE CHICK | brown king-penguin-chick restyle of Pebble | same skeleton'
rig['Units']='centimeters; +Z up; character faces -Y in Blender; FBX converts to +X forward'
rig['Animation']='Jump_Test: 1-48 at 30 fps; pelvis motion; root stationary'

def reset():
    for p in rig.pose.bones:p.location=(0,0,0); p.rotation_euler=(0,0,0); p.scale=(1,1,1)
def animate(name,keys,end):
    rig.animation_data_create(); action=bpy.data.actions.new(name); rig.animation_data.action=action
    for f,vals in keys:
        reset()
        for n,props in vals.items():
            p=rig.pose.bones[n]
            for prop,val in props.items():setattr(p,prop,val)
        # Pin the feet during crouch/landing; the short legs absorb the body dip.
        if rig.pose.bones['pelvis'].location.y < 0:
            for side in ['L','R']:
                rig.pose.bones['leg.'+side].location.y=rig.pose.bones['pelvis'].location.y
        for p in rig.pose.bones:
            p.keyframe_insert('location',frame=f,group=p.name); p.keyframe_insert('rotation_euler',frame=f,group=p.name); p.keyframe_insert('scale',frame=f,group=p.name)
    action.use_fake_user=True
    return action
idle=animate('Pebble_Idle',[(1,{}),(16,{'body':{'rotation_euler':(.02,0,0)},'head':{'rotation_euler':(-.025,.015,.015)},'flipper.L':{'rotation_euler':(0,.04,0)},'flipper.R':{'rotation_euler':(0,-.04,0)}}),(31,{})],31)
jump=animate('Pebble_Jump_Test',[(1,{}),(9,{'pelvis':{'location':(0,-9,0)},'body':{'rotation_euler':(.10,0,0)},'head':{'rotation_euler':(-.10,0,0)},'flipper.L':{'rotation_euler':(.1,0,-.16)},'flipper.R':{'rotation_euler':(.1,0,.16)}}),(18,{'pelvis':{'location':(0,29,0)},'flipper.L':{'rotation_euler':(0,0,-.85)},'flipper.R':{'rotation_euler':(0,0,.85)},'flipper_tip.L':{'rotation_euler':(.10,0,-.12)},'flipper_tip.R':{'rotation_euler':(.10,0,.12)},'foot.L':{'rotation_euler':(.3,0,0)},'foot.R':{'rotation_euler':(.3,0,0)},'head':{'rotation_euler':(-.07,0,-.06)},'crest':{'rotation_euler':(.12,0,0)}}),(27,{'pelvis':{'location':(0,38,0)},'flipper.L':{'rotation_euler':(0,0,-.67)},'flipper.R':{'rotation_euler':(0,0,.67)},'foot.L':{'rotation_euler':(-.22,0,0)},'foot.R':{'rotation_euler':(-.22,0,0)},'toe.L':{'rotation_euler':(.15,0,0)},'toe.R':{'rotation_euler':(.15,0,0)}}),(38,{'pelvis':{'location':(0,-7,0)},'body':{'rotation_euler':(.08,0,0)},'flipper.L':{'rotation_euler':(0,0,-.24)},'flipper.R':{'rotation_euler':(0,0,.24)}}),(48,{})],48)
rig.animation_data.action=jump; scene.frame_start=1; scene.frame_end=48; scene.frame_set(1)
for n,f in [('REST',1),('ANTICIPATION',9),('TAKEOFF',18),('APEX',27),('LAND',38),('RECOVER',48)]:scene.timeline_markers.new(n,frame=f)

# Studio lighting, kept outside the export selection.
groundmat=mat('STUDIO • stone',(.30,.30,.29),.85)
bpy.ops.mesh.primitive_plane_add(size=20000,location=(0,0,-.4)); ground=bpy.context.object; ground.name='Studio floor'; ground.data.materials.append(groundmat); move_collection(ground,STUDIO)
def track(o,p):o.rotation_euler=(Vector(p)-o.location).to_track_quat('-Z','Y').to_euler()
def light(name,loc,energy,size,color):
    d=bpy.data.lights.new(name,'AREA'); d.energy=energy; d.shape='DISK'; d.size=size; d.color=color
    o=bpy.data.objects.new(name,d); STUDIO.objects.link(o); o.location=loc; track(o,(0,0,85))
light('Key • warm softbox',(260,-350,430),3700000,280,(1,.86,.7))
light('Fill • sky',(-250,-170,220),2400000,230,(.82,.88,1))
light('Rim',(100,230,350),4600000,200,(1,.94,.86))
world=bpy.data.worlds.new('Lagoon studio'); scene.world=world; world.use_nodes=True; world.node_tree.nodes['Background'].inputs[0].default_value=(.42,.46,.50,1); world.node_tree.nodes['Background'].inputs[1].default_value=.45
camdata=bpy.data.cameras.new('Preview camera'); cam=bpy.data.objects.new('Preview camera',camdata); STUDIO.objects.link(cam); scene.camera=cam
camdata.type='ORTHO'; camdata.ortho_scale=225; camdata.clip_end=100000; cam.location=(265,-470,235); track(cam,(0,0,84))
scene.render.engine='CYCLES'; scene.cycles.samples=32; scene.cycles.use_denoising=True; scene.cycles.device='CPU'
scene.render.resolution_x=800; scene.render.resolution_y=800; scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX'; scene.render.image_settings.file_format='PNG'
# Select only the character when exporting; no lights/cameras/ground or leaf bones.
def selection():
    bpy.ops.object.select_all(action='DESELECT'); rig.select_set(True); char.select_set(True); bpy.context.view_layer.objects.active=rig
def fbx(name,animated=False):
    selection()
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT,name),use_selection=True,object_types={'ARMATURE','MESH'},global_scale=1,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',axis_forward='X',axis_up='Z',use_space_transform=True,bake_space_transform=False,add_leaf_bones=False,primary_bone_axis='Y',secondary_bone_axis='X',use_armature_deform_only=True,use_mesh_modifiers=True,mesh_smooth_type='FACE',use_tspace=True,bake_anim=animated,bake_anim_use_all_bones=True,bake_anim_use_nla_strips=False,bake_anim_use_all_actions=False,bake_anim_force_startend_keying=True,bake_anim_step=1,bake_anim_simplify_factor=0,path_mode='COPY',embed_textures=True)
rig.name='Armature'   # Unreal drops a root node named "Armature" instead of adding it as an extra bone
fbx('SK_Pebble_Chick.fbx')   # animation clips are authored and exported by tools/make_chick_anims.py
rig.animation_data.action=jump; scene.frame_end=48; scene.frame_set(1)
selection()
for area in (bpy.context.screen.areas if bpy.context.screen else []):
    if area.type=='VIEW_3D':
        area.spaces.active.region_3d.view_distance=310; area.spaces.active.region_3d.view_location=(0,0,85)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT,'Pebble_Chick.blend'))
char.data.calc_loop_triangles()
bad=[]; maxinf=0
for v in char.data.vertices:
    total=sum(g.weight for g in v.groups); maxinf=max(maxinf,len(v.groups))
    if abs(total-1)>1e-4:bad.append(v.index)
stats={'vertices':len(char.data.vertices),'faces':len(char.data.polygons),'triangles':len(char.data.loop_triangles),'bones':len(arm.bones),'material_slots':len(char.data.materials),'uv_layers':len(char.data.uv_layers),'max_weight_influences':maxinf,'invalid_weight_vertices':len(bad),'dimensions_cm':list(char.dimensions),'animations':'see anim_stats.json (authored by tools/make_chick_anims.py)','variant':'king penguin chick','fps':30,'blender_version':bpy.app.version_string}
open(os.path.join(OUT,'source_stats.json'),'w').write(json.dumps(stats,indent=2))
print('CHICK_STATS',json.dumps(stats),flush=True)
for name,frame,loc,target,scale in ([] if '--no-previews' in argv else [('Preview_Hero',1,(265,-470,235),(0,0,84),225),('Preview_Front',1,(0,-500,135),(0,0,84),205),('Preview_Back',1,(-220,470,200),(0,0,84),215),('Preview_Side',1,(520,-30,120),(0,0,80),200)]):
    scene.frame_set(frame); cam.location=loc; track(cam,target); camdata.ortho_scale=scale; scene.render.filepath=os.path.join(OUT,name+'.png'); bpy.ops.render.render(write_still=True)
print('CHICK_BUILD_COMPLETE',flush=True)
