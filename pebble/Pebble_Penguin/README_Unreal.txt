PEBBLE — original penguin platformer character
Created in Blender 5.1.1, October 2026.

A chunky lagoon-colored penguin with a cream face/bib, coral webbed feet,
three teal crest feathers and an expressive two-part smiling bill.
Original geometry, palette and texture; no external character assets used.

FILES
Pebble_Penguin.blend — editable model, FK deform skeleton, both actions,
  packed body texture, studio lights and camera. Opens at neutral frame 1.
SK_Pebble.fbx — skeletal mesh in rest pose; no animation.
AN_Pebble_Idle.fbx — same mesh/skeleton plus 31-frame idle, 30 fps.
AN_Pebble_Jump.fbx — same mesh/skeleton plus 48-frame jump test, 30 fps.
T_Pebble_Body_BaseColor.png — 1024-square sRGB base-color texture.
Preview_*.png / Pebble_Preview.jpg — actual rendered geometry.
Pebble_Jump.gif — short rendered deformation preview, when present.
Validation_FBX_Reimport.blend — clean-scene jump FBX reimport, frame 18.
source_stats.json, validation_report.json, topology_audit.json — checks.
build_pebble.py, validate_pebble.py, preview_extras.py — reproducible source.

MESH / RIG
17,892 vertices; 35,680 triangles; 8 material slots; 1 UV layer.
16 bones: root, pelvis, body, head, crest, tail, two flipper joints per side,
and leg / foot / toe on each side. Maximum 2 influences per vertex.
All weights normalized. One skinned mesh with closed intersecting surface
pieces; torso and head form one continuous deforming surface. Facial pieces
are rigidly bound to the head. Flippers and toes have blended weights.
The body has a seam-at-back UV unwrap. Constant-color parts have UVs that
overlap; this is not a unique whole-character baking/lightmap atlas.

SCALE / AXES
Blender scene uses centimeters (unit scale 0.01); transforms are identity.
Rest bounds: approximately 130.66 cm wide x 100.40 cm deep x 167.27 cm tall.
Soles sit 1.83 cm above the root plane; crest top is about 169.09 cm.
Blender character faces -Y, Z up. FBX export requests X forward, Z up and
centimeter scene units. Raw FBX unit metadata was checked (~1 cm/unit).
Origin/root at ground center; no root motion. Jump height is pelvis motion.

UNREAL IMPORT — starting settings; not tested inside Unreal
1. Import SK_Pebble.fbx into a new content folder as a Skeletal Mesh.
   Leave Skeleton unassigned to create the character's own skeleton.
   Import uniform scale 1; Convert Scene and Convert Scene Unit enabled.
   Use the importer's X-forward convention consistently for mesh and clips
   (Force Front XAxis when that setting is exposed). Verify +X facing in
   the asset viewer. The Blender FBX round trip validates basis conversion,
   but does not establish the behavior of your Unreal importer version.
2. Import Normals and Tangents; keep Update Skeleton Reference Pose and
   Use T0As Ref Pose off. No morph targets are included. Auto physics may
   be generated as a starting point, but must be reviewed and simplified.
3. Import the two AN_ files with Import Mesh off, Import Animations on,
   and the newly created Pebble skeleton selected. Use exported time and
   30 fps. Each file contains one baked animation. These files also carry
   mesh data so they can be inspected independently.
4. Verify the body PNG is assigned to M_Pebble_Body Base Color as sRGB.
   Other slots use constant colors. Roughness is approximately 0.45,
   eyes 0.19; no metallic surfaces. If materials do not transfer as desired,
   rebuild simple Unreal materials using the Blender material colors.
5. In a Character Blueprint, use a capsule for movement collision. A starting
   capsule half-height around 85 cm and radius around 40 cm is reasonable,
   then tune for levels, feet and flipper clearance. Place the mesh root near
   the capsule bottom; account for the 1.83 cm sole offset. Keep the skeletal
   mesh from blocking the movement capsule. Configure camera and movement
   according to the intended platforming controls.
6. Play Idle in an Animation Blueprint. Jump_Test is a deformation demo with
   vertical pelvis travel, not a production gameplay jump. Adapt it into
   in-place takeoff / fall / landing clips before combining with Character
   Movement's vertical motion, or the jump height would be doubled visually.

VALIDATION
All three FBXs were imported independently into factory-clean Blender scenes.
Mesh/rig count, topology counts, bone names/parent hierarchy, UV/material
counts, units, normalized weights and finite evaluated coordinates passed.
Neutral, 6 jump key poses and 3 idle poses were compared to source geometry.
Maximum sampled surface deviation was below 0.0001 cm.
Blender-specific reimport detail: use animation offset 0. Blender infers
connected bones for pelvis, crest, foot and toe joints even when exported
from unconnected FK joints. Clearing those inferred use_connect flags
restores the source behavior; otherwise Blender ignores translated joints.
The supplied validation script and reimport .blend include this correction.
No Unreal project was opened, changed, or used to verify these assets.

PROTOTYPE LIMITATIONS / NEXT PRODUCTION PASS
This is a polished rigged character prototype, not a completed shipping player.
No walk/run set, IK controls, facial rig/blinks, retarget mapping, physics asset,
collision setup, LODs, Unreal Blueprint or engine-specific material instance.
Eight material slots and 35.7k triangles are suitable for iteration but should
be budgeted for the target platform; atlas consolidation and LODs can reduce
draw calls and geometry. Inspect extreme limb/head poses before expanding
the animation library. Detached overlapping surface construction is deliberate
for this style and may need welding/retopology for extreme deformation.
The skeleton is custom and is not the Unreal mannequin skeleton.

OFFICIAL IMPORT REFERENCES
https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-import-options-reference-in-unreal-engine
https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-skeletal-mesh-pipeline-in-unreal-engine
