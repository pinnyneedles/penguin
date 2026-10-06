import bpy, math, os, json
from mathutils import Vector
from math import sin, cos, pi

OUT=os.path.join(os.path.dirname(__file__),'Pebble_Penguin')
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
navy=mat('M_Pebble_Ink',(0.018,0.075,0.14))
teal=mat('M_Pebble_Lagoon',(0.035,0.48,0.46))
cream=mat('M_Pebble_Vanilla',(0.96,0.85,0.61))
orange=mat('M_Pebble_Tangerine',(0.98,0.32,0.08))
sole=mat('M_Pebble_Coral',(0.72,0.10,0.055))
black=mat('M_Pebble_Eye',(0.009,0.016,0.03),.19)
white=mat('M_Pebble_Glint',(1,.98,.87),.2)
skin=mat('M_Pebble_Body',(1,1,1))
# A portable painted base-color map; UV seam is on the back.
N=1024
img=bpy.data.images.new('T_Pebble_Body_BaseColor',width=N,height=N,alpha=False)
pixels=[]
def smooth(v): return max(0,min(1,v))**2*(3-2*max(0,min(1,v)))
for iy in range(N):
    z=.2+1.3*(iy+.5)/N
    for ix in range(N):
        a=((ix+.5)/N-.5)*2*pi
        face=(a/1.10)**2+((z-1.265)/.224)**2
        bib=(a/1.03)**2+((z-.704)/.497)**2
        mask=smooth((1-min(face,bib))/.045)
        base=(.065,.23,.34); light=(.98,.91,.74)
        pixels.extend([base[k]*(1-mask)+light[k]*mask for k in range(3)]+[1])
img.pixels.foreach_set(pixels); img.filepath_raw=os.path.join(OUT,'T_Pebble_Body_BaseColor.png'); img.file_format='PNG'; img.save(); img.pack()
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
    ell('Eye white.'+label,(s*.147,-.285,1.292),(.104,.062,.133),cream,'head')
    ell('Pupil.'+label,(s*.14,-.343,1.289),(.053,.027,.075),black,'head')
    ell('Eye sparkle.'+label,(s*.14-.014,-.365,1.326),(.018,.010,.024),white,'head',seg=16,rings=12)
    ell('Eye sparkle small.'+label,(s*.14+.017,-.365,1.272),(.008,.005,.011),white,'head',seg=12,rings=8)
    ell('Expressive brow.'+label,(s*.151,-.28,1.422),(.079,.025,.026),navy,'head',rot=(0,s*.12,s*-.14))

# The softly flattened two-part bill provides a readable smile in profile.
ell('Bill upper',(0,-.362,1.135),(.163,.162,.072),orange,'head',seg=32)
ell('Smile seam',(0,-.373,1.105),(.146,.145,.014),black,'head',seg=32)
ell('Bill lower',(0,-.374,1.086),(.136,.135,.039),sole,'head',seg=32)
for s in [-1,1]: ell('Nostril',(s*.049,-.491,1.159),(.012,.007,.007),sole,'head',seg=12,rings=8)

for k,(x,height,sweep) in enumerate([(-.11,1.605,.06),(0,1.692,.12),(.102,1.627,.135)]):
    leaf('Crest feather '+str(k+1),[(x,.025,1.425),(x,.015,1.48),(x+.012,.035,1.54),(x+.025,sweep,height-.025),(x+.03,sweep+.04,height)],[.026,.056,.055,.029,.002],.48,teal,rigid('crest'),2)
leaf('Tail tuft',[(0,.28,.33),(0,.34,.37),(0,.43,.43),(0,.48,.49)],[.12,.13,.10,.002],.5,navy,rigid('tail'),2)

# Correct face winding/normals and consolidate to one skinned mesh.
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=body; bpy.ops.object.join(); char=body; char.name='SK_Pebble'; char.data.name='Pebble_DeformMesh'
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
rig['Design']='PEBBLE | original lagoon penguin | platformer prototype'
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
groundmat=mat('STUDIO • chalk blue',(.22,.39,.46),.7)
bpy.ops.mesh.primitive_plane_add(size=20000,location=(0,0,-.4)); ground=bpy.context.object; ground.name='Studio floor'; ground.data.materials.append(groundmat); move_collection(ground,STUDIO)
def track(o,p):o.rotation_euler=(Vector(p)-o.location).to_track_quat('-Z','Y').to_euler()
def light(name,loc,energy,size,color):
    d=bpy.data.lights.new(name,'AREA'); d.energy=energy; d.shape='DISK'; d.size=size; d.color=color
    o=bpy.data.objects.new(name,d); STUDIO.objects.link(o); o.location=loc; track(o,(0,0,85))
light('Key • warm softbox',(260,-350,430),3700000,280,(1,.86,.7))
light('Fill • sky',(-250,-170,220),2400000,230,(.62,.84,1))
light('Rim',(100,230,350),4600000,200,(.72,1,.91))
world=bpy.data.worlds.new('Lagoon studio'); scene.world=world; world.use_nodes=True; world.node_tree.nodes['Background'].inputs[0].default_value=(.16,.24,.32,1); world.node_tree.nodes['Background'].inputs[1].default_value=.45
camdata=bpy.data.cameras.new('Preview camera'); cam=bpy.data.objects.new('Preview camera',camdata); STUDIO.objects.link(cam); scene.camera=cam
camdata.type='ORTHO'; camdata.ortho_scale=225; camdata.clip_end=100000; cam.location=(265,-470,235); track(cam,(0,0,84))
scene.render.engine='CYCLES'; scene.cycles.samples=48; scene.cycles.use_denoising=True
scene.render.resolution_x=1100; scene.render.resolution_y=1100; scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX'; scene.render.image_settings.file_format='PNG'
# Select only the character when exporting; no lights/cameras/ground or leaf bones.
def selection():
    bpy.ops.object.select_all(action='DESELECT'); rig.select_set(True); char.select_set(True); bpy.context.view_layer.objects.active=rig
def fbx(name,animated=False):
    selection()
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT,name),use_selection=True,object_types={'ARMATURE','MESH'},global_scale=1,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',axis_forward='X',axis_up='Z',use_space_transform=True,bake_space_transform=False,add_leaf_bones=False,primary_bone_axis='Y',secondary_bone_axis='X',use_armature_deform_only=True,use_mesh_modifiers=True,mesh_smooth_type='FACE',use_tspace=True,bake_anim=animated,bake_anim_use_all_bones=True,bake_anim_use_nla_strips=False,bake_anim_use_all_actions=False,bake_anim_force_startend_keying=True,bake_anim_step=1,bake_anim_simplify_factor=0,path_mode='COPY',embed_textures=True)
fbx('SK_Pebble.fbx')
fbx('AN_Pebble_Jump.fbx',True)
rig.animation_data.action=idle; scene.frame_end=31; scene.frame_set(1); fbx('AN_Pebble_Idle.fbx',True)
rig.animation_data.action=jump; scene.frame_end=48; scene.frame_set(1)
selection()
for area in bpy.context.screen.areas:
    if area.type=='VIEW_3D':
        area.spaces.active.region_3d.view_distance=310; area.spaces.active.region_3d.view_location=(0,0,85)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT,'Pebble_Penguin.blend'))
char.data.calc_loop_triangles()
bad=[]; maxinf=0
for v in char.data.vertices:
    total=sum(g.weight for g in v.groups); maxinf=max(maxinf,len(v.groups))
    if abs(total-1)>1e-4:bad.append(v.index)
stats={'vertices':len(char.data.vertices),'faces':len(char.data.polygons),'triangles':len(char.data.loop_triangles),'bones':len(arm.bones),'material_slots':len(char.data.materials),'uv_layers':len(char.data.uv_layers),'max_weight_influences':maxinf,'invalid_weight_vertices':len(bad),'dimensions_cm':list(char.dimensions),'animations':{'Pebble_Idle':[1,31],'Pebble_Jump_Test':[1,48]},'fps':30,'blender_version':bpy.app.version_string}
open(os.path.join(OUT,'source_stats.json'),'w').write(json.dumps(stats,indent=2))
print('PEBBLE_STATS',json.dumps(stats),flush=True)
for name,frame,loc,target,scale in [('Preview_Hero',1,(265,-470,235),(0,0,84),225),('Preview_Jump',18,(265,-470,250),(0,0,101),258),('Preview_Front',1,(0,-500,135),(0,0,84),205),('Preview_Back',1,(-220,470,200),(0,0,84),215)]:
    scene.frame_set(frame); cam.location=loc; track(cam,target); camdata.ortho_scale=scale; scene.render.filepath=os.path.join(OUT,name+'.png'); bpy.ops.render.render(write_still=True)
print('PEBBLE_BUILD_COMPLETE',flush=True)
