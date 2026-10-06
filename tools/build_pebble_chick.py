# Brown king-penguin-chick restyle of the Pebble character: same skeleton, weights and
# animation set, new proportions, bill, eyes, feet and a fluffy brown down texture.
# Run:  python3 tools/build_pebble_chick.py --out pebble/Pebble_Chick
import bpy, math, os, json, sys
import numpy as np
from scipy.ndimage import zoom
from mathutils import Vector
from math import sin, cos, pi

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
    for k,v in [('Sheen Weight',.3),('Sheen Roughness',.7),('Sheen Tint',(.55,.36,.2,1))]:
        if k in bs.inputs: bs.inputs[k].default_value=v
    return m
navy=fluffy(mat('M_Chick_DownDark',(0.024,0.011,0.004),.85))      # flippers, tail
charcoal=mat('M_Chick_Bill',(0.045,0.04,0.045),.5)              # upper bill
billlow=mat('M_Chick_BillLower',(0.10,0.085,0.085),.5)
orange=mat('M_Chick_Foot',(0.04,0.034,0.034),.65)               # feet and ankles
sole=mat('M_Chick_Sole',(0.04,0.035,0.035),.7)
cream=mat('M_Chick_Iris',(0.11,0.06,0.03),.3)                   # small dark eye
black=mat('M_Chick_Pupil',(0.009,0.008,0.01),.19)
white=mat('M_Chick_Glint',(1,.98,.9),.2)
skin=fluffy(mat('M_Chick_Body',(1,1,1),.8))
# A portable painted base-color map; UV seam is on the back.
def smooth(v): return max(0,min(1,v))**2*(3-2*max(0,min(1,v)))
N=1024
img=bpy.data.images.new('T_Chick_Body_BaseColor',width=N,height=N,alpha=False)
iy,ix=np.mgrid[0:N,0:N].astype(np.float64)
z=.2+1.3*(iy+.5)/N
a=((ix+.5)/N-.5)*2*pi                      # 0 = front (-Y), +-pi = back seam
front=(np.cos(a)+1)/2
rng=np.random.default_rng(7)
def octave(nx,ny,amp):
    g=rng.standard_normal((ny,nx)); return amp*zoom(g,(N/ny,N/nx),order=3,mode='grid-wrap')
fur=octave(6,4,.55)+octave(24,10,.35)+octave(96,24,.28)+octave(384,64,.2)+octave(1024,128,.12)   # vertical streaks
fur=np.clip(fur,-1.6,1.6)
dark=np.array([.13,.065,.028]); light=np.array([.34,.185,.085])
t=np.clip(front**1.3*(1-.35*np.clip((z-1.15)/.3,0,1)),0,1)        # lighter chest, darker back and crown
rgb=dark[None,None,:]*(1-t[...,None])+light[None,None,:]*t[...,None]
rgb=rgb*(1+.22*fur[...,None])
rgb*=1-.18*np.clip((.45-z)/.25,0,1)[...,None]                         # dusty toward the feet
face=(a/.36)**2+((z-1.16)/.11)**2                                       # bare grey skin at the bill base
fm=np.clip((1-face)/.35,0,1); fm=fm*fm*(3-2*fm)
fm*=.75
rgb=rgb*(1-fm[...,None])+np.array([.2,.17,.15])[None,None,:]*fm[...,None]*(1+.06*fur[...,None])
pixels=np.concatenate([np.clip(rgb,0,1),np.ones((N,N,1))],axis=2).ravel().tolist()
img.pixels.foreach_set(pixels); img.filepath_raw=os.path.join(OUT,'T_Chick_Body_BaseColor.png'); img.file_format='PNG'; img.save(); img.pack()
tex=skin.node_tree.nodes.new('ShaderNodeTexImage'); tex.image=img
skin.node_tree.links.new(tex.outputs['Color'],skin.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])

def weights(o,fn):
    for v in o.data.vertices:
        w=fn(v.co/100)
        for name,value in w.items():
            if value>1e-6:
                g=o.vertex_groups.get(name) or o.vertex_groups.new(name=name); g.add([v.index],value,'REPLACE')
def finish(o,m,fn,sub=0):
    move_collection(o,CHAR); o.data.materials.append(m)
    bpy.context.view_layer.objects.active=o
    if sub:
        mod=o.modifiers.new('Rounded surface','SUBSURF'); mod.levels=sub
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in o.data.polygons:p.use_smooth=True
    weights(o,fn); parts.append(o)
    return o
def mesh(name,verts,faces,m,fn,sub=0,uvs=None):
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
    return finish(ob,m,fn,sub)
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
profile=[(.21,.08,.075),(.245,.22,.19),(.30,.315,.267),(.39,.385,.315),(.50,.426,.352),(.63,.44,.367),(.76,.426,.35),(.88,.394,.327),(.97,.353,.30),(1.04,.334,.291),(1.12,.357,.307),(1.22,.376,.32),(1.32,.36,.305),(1.40,.307,.258),(1.455,.222,.183),(1.488,.10,.079),(1.50,.01,.01)]
profile=[(z,rx*(1.07 if .28<z<.97 else .93 if z>=1.2 else 1),ry*(1.07 if .28<z<.97 else .93 if z>=1.2 else 1)) for z,rx,ry in profile]
verts=[]; faces=[]; uvs=[]; seg=64
for z,rx,ry in profile:
    for j in range(seg):
        a=-pi+j*2*pi/seg; verts.append((rx*sin(a),-ry*cos(a),z))
for i in range(len(profile)-1):
    for j in range(seg):
        nj=(j+1)%seg; faces.append((i*seg+j,i*seg+nj,(i+1)*seg+nj,(i+1)*seg+j))
        uvs.append([(j/seg,(profile[i][0]-.2)/1.3),((j+1)/seg,(profile[i][0]-.2)/1.3),((j+1)/seg,(profile[i+1][0]-.2)/1.3),(j/seg,(profile[i+1][0]-.2)/1.3)])
faces+=[tuple(reversed(range(seg))),tuple((len(profile)-1)*seg+j for j in range(seg))]
uvs += [[(.5,0)]*seg,[(.5,1)]*seg]
body=mesh('Body • continuous head and torso',verts,faces,skin,body_w,1,uvs)

def leaf(name,centers,widths,thickness,m,fn,sub=1):
    vs=[]; fs=[]; n=12
    for c,w in zip(centers,widths):
        for j in range(n):
            a=2*pi*j/n; vs.append((c[0]+w*cos(a),c[1]+thickness*w*sin(a),c[2]))
    for i in range(len(centers)-1):
        for j in range(n): fs.append((i*n+j,i*n+(j+1)%n,(i+1)*n+(j+1)%n,(i+1)*n+j))
    fs.extend([tuple(reversed(range(n))),tuple((len(centers)-1)*n+j for j in range(n))])
    return mesh(name,vs,fs,m,fn,sub)

for s,label in [(1,'L'),(-1,'R')]:
    centers=[(s*x,y,z) for x,y,z in [(.322,.015,1.02),(.374,-.001,.985),(.433,-.023,.916),(.50,-.036,.818),(.565,-.046,.701),(.605,-.052,.593),(.61,-.05,.532),(.60,-.05,.517)]]
    def fw(p,L=label):
        t=smooth((.87-p.z)/.24); return {'flipper.'+L:1-t,'flipper_tip.'+L:t}
    leaf('Flipper.'+label,centers,[.025,.065,.092,.099,.085,.057,.025,.004],.48,navy,fw,2)
    # Webbed paddle foot: three rounded scallops on the leading edge.
    outline=[(-.10,.13),(-.155,.035),(-.178,-.16),(-.159,-.245),(-.111,-.272),(-.055,-.245),(0,-.287),(.061,-.27),(.097,-.245),(.144,-.264),(.18,-.212),(.166,-.106),(.116,.10),(.055,.143)]
    vs=[]; fs=[]; count=len(outline)
    for z,k in [(.018,.72),(.025,.96),(.055,1),(.115,.96),(.149,.6),(.16,.22)]:
        for x,y in outline:vs.append((s*.226+s*x*k,-.058+y*k,z))
    for i in range(5):
        for j in range(count):fs.append((i*count+j,i*count+(j+1)%count,(i+1)*count+(j+1)%count,(i+1)*count+j))
    fs += [tuple(reversed(range(count))),tuple(5*count+j for j in range(count))]
    # Mirror winding on right side.
    if s<0:fs=[tuple(reversed(f)) for f in fs]
    def footw(p,L=label):
        t=.7*smooth((-.10-p.y)/.18); return {'foot.'+L:1-t,'toe.'+L:t}
    foot=mesh('Webbed foot.'+label,vs,fs,orange,footw,2)
    foot.data.materials.append(sole)
    for p in foot.data.polygons:
        if p.center.z<4.2:p.material_index=1
    ell('Ankle.'+label,(s*.226,.015,.218),(.095,.098,.135),orange,'leg.'+label)
    ell('Eye.'+label,(s*.15,-.272,1.292),(.064,.042,.080),cream,'head')
    ell('Pupil.'+label,(s*.147,-.305,1.291),(.040,.022,.050),black,'head')
    ell('Eye sparkle.'+label,(s*.147-.011,-.328,1.312),(.012,.007,.015),white,'head',seg=16,rings=12)

# The softly flattened two-part bill provides a readable smile in profile.
# Long slender chick bill, dark with a slightly lighter lower mandible.
ell('Bill upper',(0,-.46,1.138),(.072,.28,.046),charcoal,'head',seg=32)
ell('Bill seam',(0,-.465,1.112),(.066,.262,.009),black,'head',seg=32)
ell('Bill lower',(0,-.45,1.100),(.060,.245,.028),billlow,'head',seg=32)

# No crest on a chick; the 'crest' bone is kept so the skeleton matches Pebble's clips.
leaf('Tail tuft',[(0,.28,.33),(0,.34,.37),(0,.43,.43),(0,.48,.49)],[.12,.13,.10,.002],.5,navy,rigid('tail'),2)

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
light('Fill • sky',(-250,-170,220),2400000,230,(.62,.84,1))
light('Rim',(100,230,350),4600000,200,(.72,1,.91))
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
fbx('SK_Pebble_Chick.fbx')
fbx('AN_Pebble_Chick_Jump.fbx',True)
rig.animation_data.action=idle; scene.frame_end=31; scene.frame_set(1); fbx('AN_Pebble_Chick_Idle.fbx',True)
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
stats={'vertices':len(char.data.vertices),'faces':len(char.data.polygons),'triangles':len(char.data.loop_triangles),'bones':len(arm.bones),'material_slots':len(char.data.materials),'uv_layers':len(char.data.uv_layers),'max_weight_influences':maxinf,'invalid_weight_vertices':len(bad),'dimensions_cm':list(char.dimensions),'animations':{'Pebble_Idle':[1,31],'Pebble_Jump_Test':[1,48]},'variant':'king penguin chick','fps':30,'blender_version':bpy.app.version_string}
open(os.path.join(OUT,'source_stats.json'),'w').write(json.dumps(stats,indent=2))
print('CHICK_STATS',json.dumps(stats),flush=True)
for name,frame,loc,target,scale in [('Preview_Hero',1,(265,-470,235),(0,0,84),225),('Preview_Jump',18,(265,-470,250),(0,0,101),258),('Preview_Front',1,(0,-500,135),(0,0,84),205),('Preview_Back',1,(-220,470,200),(0,0,84),215)]:
    scene.frame_set(frame); cam.location=loc; track(cam,target); camdata.ortho_scale=scale; scene.render.filepath=os.path.join(OUT,name+'.png'); bpy.ops.render.render(write_still=True)
print('CHICK_BUILD_COMPLETE',flush=True)
