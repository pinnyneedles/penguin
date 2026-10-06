PEBBLE CHICK — brown king penguin chick (Unreal export guide)
Built with Blender 5.0.1 from tools/build_pebble_chick.py, October 2026.
Same skeleton as PEBBLE (see ../Pebble_Penguin/README_Unreal.txt); this file describes the
chick's own mesh, materials, animation set (tools/make_chick_anims.py) and import.

FILES
SK_Pebble_Chick.fbx          skeletal mesh in rest pose (mesh + skeleton, texture embedded); no animation.
AN_Pebble_Chick_*.fbx        eleven animation clips, skeleton only (no mesh), one clip per file; see ANIMATIONS.
T_Chick_Body_BaseColor.png   1024-square sRGB base colour for the down (also embedded in the mesh FBX).
T_Chick_Body_Normal_DX.png   1024-square normal map of fine down fibres, DirectX convention, for Unreal.
T_Chick_Body_Normal_GL.png   the same map in OpenGL convention, as used inside Blender (the FBX embeds
                             this one; in Unreal use the DX file or tick Flip Green Channel).
Pebble_Chick.blend           editable scene: mesh, rig, lights, camera (built by tools/build_pebble_chick.py).
Pebble_Chick_Anims.blend     the same scene with all eleven clips as actions (tools/make_chick_anims.py).
Pebble_Chick_*.gif           rendered previews: Idle, Waddle, Jump (start, loop, land), BellySlide
                             (start, loop, end, in place) and BellySlide_Travel (the same chain sliding
                             over snow with a following camera; display speed only).
Preview_SlideLean.png        the slide loop leaning right, centred and leaning left, from the front.
Preview_*.png, Compare_Eye_Bill.png, Compare_Iteration3.png, Preview_Animations.png
                             renders of the actual geometry (Compare_Iteration3 shows the model
                             before and after the third iteration, next to a reference photo).
source_stats.json, anim_stats.json, anim_validation.json      counts and checks written by the tools.

MESH
49,124 triangles; 24,626 vertices; 8 material slots; 1 UV layer.
One skinned mesh. The body and head are one continuous surface shaped like a real chick: a tall,
straight-sided column, heaviest low down, with broad shoulders flowing into a small head and no
neck pinch. About 730 soft down clumps are displaced into the geometry (fuller at the hem, short
on the head, nearly bare around the bill and eyes); finer down fibres come from the normal map.
The down stops above short dark legs with faint scale rings, so the legs show above the feet.
Eyes, eyelids and bill are rigid to the head bone; flippers, legs, toes and claws have blended
weights. The flippers are long, hang close along the sides and use the body's down material.
UVs: the body has a cylindrical unwrap with the seam down the back. The flippers and tail map onto
strips of the same texture with the fibres running along them. Constant-colour parts have
overlapping UVs, so this is not a lightmap or whole-character bake atlas.

SKELETON
16 bones, identical names, hierarchy and rest pose to Pebble:
root > pelvis > body > head > crest; body > flipper.L/R > flipper_tip.L/R;
pelvis > tail; pelvis > leg.L/R > foot.L/R > toe.L/R.
The chick has no crest geometry; the crest bone is kept only for compatibility.
Maximum 2 influences per vertex; all weights normalized; no morph targets.
The armature object is exported as "Armature". Unreal drops a root node with that name, so
the skeleton's top bone is "root" and root motion works. (Any other name becomes an extra,
motionless bone above "root".)

SCALE / AXES (read from the exported FBX headers)
FBX 7400, binary. UpAxis Z (+), FrontAxis X, UnitScaleFactor 1.0 (1 unit = 1 cm),
30 fps. Blender scene: centimetres (unit scale 0.01), character faces -Y, Z up;
the exporter converts to X forward.
Rest bounds: about 91 cm wide (flipper to flipper) x 102 cm deep (bill tip
to back) x 152 cm tall. Body alone is about 84 cm wide.
Origin/root at ground centre. Lowest sole point is 0.3 cm above the root plane.

ANIMATIONS — 30 fps. In place unless noted; the root bone stays at the origin.
Looping clips repeat their first pose on their last frame, which is what Unreal expects for a
seamless loop (sequence length = frames - 1). Every one-shot clip starts or ends on the rest pose
(Idle frame 1) or on the first frame of its loop, so the clips chain without pops.

Clip (file AN_Pebble_<clip>.fbx)  Frames  Length  Loop  Notes
Chick_Idle                          91    3.0 s   yes   breathing, weight shift, a slow glance, flipper
                                                        settle; feet stay planted.
Chick_Waddle                        33    1.07 s  yes   walk cycle. Planted feet move backward at a
                                                        constant 23.25 cm/s, so set the walk speed to
                                                        23.25 cm/s (or scale play rate by speed / 23.25).
                                                        Each foot is planted 56% of the cycle, with brief
                                                        double support. Footstep contacts: left frame 1,
                                                        right frame 17 (0.0 s and 0.53 s).
Chick_Waddle_RootMotion             33    1.07 s  yes   identical pose; the root bone carries the forward
                                                        motion (24.8 cm per cycle = 23.25 cm/s). Enable
                                                        Root Motion on the sequence; planted feet stay
                                                        fixed in the world.
Chick_Jump_Start                    10    0.30 s  no    rest -> crouch (pelvis -6 cm) -> launch pose.
                                                        Play when the jump begins.
Chick_Jump_Loop                     25    0.80 s  yes   in the air: flippers flap, legs paddle. Use for
                                                        rising and falling. No vertical travel; height
                                                        comes from Character Movement.
Chick_Jump_Land                     18    0.57 s  no    air pose -> feet plant (frame 3) -> squash ->
                                                        rest. Play on landing.
Chick_BellySlide_Start              28    0.93 s  no    rest -> crouch -> lunge -> belly hits the snow
                                                        (frame 17) -> head overshoots and settles.
Chick_BellySlide_Loop               65    2.13 s  yes   tobogganing, push and glide: left foot pushes
                                                        (frame 10), right foot pushes (frame 20), then a
                                                        long glide. Each push sets off a damped rock of
                                                        the body (about 8 deg); the head sways with it
                                                        about 4 frames late and a little further (about
                                                        11 deg), glances around (about 18 deg in all) and
                                                        dips after each push. Flippers balance against
                                                        the rock. The belly rests 1 cm into the snow.
Chick_BellySlide_Loop_LeanLeft      65    2.13 s  yes   the same loop banked about 9 deg into a left turn,
Chick_BellySlide_Loop_LeanRight     65    2.13 s  yes   or a right turn: head turned about 18 deg into the
                                                        turn, inside flipper lowered, feet trailing wide.
                                                        Same frame count and timing as the centre loop,
                                                        so the three blend cleanly.
Chick_BellySlide_End                28    0.93 s  no    flippers push up, legs swing under, stand, settle
                                                        to rest.

Suggested state machine: Locomotion (1D Blend Space on speed: Idle at 0, Waddle at 23.25 cm/s)
-> Jump_Start -> Jump_Loop while airborne -> Jump_Land -> Locomotion.
Locomotion -> BellySlide_Start -> Sliding -> BellySlide_End -> Locomotion, where Sliding is a 1D
Blend Space on steering input from -1 (LeanRight) through 0 (Loop) to +1 (LeanLeft).
For a push-and-glide feel, add AnimNotifies on BellySlide_Loop frames 10 and 20 and give the
character a short burst of speed on each, with friction slowing it during the glide.
The lying body is centred over the root, about 148 cm wide (flipper to flipper), 184 cm long
(bill to trailing feet) and 105 cm tall. While sliding, a smaller collision shape (for example a
capsule of half-height about 57 cm and radius about 55 cm) fits it better than the standing
capsule. The belly sits 1 cm below the root plane, so on a hard floor it reads as pressing into
snow; raise the mesh 1 cm while sliding if your surface must not be touched.
Clips use the same skeleton and work on Pebble's mesh too, once Pebble's files are exported
with the same "Armature" object name (see SKELETON).

UNREAL IMPORT — starting settings; not yet tested inside Unreal
1. Import SK_Pebble_Chick.fbx as a Skeletal Mesh into its own folder with Skeleton left
   empty, which creates the chick skeleton. Import Uniform Scale 1; Convert Scene and
   Convert Scene Unit on; Force Front XAxis on when the option is shown. Check in the asset
   viewer that the chick faces +X, stands on the grid, and that the skeleton's top bone is
   "root" (no extra "Armature" bone above it).
   Pebble's package files still use the armature name "Pebble_Rig", so in Unreal they gain
   an extra top bone and cannot share this skeleton until they are re-exported the same way.
2. Import Normals and Tangents. Leave Update Skeleton Reference Pose and Use T0
   As Ref Pose off. Auto physics asset is a starting point only; review it.
3. Import each AN_ file with Import Mesh off, Import Animations on, and the chick skeleton
   selected. These files contain only the skeleton and one clip. Use exported time and 30 fps.
   Rename the sequences if you like (AS_Chick_Idle, AS_Chick_Waddle, ...). Looping clips need
   Loop enabled where they are played (Blend Space, state or Play Animation node).
   For Chick_Waddle_RootMotion tick Enable Root Motion in the sequence; leave it off for the rest.
4. Materials. FBX carries the base colours and the embedded body texture, but
   not Blender's roughness and sheen reliably, so rebuild or check them:
     M_Chick_Body       Base Color = T_Chick_Body_BaseColor (sRGB), Normal =
                        T_Chick_Body_Normal_DX (Normal Map compression), Roughness 0.8.
                        For the soft fuzzy rim, use the Cloth shading model with
                        Fuzz Color about (0.55, 0.38, 0.24) and Cloth about 0.2,
                        or a Substrate Slab with FuzzAmount and FuzzColor.
     M_Chick_Foot       (0.030, 0.028, 0.030), Roughness 0.62  — legs, feet, eyelids
     M_Chick_Claw       (0.075, 0.070, 0.065), Roughness 0.35
     M_Chick_Bill       (0.022, 0.019, 0.021), Roughness 0.32  — upper bill
     M_Chick_BillLower  (0.050, 0.043, 0.043), Roughness 0.38
     M_Chick_Iris       (0.030, 0.016, 0.009), Roughness 0.12  — eyeball
     M_Chick_Pupil      (0.009, 0.008, 0.010), Roughness 0.19
     M_Chick_Glint      (1.000, 0.980, 0.900), Roughness 0.20
   Colours are linear RGB as used in Blender. No metallic surfaces.
5. Character Blueprint: start with a capsule of half-height about 76 cm and
   radius about 45 cm, mesh root at the capsule bottom (Z offset -76), and tune
   for your levels. The 0.3 cm sole offset can be ignored. Keep the skeletal
   mesh from blocking the movement capsule.
6. Animation Blueprint: see the suggested state machine under ANIMATIONS. Add AnimNotifies for
   footsteps on Chick_Waddle frames 1 and 17, landing on Chick_Jump_Land frame 3, belly
   impact on Chick_BellySlide_Start frame 17, and pushes on Chick_BellySlide_Loop frames 10
   (left) and 20 (right). The same frames are listed in anim_stats.json.
7. LODs: 47.9k triangles is fine for a player character. Generate LODs in the
   Skeletal Mesh editor for crowds or distant views.

ADDING HAIR / FUZZ (optional next step)
The mesh already has sculpted tufts and painted down, so it works on its own and
stays the fallback on every platform. Real strands are added on top:
- Author the strands in Blender with a Hair Curves object on the body: short on
  the head, longer and combed downward on the body, almost none around the bill
  and eyes, clumped to follow the existing tufts.
- Export the curves to Alembic (.abc) in Unreal's groom format. Exporting from
  this centimetre scene usually needs Scale 1; Alembic is Y-up, so set the groom
  import Rotation so the groom lines up with SK_Pebble_Chick.
- In Unreal enable the Groom and Alembic Groom Importer plugins and Support
  Compute Skin Cache, import the .abc as a Groom asset, create a Groom Binding
  to SK_Pebble_Chick, and add a Groom component attached to the character's
  skeletal mesh so it follows the animations.
- Strands are expensive and not supported on every platform. Set up groom LODs:
  strands up close, then cards (Hair Card Generator plugin) or the bare mesh.
Epic references:
https://dev.epicgames.com/documentation/unreal-engine/importing-grooms-into-unreal-engine
https://dev.epicgames.com/documentation/unreal-engine/groom-scalability-and-performance-with-unreal-engine

VALIDATION (tools/verify_chick_anims.py, results in anim_validation.json)
Mesh: the skeletal mesh FBX reimports into a clean Blender scene with one mesh, one armature named
"Armature", 16 bones, 49,124 triangles, 8 materials, embedded textures and normalized weights.
Clips: every AN_ file reimports with the "Armature" node, the same 16 bones and the expected
frame count; reimported bone positions match the source within 0.0001 cm. All four loops close
exactly (first and last pose identical), including both lean loops. All clip boundaries listed
under ANIMATIONS match exactly. In the slide loop the head's roll lags the body's by 4 frames. In the root-motion waddle each planted foot stays fixed in the world: 0.0 cm slip and
no rotation while planted (the previous waddle slid about 2.5 cm sideways and 1.3 cm front to
back per step). No vertex goes below the ground in any clip except the sliding belly, which presses exactly 1 cm
into the snow by design.
No Unreal project was opened; the import steps above are starting settings.

KNOWN LIMITATIONS
No IK controls, facial rig or blinks, physics asset, LODs or Unreal materials are included.
Clips are keyed on every frame (baked), so edit them through tools/make_chick_anims.py rather than
by hand. The legs stretch slightly to keep feet planted (there is no knee); the stretch stays hidden
in the down except for the trailing feet while sliding. The bill meets the down with a hard edge,
the eyelid is an even ring, and the toes have no scale texture.
