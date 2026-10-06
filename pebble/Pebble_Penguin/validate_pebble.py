import bpy, os, json, math
from mathutils import Vector, kdtree
from io_scene_fbx import parse_fbx as parse
P=os.path.join(os.path.dirname(__file__),'Pebble_Penguin')
bpy.ops.wm.open_mainfile(filepath=os.path.join(P,'Pebble_Penguin.blend'))
sc=bpy.context.scene; ch=bpy.data.objects['SK_Pebble']; rig=bpy.data.objects['Pebble_Rig']
def positions(ob):
    dg=bpy.context.evaluated_depsgraph_get(); ev=ob.evaluated_get(dg); me=ev.to_mesh()
    pts=[tuple(ev.matrix_world@v.co) for v in me.vertices]; ev.to_mesh_clear(); return pts
def bounds(pts):return [[min(p[i] for p in pts),max(p[i] for p in pts)] for i in range(3)]
expect={}
for anim,frames in [('Pebble_Jump_Test',[1,9,18,27,38,48]),('Pebble_Idle',[1,16,31])]:
    rig.animation_data.action=bpy.data.actions[anim]
    expect[anim]={}
    for f in frames:sc.frame_set(f); expect[anim][f]=positions(ch)
source_bones={b.name:b.parent.name if b.parent else None for b in rig.data.bones}
report={'source_bone_hierarchy':source_bones,'unreal_import_tested':False,'tests':[]}
for filename,anim in [('SK_Pebble.fbx',None),('AN_Pebble_Jump.fbx','Pebble_Jump_Test'),('AN_Pebble_Idle.fbx','Pebble_Idle')]:
    bpy.ops.wm.read_factory_settings(use_empty=True); sc=bpy.context.scene; sc.unit_settings.system='METRIC'; sc.unit_settings.scale_length=.01; sc.render.fps=30
    bpy.ops.import_scene.fbx(filepath=os.path.join(P,filename),use_anim=True,anim_offset=0,ignore_leaf_bones=False,automatic_bone_orientation=False,force_connect_children=False)
    meshes=[o for o in sc.objects if o.type=='MESH']; arms=[o for o in sc.objects if o.type=='ARMATURE']; obj=meshes[0]; ar=arms[0]
    # FBX has no Blender use_connect flags. The importer infers connected
    # bones, which suppresses their translated channels. Restore the source's
    # disconnected FK joints before evaluating the faithful FBX transforms.
    inferred_connections=[b.name for b in ar.data.bones if b.use_connect]
    bpy.context.view_layer.objects.active=ar
    bpy.ops.object.mode_set(mode='EDIT')
    for b in ar.data.edit_bones:b.use_connect=False
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.data.calc_loop_triangles()
    rec={'file':filename,'mesh_count':len(meshes),'armature_count':len(arms),'vertices':len(obj.data.vertices),'triangles':len(obj.data.loop_triangles),'bones':len(ar.data.bones),'hierarchy_matches':{b.name:b.parent.name if b.parent else None for b in ar.data.bones}==source_bones,'uv_layers':len(obj.data.uv_layers),'material_slots':len(obj.data.materials),'action_count':len(bpy.data.actions),'samples':[]}
    rec['blender_import_inferred_connections_cleared']=inferred_connections
    rec['animation_import_offset']=0
    for f,pts in (expect[anim] if anim else {1:expect['Pebble_Jump_Test'][1]}).items():
        sc.frame_set(f); actual=positions(obj); tree=kdtree.KDTree(len(pts))
        for i,p in enumerate(pts):tree.insert(p,i)
        tree.balance(); maxerr=max(tree.find(p)[2] for p in actual)
        rec['samples'].append({'frame':f,'max_surface_distance_cm':maxerr,'bounds_cm':bounds(actual),'finite':all(math.isfinite(c) for p in actual for c in p)})
    bad=0; maxinf=0
    for v in obj.data.vertices:
        total=sum(g.weight for g in v.groups); maxinf=max(maxinf,len(v.groups)); bad+=abs(total-1)>1e-4
    rec['bad_weight_vertices']=bad; rec['max_influences']=maxinf
    rec['pass']=len(meshes)==1 and len(arms)==1 and rec['hierarchy_matches'] and bad==0 and all(s['max_surface_distance_cm']<.01 and s['finite'] for s in rec['samples'])
    report['tests'].append(rec)
    if anim=='Pebble_Jump_Test':
        sc.frame_start=1;sc.frame_end=48;sc.frame_set(18)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(P,'Validation_FBX_Reimport.blend'))
    root,ver=parse.parse(os.path.join(P,filename))
    gs=next(e for e in root.elems if e.id==b'GlobalSettings')
    props=next(e for e in gs.elems if e.id==b'Properties70')
    rec['fbx_version']=ver;rec['fbx_axis_and_units']={e.props[0].decode():e.props[-1] for e in props.elems if e.props[0] in [b'UpAxis',b'UpAxisSign',b'FrontAxis',b'FrontAxisSign',b'CoordAxis',b'CoordAxisSign',b'UnitScaleFactor']}
report['all_pass']=all(t['pass'] for t in report['tests'])
open(os.path.join(P,'validation_report.json'),'w').write(json.dumps(report,indent=2))
print('VALIDATION',json.dumps(report),flush=True)
