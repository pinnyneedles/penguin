# Crab: import into Unreal Engine 5

A red crab enemy for the penguin game. It comes as a skeletal mesh with three lower levels of detail, an 80-bone
skeleton built for procedural animation, twelve animation clips, and a colour, normal and ORM texture set. Steps 1 to 9
take you from the zip to a crab that walks, scuttles, turns, threatens, pinches, flinches and dies in your level. Plan on
about 30 minutes the first time. Step 10 is optional: it sets up feet that adapt to uneven ground, claw and eye aiming,
and fully procedural walking.

> These files were checked by re-importing them into a clean Blender scene, not inside an Unreal project. The
> steps use settings that work with both Unreal FBX importers, and several steps include a quick check so you can
> confirm the result in your own editor. Node and option names can differ slightly between engine versions.

---

## What is in the zip

| Folder | Contents |
|---|---|
| `Content/Meshes` | `SK_Crab.fbx`: skeletal mesh and skeleton in the rest pose, textures embedded. `SK_Crab_LOD1.fbx` to `SK_Crab_LOD3.fbx`: lower levels of detail on the same skeleton |
| `Content/Animations` | Twelve `AN_Crab_*.fbx` clips, skeleton only, one clip per file |
| `Content/Textures` | `T_Crab_BaseColor.png`, `T_Crab_Normal_DX.png` (normal map for Unreal) and `T_Crab_ORM.png` |
| `Reference` | `procedural_rig.json` and `Rig_Diagram.png` (bone roles for procedural setups), `materials.csv`, `animations.csv`, `anim_events.json`, `mesh_stats.json` and the validation report |
| `Previews` | Renders and GIFs of the model, its levels of detail and every animation |
| `Source_Blender` | `Crab.blend` (the rig with foot IK for posing) and `Crab_Anims.blend` (all twelve clips) |

**Crab facts**

| | |
|---|---|
| Size | 63.5 cm across the shell, 96 cm leg tip to leg tip, 84 cm from claw tips to back legs, 28 cm tall. Pebble Chick is 152 cm tall, so the crab comes up to about its knee |
| Triangles | 35,064 at full detail; 13,392, 6,024 and 3,420 for LOD1 to LOD3. Two material slots (`M_Crab_Shell`, `M_Crab_Eye`) |
| Skeleton | 80 bones under `root`. 40 move the mesh: `body`, eye stalks, antennae, mouthparts, four bones per claw and three per leg. 40 are helpers with no skin: IK goals, knee poles, foot contact points and claw hit points (see Step 10 and `Reference/Rig_Diagram.png`) |
| Skinning | Rigid. Every piece of shell follows exactly one bone, as on a real crab, so nothing stretches at any level of detail |
| Claws | A heavy crusher claw on the right (32% bigger, with blunt molars) and a slimmer cutter on the left (fine sharp teeth), like many real crabs |
| Units | Centimetres, Z up, 30 fps |

**Already imported the first crab?** Bone names changed in this version (`eye.L` is now `eye_l`, `leg1_tip.R` is now
`leg1_tip_r`, and so on, following Unreal's naming), and the skeleton gained helper bones. The old clips do not fit the
new skeleton. Import this version into a fresh `Characters/Crab` folder (or delete the old crab assets first) and point
your Blueprints at the new assets.

---

## Step 1: Make a folder in your project

In the Content Browser create `Content/Characters/Crab` with four sub-folders:
`Meshes`, `Animations`, `Textures` and `Materials`. The rest of this guide assumes those names.

## Step 2: Import the skeletal mesh

1. Open `Characters/Crab/Meshes`, click **Import**, and pick `Content/Meshes/SK_Crab.fbx` only (the LOD files come in Step 3).
2. Set the options. Which dialog you see depends on your engine version and settings:

    **If the dialog has sections called Common, Common Meshes and Skeletal Meshes (Interchange importer):**

    - Common Skeletal Meshes and Animations: **Import Only Animations** off, **Skeleton** empty (a new skeleton is created).
    - Skeletal Meshes: **Import Skeletal Meshes** on, **Import Content Type** = Geometry and Skinning Weights,
      **Create Physics Asset** on, **Import Morph Targets** off, **Update Skeleton Reference Pose** off.
      Common Skeletal Meshes and Animations: **Use T0 As Ref Pose** off.
    - Animations: **Import Animations** off (the mesh file has none).
    - Common: **Offset Uniform Scale** 1.0. Leave the offsets at zero.
    - Materials and textures: on is fine; you will set up the shell material in Step 5.

    **If you see the older FBX Import Options dialog:**

    - Mesh: **Skeletal Mesh** on, **Skeleton** None, **Import Mesh** on, **Create Physics Asset** on,
      **Import Morph Targets** off, **Update Skeleton Reference Pose** off, **Use T0 As Ref Pose** off.
    - Transform: **Import Uniform Scale** 1.0.
    - Miscellaneous: **Convert Scene** on, **Convert Scene Unit** on, **Force Front XAxis** off.
    - Animation: **Import Animations** off.

3. Click **Import**. You get `SK_Crab`, `SK_Crab_Skeleton` and `SK_Crab_PhysicsAsset` (names can vary slightly
    by version).
4. **Check it.** Open the skeletal mesh:
    - The crab should stand on the grid, about 28 cm tall and 96 cm across the legs. If it is tiny or 100 times
      too big, re-import with the scale at 1.0 and Convert Scene Unit on.
    - In the Skeleton Tree, the top bone should be `root` with `body`, `ik_foot_root` and `ik_claw_root` below it,
      80 bones in all. If you see an extra bone called `Armature` above `root`, re-import the mesh.
    - Note which way the eyes and claws point. That is the crab's front, and you need it in Step 8.

## Step 3: Add the levels of detail

The three lower levels are the same crab built from fewer polygons. They share the skeleton, the UV layout and the
textures, so they swap in without popping in colour. See `Previews/Preview_LODs.png`.

1. Open `SK_Crab`. In the Details panel, find the **LOD Picker** section and its **LOD Import** drop-down.
2. Choose **Import LOD Level 1** and pick `SK_Crab_LOD1.fbx`. Repeat with **Import LOD Level 2** and `SK_Crab_LOD2.fbx`,
    then **Import LOD Level 3** and `SK_Crab_LOD3.fbx`.
3. Set when each level switches in. Under each LOD's **LOD Info**, set **Screen Size**: LOD1 0.4, LOD2 0.2, LOD3 0.1.
    These are starting values; raise them if you notice the switch.
4. **Check it.** In the viewport, use the LOD drop-down (or `r.ForceLOD 1` to `3` in the console) and look at each
    level. The crab keeps its shape and colours; only the curves get coarser.

If **LOD Import** is missing in your version, the same menu is under the viewport's **LOD** options or in the
skeletal mesh's **Asset Details**. If you skip this step the crab works fine with one level.

## Step 4: Import the textures

1. Open `Characters/Crab/Textures` and import the three PNG files from `Content/Textures`.
2. Open `T_Crab_Normal_DX` and check **Compression Settings** = Normalmap and **sRGB** off. Unreal often detects
    normal maps on import; if it did not, set these two by hand. Leave **Flip Green Channel** off, because this file
    already uses Unreal's DirectX convention.
3. Open `T_Crab_ORM` and set **Compression Settings** = Masks (no sRGB). Its channels are R = ambient occlusion
    (baked), G = roughness and B = metallic (zero everywhere).
4. `T_Crab_BaseColor` keeps the defaults (sRGB on).

## Step 5: Set up the materials

1. In `Materials`, create **M_Crab_Shell**:
    - Texture Sample `T_Crab_BaseColor` into **Base Color**.
    - Texture Sample `T_Crab_Normal_DX` (sampler type Normal) into **Normal**.
    - Texture Sample `T_Crab_ORM` (sampler type Masks): **R** into **Ambient Occlusion**, **G** into **Roughness**,
      **B** into **Metallic**.
    - Optional damp sheen: set **Shading Model** to Clear Coat with **Clear Coat** 0.1 and **Clear Coat Roughness**
      0.2. Keep it subtle; a strong coat makes the shell look like plastic. With Substrate, add a thin coat layer instead.
2. Create **M_Crab_Eye**: a Constant3Vector (0.008, 0.007, 0.008) into **Base Color**, 0.06 into **Roughness**, and
    optionally Clear Coat 1.0. The eyes are glossy black beads; the reflections do the work.
3. Open `SK_Crab`, and in **Material Slots** assign each material to the slot with the same name. The levels of
    detail use the same two slots.

## Step 6: Import the animations

1. Open `Characters/Crab/Animations` and import all twelve files from `Content/Animations` in one go.
2. Settings:
    - **Interchange dialog:** Common Skeletal Meshes and Animations: **Import Only Animations** on and
      **Skeleton** = `SK_Crab_Skeleton`. Animations: **Import Animations** on, **Import Bone Tracks** on,
      **Animation Length** = the source or exported timeline option (not Set Range), **Snap to Closest Frame Boundary** on.
    - **Older dialog:** Mesh: **Import Mesh** off, **Skeleton** = `SK_Crab_Skeleton`. Animation: **Import Animations** on,
      **Animation Length** = Exported Time. Use the same Miscellaneous axis settings as the mesh in Step 2.
3. You get twelve Animation Sequences:

    | Sequence | Frames | Length | Loops | What it does |
    |---|---|---|---|---|
    | Crab_Idle | 91 | 3.0 s | yes | breathing, eye stalks glance left and right, antenna flicks, mouthparts working, claw snips, two leg shuffles |
    | Crab_Scuttle_Left | 15 | 0.47 s | yes | sideways run toward the crab's own left; planted feet match 50 cm/s |
    | Crab_Scuttle_Right | 15 | 0.47 s | yes | the same toward its right |
    | Crab_Walk_Forward | 25 | 0.8 s | yes | slow forward walk; planted feet match 22 cm/s |
    | Crab_Walk_Backward | 25 | 0.8 s | yes | backs away with its claws up; planted feet match 18 cm/s |
    | Crab_Turn_Left | 21 | 0.67 s | yes | turns in place, counter-clockwise seen from above; planted feet match 60° per second |
    | Crab_Turn_Right | 21 | 0.67 s | yes | the same, clockwise |
    | Crab_Threat | 55 | 1.8 s | no | rears up, claws raised wide and open, snaps on frames 22 and 34 |
    | Crab_Attack_Snap | 33 | 1.07 s | no | wind-up, lunge and double pinch; the claws close on frame 13 |
    | Crab_Claw_Snap | 31 | 1.0 s | no | claws only, to layer over any other clip: the left claw snaps on frame 9, the right on frame 23 |
    | Crab_Hit | 21 | 0.67 s | no | flinch: knocked back, eye stalks fold down, claws tucked in |
    | Crab_Death | 60 | 1.97 s | no | curls up, hops and flips onto its back (lands on frame 25), legs twitch, then still |

4. Quick test: drag `SK_Crab` into a level, select it, set **Animation Mode** = Use Animation Asset and pick any clip.
    It should play with the feet on the ground and no pop at the loop point.

All clips are in place: the root bone never moves, and your Character Movement moves and turns the capsule. Looping
clips repeat their first pose as their last frame, which is what Unreal expects for a seamless loop. Every one-shot
clip starts on the idle's first pose, and every one except Death also ends there. In the idle, walking, scuttling,
turning and attack clips the eye stalks, antennae and claws sway and settle with the body's motion, so the crab looks
alive without any extra setup.

Every clip also moves the helper bones: each `ik_legN` sits exactly on its foot, and each `ik_claw` on its claw tip.
That is what lets the IK setups in Step 10 start from the animated pose without changing it.

## Step 7: Physics asset

The physics asset gives the crab per-bone collision for hit traces and an optional ragdoll. The capsule in Step 8
still does the moving. The generated one may be uneven, so rebuild it once:

1. Open `SK_Crab_PhysicsAsset`. Select all bodies in the Skeleton Tree and delete them.
2. In the **Tools** panel set **Primitive Type** = Capsule, **Vertex Weighting Type** = Dominant Weight (each vertex
    belongs to one bone, so this is exact), **Min Bone Size** = 3, **Bodies for All Bones** off,
    **Create Constraints** on. Click **Generate All Bodies**.
3. You should see a capsule or box per shell piece and none on the helper bones (they have no geometry). Replace the
    `body` capsule with a box that covers the shell if you want flat-topped collision.
4. For hit detection only, set every body's **Physics Type** to Kinematic. For a ragdoll on death, leave them
    Simulated and limit the leg constraints to about 30° swing.

## Step 8: Character Blueprint

1. Create a Blueprint class based on **Character** called `BP_Crab`.
2. **Capsule Component:** Capsule Radius 34, Capsule Half Height 34. The capsule covers the shell. The legs reach past it
    on purpose, as a crab's legs splay wider than its body.
3. **Mesh** component: Skeletal Mesh Asset = `SK_Crab`, Location Z = -34 so the feet sit at the bottom of the capsule.
    Rotate it about Z (yaw) until the eyes and claws point along the blue Arrow component, which is the character's
    forward. Try 0 first, then -90 or 90, depending on what you saw in Step 2. **Collision Presets** on the mesh:
    CharacterMesh, or anything that does not block the capsule.
4. **Character Movement:** Max Walk Speed 50 for a perfect foot match while scuttling. To turn at the speed of the
    turn clips, turn on **Use Controller Desired Rotation** with **Rotation Rate** Yaw 60, and turn off
    **Use Controller Rotation Yaw** on the pawn itself.
5. **Crabs walk sideways.** Turn **Orient Rotation to Movement** off, so the crab keeps facing its target and strafes.
    For an AI crab, call **Set Focus** with the penguin as the focus actor so it always faces the player, then move it
    with **AI Move To** or **Add Movement Input**. Movement to the side plays the scuttle, movement toward the player
    plays the forward walk, and backing off plays the backward walk.

## Step 9: Animation Blueprint

1. Create an **Animation Blueprint** for `SK_Crab_Skeleton` called `ABP_Crab`, and set it as the Anim Class on the
    Mesh component of `BP_Crab`.
2. Make a **Blend Space** (2D) on the same skeleton called **BS_Crab_Locomotion**:
    - Horizontal axis `Side` from -50 to 50, vertical axis `Forward` from -18 to 22.
    - Put Crab_Idle at (0, 0), Crab_Scuttle_Left at (-50, 0), Crab_Scuttle_Right at (50, 0),
      Crab_Walk_Forward at (0, 22) and Crab_Walk_Backward at (0, -18).
3. In the Event Graph, on **Event Blueprint Update Animation**, get the pawn and set:
    - `Side` = Velocity · Actor Right Vector (positive when moving to the crab's right).
    - `Forward` = Velocity · Actor Forward Vector, clamped to -18..22.
    - `TurnRate` = the change in the actor's yaw since last frame (use **Normalize Axis**) divided by Delta Seconds.
      In Unreal a positive yaw change turns right (clockwise seen from above).
    - `IsDead` = a bool your crab sets when it dies.
4. In the AnimGraph add a **State Machine** with three states, then a **Default Slot** after it for one-shots:

        Turning ◀──▶ Locomotion ──IsDead──▶ Dead

    - **Locomotion** plays BS_Crab_Locomotion with `Side` and `Forward`. Above 50 cm/s sideways, set its Play Rate to
      `max(1, abs(Side) / 50)` so the feet keep up.
    - **Turning** plays Crab_Turn_Right when `TurnRate` is positive and Crab_Turn_Left when it is negative (a
      **Blend Poses by Bool** works), with Play Rate `abs(TurnRate) / 60`. Enter it when the speed is under 5 and
      `abs(TurnRate)` is over 15; leave it when either changes. A blend time of 0.15 s on both transitions works well.
    - **Dead** plays Crab_Death once with Loop off. It stops on its last frame, lying on its back.
    - Right-click Crab_Threat, Crab_Attack_Snap and Crab_Hit and choose **Create AnimMontage**. Play them from the crab's
      Blueprint with **Play Anim Montage**; they run through the Default Slot over the locomotion.
5. **Claw snaps while walking.** Crab_Claw_Snap moves only the claws, so it can play on top of anything:
    - Create a montage from it and give it its own slot, for example `DefaultGroup.Claws`.
    - In the AnimGraph, after the Default Slot, add **Layered blend per bone**. Base Pose = everything so far.
      Blend Poses 0 = a **Slot** node for `Claws` fed by the same pose.
    - In its Layer Setup add two **Branch Filters**: `claw_arm_l` and `claw_arm_r`, Blend Depth 0. Turn on
      **Mesh Space Rotation Blend** so the claws follow the body.
    - Play the montage whenever the crab should snap (for example every few seconds while it chases the penguin).
6. **AnimNotifies** for sound, effects and damage. Add them in each sequence's or montage's Notifies track:

    | Sequence | Frame | Event |
    |---|---|---|
    | Crab_Scuttle_Left / Right | 1 and 7 | footsteps (each set of four feet lands) |
    | Crab_Walk_Forward / Backward | 11 and 23 | footsteps |
    | Crab_Turn_Left / Right | 10 and 20 | footsteps |
    | Crab_Threat | 22 and 34 | claw snap |
    | Crab_Attack_Snap | 13 | hit: claws close, apply damage here |
    | Crab_Claw_Snap | 9 and 23 | left claw snap, right claw snap |
    | Crab_Death | 25 | lands on its back |

    The same frames are in `Reference/anim_events.json`, together with the frame on which each individual foot lands.

## Step 10 (optional): Procedural animation

The skeleton carries everything a procedural setup needs. `Reference/Rig_Diagram.png` shows where the helpers sit
and `Reference/procedural_rig.json` lists every chain, bone length, gait timing and spring setting.

| Helper bones | Parent | What they are for |
|---|---|---|
| `ik_leg1_l` … `ik_leg4_r` | `ik_foot_root` (under `root`) | Foot goals. Each sits on the point where its leg touches the ground, in every frame of every clip |
| `ik_leg1_ankle_l` … | its `ik_legN` | The Two Bone IK effector: placed and oriented like the leg's tip segment, so the leg's point lands exactly on `ik_legN` |
| `pole_leg1_l` … | `body` | Knee pole targets, above and beside each knee |
| `leg1_end_l` … | its `legN_tip` | The foot contact point at the end of each leg (read it for footstep effects) |
| `ik_claw_l`, `ik_claw_r` | `ik_claw_root` | Claw goals, on the moving finger's tip in every clip |
| `claw_tip_l/r`, `claw_pinch_l/r` | the claw | The finger tip, and the point where the fingers close: use it as the attack's hit point or a socket |

### 10a. Feet on uneven ground (recommended)

Keep playing the baked clips and let IK move each planted foot onto the real ground. This gives you slopes, steps
and rocks without new animation.

1. **Find the ground under each foot.** Every frame, for each of the eight `ik_legN` bones: take its world position,
   trace down from 30 cm above it to 40 cm below it (a sphere trace of radius 1 to 2 cm is smoother than a line), and
   keep the height difference between the hit and the bone. Do this in a **Control Rig** (Sphere Trace by Trace
   Channel node) or in the Animation Blueprint's Event Graph. Smooth the offsets over a few frames (an
   interpolation speed of about 15) so feet do not snap.
2. **Move the goals.** Add each offset to the goal's Z. In the AnimGraph that is one **Transform (Modify) Bone** per
   leg on `ik_legN_s`: Translation Mode Add to Existing, Translation Space World. In Control Rig, set the bone's global
   transform. The `ik_legN_ankle` child follows automatically.
3. **Solve each leg.** One **Two Bone IK** node per leg (eight in all):
    - **IK Bone** = `legN_tip_s`.
    - **Effector Location Space** = Bone Space, **Effector Target** = `ik_legN_ankle_s`, Effector Location (0, 0, 0).
    - **Joint Target Location Space** = Bone Space, **Joint Target** = `pole_legN_s`.
    - **Take Rotation from Effector Space** on, so the tip segment takes the ankle's rotation and its point lands
      exactly on `ik_legN`. **Allow Stretching** off.

    In Control Rig use **Basic IK** with Bone A `legN_upper_s`, Bone B `legN_lower_s`, Effector Bone `legN_tip_s`,
    the effector taken from `ik_legN_ankle_s`, and the pole from `pole_legN_s`. Set **Primary Axis** to the axis that
    points down the leg bones (try Y; if a leg twists, try -Y or X).
4. **Tilt and lift the body.** Average the eight offsets and add that to the `body` bone's height, then tilt `body` by
   the slope of a plane through the feet (front feet minus back feet for pitch, left minus right for roll). Lower
   the body a little more if a leg would have to stretch past its reach (`max_reach_from_hip_cm` in the JSON).
5. **Check it.** With all offsets at zero the IK does nothing visible, because the clips already put each goal on its
   foot. On a slope the feet should land on the surface and the shell should tilt with it.

### 10b. Fully procedural walking

For crabs that walk anywhere at any speed without the locomotion clips, drive the eight goals with a gait clock.
This is what `Previews/Crab_Procedural_Terrain.gif` shows: the crab crossing bumpy, rising ground with its feet
planted exactly (0.0 cm slip, measured), driven only by the rules below.

- **Gait.** An alternating tetrapod: group A (`leg1_l`, `leg2_r`, `leg3_l`, `leg4_r`) and group B (the other four)
  are half a cycle apart. Each leg also leads the leg in front of it by 0.035 of a cycle, so steps ripple from back
  to front. Each leg's `phase_offset` is in the JSON.
- **Stance and swing.** With a cycle period of 0.5 s and a duty of 0.6, each foot is planted for 60% of the cycle and
  swings for 40%. Run the clock at `speed / stride`.
- **Where a foot lands.** At lift-off, aim for the foot's rest position (`rest_foot_cm`, or the reference pose of
  `ik_legN`) under where the body will be halfway through the next stance, then trace down to the ground.
- **Swing path.** Move horizontally with a smootherstep curve, add a lift arc (about 5 cm for a scuttle, peaking a
  little before mid-swing so the foot lifts quickly and sets down gently), and arc 1.2 cm outward. When moving sideways,
  the leading legs step about 20% higher than the trailing ones.
- **Body.** Fit a plane through the ground under the eight rest feet; set the body's height and tilt from it, and
  smooth both over about 0.1 s. Add a small bob that bottoms out 0.1 of a cycle after each set of feet lands.
- **Solve** the legs as in 10a.

### 10c. Secondary motion, aiming and claws

- **Springy eyes and antennae.** The baked clips already contain this. For procedural motion add one
  **AnimDynamics** node per eye stalk and antenna (Bound Bone `eye_l`, `antenna_l` and so on, Chain off), with angular
  limits of about ±13° for the eyes and ±25° for the antennae. The JSON lists the spring frequency, damping and limit
  used in the clips if you want to match them.
- **Watching the penguin.** A **Look At** node on `eye_l` and `eye_r` with the penguin's location as the target and
  **Look at Clamp** about 15° tilts the stalks toward it. The stalks run along each bone's Y axis.
- **Reaching with a claw.** A **FABRIK** node from `claw_arm_s` to `claw_tip_s` with the effector on a target (or on
  `ik_claw_s` after you move it) makes a claw reach for something, such as a fish on the ice. The claw opens by
  rotating `claw_pincer_s` about its X axis (negative opens; about 0.8 rad is wide open).

## Step 11: Gameplay tips

- **Attack range.** On the hit notify, the `claw_pinch_l` and `claw_pinch_r` bones are about 56 cm in front of the
  crab's centre and 8 cm above the ground, right at a penguin's feet. Use **Get Socket Location** with either bone name
  and a sphere overlap of radius 25 there. The exact positions are in `Reference/anim_events.json`.
- **Threat then attack.** A nice pattern: when the penguin comes within 3 m, play Crab_Threat once, then scuttle
  toward it. Within 60 cm, play Crab_Attack_Snap and wait for the montage to end before the next attack.
- **Keeping its distance.** Back the crab off with the backward walk after an attack, and layer Crab_Claw_Snap on
  top so it snaps while it retreats.
- **Getting hit.** Play Crab_Hit as a montage. It is short (0.67 s), so the crab can recover and keep chasing.
- **Death.** Set `IsDead`, stop movement, and set the capsule to ignore pawns so the penguin can walk past the
  upturned crab. The body ends lying on its back, centred near where it stood.
- **Variety.** Scale the actor between 0.6 and 1.4 for small and big crabs. Multiply the walk speeds by the same scale.
- **Many crabs.** With the levels of detail from Step 3, a distant crab costs 3,420 triangles. Rigid skinning keeps
  every level clean.

## Troubleshooting

| Problem | Fix |
|---|---|
| The crab faces sideways in the game | Rotate the Mesh component's yaw in BP_Crab (Step 8). Use the same axis settings for the mesh and the animations. |
| An extra `Armature` bone sits above `root` | Re-import the mesh. The files name the armature so Unreal drops it; a custom pipeline or plugin may keep it. |
| Everything is 100 times too big or too small | Re-import with scale 1.0 and Convert Scene Unit on. |
| A level of detail will not import | Import it onto `SK_Crab` with LOD Import (Step 3), not as a new asset. All four files share the skeleton. |
| The shell looks dented or lit from the wrong side | Use `T_Crab_Normal_DX.png`. The normal map embedded in the FBX is the OpenGL copy for Blender; tick Flip Green Channel on it, or replace it. |
| The crab looks flat and plasticky | Wire the ORM texture (Step 5). Roughness and the baked occlusion give the shell its depth. |
| Feet slide while scuttling or turning | Match Max Walk Speed to 50 and Rotation Rate to 60, or scale the play rate by speed / 50 and turn rate / 60. |
| The crab turns to face where it walks | Turn off Orient Rotation to Movement and give it a focus target (Step 8). |
| The turn plays the wrong way | Swap Crab_Turn_Left and Crab_Turn_Right in the Turning state (Step 9). |
| A leg bends the wrong way with IK | Check that the Joint Target is that leg's own `pole_legN` bone and the space is Bone Space (Step 10a). |
| Animations import onto a new skeleton | Pick `SK_Crab_Skeleton` in the import dialog (Step 6). |
| Old crab clips do not play on this crab | Bone names changed in this version. Re-import all twelve clips from this package. |

## Editing the crab

`Source_Blender/Crab.blend` holds the mesh, the three levels of detail (hidden, in their own collection) and the rig.
To pose it, drag an `ik_legN` bone to place a foot: the leg follows by IK, the knee aims at its `pole_legN` bone, and
the leg's point stays on the goal. Rotate the `claw_*`, `eye_*`, `antenna_*`, `mouthpart_*` and `body` bones directly.
The bone collections separate the skinned bones from the helpers. `Source_Blender/Crab_Anims.blend` has the twelve
clips as Blender actions. The model and animations come from scripts in the project repository
(`tools/build_crab.py`, `tools/make_crab_anims.py`), so for bigger changes edit those and re-export.
