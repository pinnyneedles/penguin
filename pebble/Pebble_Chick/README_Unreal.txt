PEBBLE CHICK — brown king penguin chick (Unreal export guide)
Built with Blender 5.0.1 from tools/build_pebble_chick.py, October 2026.
Same skeleton and clip set as PEBBLE (see ../Pebble_Penguin/README_Unreal.txt);
this file describes the chick's own mesh, materials, animations and import.

FILES
SK_Pebble_Chick.fbx          skeletal mesh in rest pose; no animation.
AN_Pebble_Chick_Idle.fbx     mesh + skeleton + idle clip.
AN_Pebble_Chick_Jump.fbx     mesh + skeleton + jump test clip.
AN_Pebble_Chick_Waddle.fbx   mesh + skeleton + waddle walk cycle.
T_Chick_Body_BaseColor.png   1024-square sRGB base colour for the down (also embedded in each FBX).
Pebble_Chick.blend           editable scene: mesh, rig, Idle and Jump actions, lights, camera.
Pebble_Chick_Waddle.blend    same scene with the Waddle action added.
Preview_*.png, Pebble_Chick_Waddle.gif, Compare_Eye_Bill.png   renders of the actual geometry.
source_stats.json            counts written by the build.

MESH
47,908 triangles; 24,018 vertices; 8 material slots; 1 UV layer.
One skinned mesh. The body and head are one continuous surface with about 840
down tufts displaced into the geometry (shaggy at the hem, short on the head,
nearly bare around the bill and eyes). Eyes, eyelids and bill are rigid to the
head bone; flippers, toes and claws have blended weights.
UVs: the body has a cylindrical unwrap with the seam down the back; it is the
only part that uses the texture. Constant-colour parts have overlapping UVs, so
this is not a lightmap or whole-character bake atlas.

SKELETON
16 bones, identical names and hierarchy to Pebble, so the two characters can
share one Skeleton asset and one Animation Blueprint:
root > pelvis > body > head > crest; body > flipper.L/R > flipper_tip.L/R;
pelvis > tail; pelvis > leg.L/R > foot.L/R > toe.L/R.
The chick has no crest geometry; the crest bone is kept only for compatibility.
Maximum 2 influences per vertex; all weights normalized; no morph targets.

SCALE / AXES (read from the exported FBX headers)
FBX 7400, binary. UpAxis Z (+), FrontAxis X, UnitScaleFactor 1.0 (1 unit = 1 cm),
30 fps. Blender scene: centimetres (unit scale 0.01), character faces -Y, Z up;
the exporter converts to X forward.
Rest bounds: about 107.7 cm wide (flipper to flipper) x 103.1 cm deep (bill tip
to back) x 152.4 cm tall. Body alone is about 100 cm wide.
Origin/root at ground centre. Lowest sole point is 0.3 cm above the root plane.

ANIMATIONS — all 30 fps, all in place (no root motion), root bone stationary
Pebble_Idle        31 frames, about 1.0 s, loops. Gentle breathing sway of
                   body, head and flippers.
Pebble_Jump_Test   48 frames, 1.6 s, one-shot. Crouch at frame 9 (pelvis
                   -9 cm), takeoff 18, apex 27 (pelvis +38 cm), land 38,
                   recover 48. A deformation test, not a gameplay jump: the
                   height is in the pelvis, so with Character Movement it would
                   double the visual jump. Split it into in-place takeoff,
                   fall and land clips before using it in gameplay.
Pebble_Waddle      33 frames, about 1.07 s per two-step cycle, loops.
                   Side-to-side weight shift with pelvis roll, hip twist,
                   head counter-roll, flipper swing and foot lift. Planted feet
                   travel about 12.4 cm per step, so the feet match the ground
                   at about 23 cm/s. Faster than that shows foot slide; scale the
                   play rate by (speed / 23) or blend to a faster gait.
Idle and Waddle repeat their first frame as their last frame (seamless in
Blender). If Unreal shows a tiny hitch at the loop point, trim the final frame.

UNREAL IMPORT — starting settings; not yet tested inside Unreal
1. Import SK_Pebble_Chick.fbx as a Skeletal Mesh into its own folder.
   Either leave Skeleton empty to create a new one, or pick Pebble's skeleton
   to share animations with Pebble. Import Uniform Scale 1; Convert Scene and
   Convert Scene Unit on; Force Front XAxis on when the option is shown. Check
   in the asset viewer that the chick faces +X and stands on the grid.
2. Import Normals and Tangents. Leave Update Skeleton Reference Pose and Use T0
   As Ref Pose off. Auto physics asset is a starting point only; review it.
3. Import each AN_ file with Import Mesh off, Import Animations on, and the
   chick (or shared) skeleton selected. Use exported time and 30 fps. Each file
   holds one clip; rename the sequences, for example AS_Chick_Idle,
   AS_Chick_Jump, AS_Chick_Waddle. Enable looping on Idle and Waddle.
4. Materials. FBX carries the base colours and the embedded body texture, but
   not Blender's roughness and sheen reliably, so rebuild or check them:
     M_Chick_Body       Base Color = T_Chick_Body_BaseColor (sRGB), Roughness 0.8.
                        For a soft fuzzy rim, use the Cloth shading model with
                        Fuzz Color about (0.35, 0.22, 0.12) and Cloth about 0.15–0.3,
                        or a Substrate Slab with FuzzAmount and FuzzColor.
     M_Chick_Foot       (0.040, 0.034, 0.034), Roughness 0.65  — feet, eyelids
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
6. Animation Blueprint: a 1D Blend Space on speed with Idle at 0 and Waddle at
   about 23 cm/s is a good start. Use the jump only after splitting it (see above).
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

VALIDATION
All four FBX files were reimported into factory-clean Blender scenes: one mesh,
one armature, 16 bones with matching hierarchy, 47,908 triangles, 8 materials,
embedded texture, normalized weights, and clip lengths 31 / 48 / 33 frames.
No Unreal project was opened; the import steps above are starting settings.

KNOWN LIMITATIONS
No root motion, IK, facial rig or blinks, physics asset, LODs or Unreal
materials are included. The bill meets the down with a hard edge, the eyelid is
an even ring, and the toes have no scale texture; these were left as they are
because no tested improvement was available. The jump is a test clip only.
