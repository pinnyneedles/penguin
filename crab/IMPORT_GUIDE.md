# Crab: import into Unreal Engine 5

A red crab enemy for the penguin game. It comes as one skeletal mesh with a 36-bone skeleton, eight
animation clips, and a colour, normal and ORM texture set. This guide takes you from the zip to a crab
that scuttles, threatens, pinches, flinches and dies in your level. Plan on about 20 minutes the first time.

> These files were checked by re-importing them into a clean Blender scene, not inside an Unreal
> project. The steps below use settings that work with both Unreal FBX importers. Step 2 includes a
> quick check so you can confirm the result in your own editor.

---

## What is in the zip

| Folder | Contents |
|---|---|
| `Content/Meshes` | `SK_Crab.fbx`: skeletal mesh and skeleton in the rest pose, textures embedded |
| `Content/Animations` | Eight `AN_Crab_*.fbx` clips, skeleton only, one clip per file |
| `Content/Textures` | `T_Crab_BaseColor.png`, `T_Crab_Normal_DX.png` (normal map for Unreal) and `T_Crab_ORM.png` |
| `Reference` | `materials.csv`, `animations.csv`, `anim_events.json`, `mesh_stats.json` and the validation report |
| `Previews` | Renders and GIFs of the model and every animation |
| `Source_Blender` | `Crab.blend` (the rig with foot IK controls for posing) and `Crab_Anims.blend` (all eight clips) |

**Crab facts**

| | |
|---|---|
| Size | 63.5 cm across the shell, 97 cm leg tip to leg tip, 78 cm from claw tips to back legs, 32 cm tall. Pebble Chick is 152 cm tall, so the crab comes up to about its knee |
| Triangles | 33,336, two material slots (`M_Crab_Shell`, `M_Crab_Eye`) |
| Skeleton | 36 bones, top bone `root`: `body`, two eye stalks, four bones per claw, three per leg |
| Skinning | Rigid. Every piece of shell follows exactly one bone, as on a real crab, so nothing stretches |
| Claws | A heavy crusher claw on the right (32% bigger, with blunt molars) and a slimmer cutter on the left (fine sharp teeth), like many real crabs |
| Units | Centimetres, Z up, 30 fps |

---

## Step 1: Make a folder in your project

In the Content Browser create `Content/Characters/Crab` with four sub-folders:
`Meshes`, `Animations`, `Textures` and `Materials`. The rest of this guide assumes those names.

## Step 2: Import the skeletal mesh

1. Open `Characters/Crab/Meshes`, click **Import**, and pick `Content/Meshes/SK_Crab.fbx`.
2. Set the options. Which dialog you see depends on your engine version and settings:

    **If the dialog has sections called Common, Common Meshes and Skeletal Meshes (Interchange importer):**

    - Common Skeletal Meshes and Animations: **Import Only Animations** off, **Skeleton** empty (a new skeleton is created).
    - Skeletal Meshes: **Import Skeletal Meshes** on, **Import Content Type** = Geometry and Skinning Weights,
      **Create Physics Asset** on, **Import Morph Targets** off, **Update Skeleton Reference Pose** off.
      Common Skeletal Meshes and Animations: **Use T0 As Ref Pose** off.
    - Animations: **Import Animations** off (the mesh file has none).
    - Common: **Offset Uniform Scale** 1.0. Leave the offsets at zero.
    - Materials and textures: on is fine; you will set up the shell material in Step 4.

    **If you see the older FBX Import Options dialog:**

    - Mesh: **Skeletal Mesh** on, **Skeleton** None, **Import Mesh** on, **Create Physics Asset** on,
      **Import Morph Targets** off, **Update Skeleton Reference Pose** off, **Use T0 As Ref Pose** off.
    - Transform: **Import Uniform Scale** 1.0.
    - Miscellaneous: **Convert Scene** on, **Convert Scene Unit** on, **Force Front XAxis** off.
    - Animation: **Import Animations** off.

3. Click **Import**. You get `SK_Crab`, `SK_Crab_Skeleton` and `SK_Crab_PhysicsAsset` (names can vary slightly
    by version).
4. **Check it.** Open the skeletal mesh:
    - The crab should stand on the grid, about 32 cm tall and 97 cm across the legs. If it is tiny or 100 times
      too big, re-import with the scale at 1.0 and Convert Scene Unit on.
    - In the Skeleton Tree, the top bone should be `root` with `body` below it. If you see an extra bone called
      `Armature` above `root`, re-import the mesh.
    - Note which way the eyes and claws point. That is the crab's front, and you need it in Step 6.

## Step 3: Import the textures

1. Open `Characters/Crab/Textures` and import the three PNG files from `Content/Textures`.
2. Open `T_Crab_Normal_DX` and check **Compression Settings** = Normalmap and **sRGB** off. Unreal often detects
    normal maps on import; if it did not, set these two by hand. Leave **Flip Green Channel** off, because this file
    already uses Unreal's DirectX convention.
3. Open `T_Crab_ORM` and set **Compression Settings** = Masks (no sRGB). Its channels are R = ambient occlusion
    (baked), G = roughness and B = metallic (zero everywhere).
4. `T_Crab_BaseColor` keeps the defaults (sRGB on).

## Step 4: Set up the materials

1. In `Materials`, create **M_Crab_Shell**:
    - Texture Sample `T_Crab_BaseColor` into **Base Color**.
    - Texture Sample `T_Crab_Normal_DX` (sampler type Normal) into **Normal**.
    - Texture Sample `T_Crab_ORM` (sampler type Masks): **R** into **Ambient Occlusion**, **G** into **Roughness**,
      **B** into **Metallic**.
    - Optional damp sheen: set **Shading Model** to Clear Coat with **Clear Coat** 0.1 and **Clear Coat Roughness**
      0.2. Keep it subtle; a strong coat makes the shell look like plastic. With Substrate, add a thin coat layer instead.
2. Create **M_Crab_Eye**: a Constant3Vector (0.008, 0.007, 0.008) into **Base Color**, 0.06 into **Roughness**, and
    optionally Clear Coat 1.0. The eyes are glossy black beads; the reflections do the work.
3. Open `SK_Crab`, and in **Material Slots** assign each material to the slot with the same name.

## Step 5: Import the animations

1. Open `Characters/Crab/Animations` and import all eight files from `Content/Animations` in one go.
2. Settings:
    - **Interchange dialog:** Common Skeletal Meshes and Animations: **Import Only Animations** on and
      **Skeleton** = `SK_Crab_Skeleton`. Animations: **Import Animations** on, **Import Bone Tracks** on,
      **Animation Length** = the source or exported timeline option (not Set Range), **Snap to Closest Frame Boundary** on.
    - **Older dialog:** Mesh: **Import Mesh** off, **Skeleton** = `SK_Crab_Skeleton`. Animation: **Import Animations** on,
      **Animation Length** = Exported Time. Use the same Miscellaneous axis settings as the mesh in Step 2.
3. You get eight Animation Sequences:

    | Sequence | Frames | Length | Loops | What it does |
    |---|---|---|---|---|
    | Crab_Idle | 91 | 3.0 s | yes | breathing, eye stalks look around, a claw snip, a back leg shuffles |
    | Crab_Scuttle_Left | 15 | 0.47 s | yes | sideways run toward the crab's own left; planted feet match 50 cm/s |
    | Crab_Scuttle_Right | 15 | 0.47 s | yes | the same toward its right |
    | Crab_Walk_Forward | 25 | 0.8 s | yes | slow forward walk; planted feet match 22 cm/s |
    | Crab_Threat | 55 | 1.8 s | no | rears up, claws raised wide and open, snaps on frames 22 and 34 |
    | Crab_Attack_Snap | 33 | 1.07 s | no | wind-up, lunge and double pinch; the claws close on frame 13 |
    | Crab_Hit | 21 | 0.67 s | no | flinch: knocked back, eye stalks fold down, claws tucked in |
    | Crab_Death | 60 | 1.97 s | no | curls up, hops and flips onto its back (lands on frame 25), legs twitch, then still |

4. Quick test: drag `SK_Crab` into a level, select it, set **Animation Mode** = Use Animation Asset and pick any clip.
    It should play with the feet on the ground and no pop at the loop point.

All clips are in place: the root bone never moves, and your Character Movement moves the capsule. Looping clips repeat
their first pose as their last frame, which is what Unreal expects for a seamless loop. Every one-shot clip starts on
the idle's first pose, and every one except Death also ends there.

## Step 6: Character Blueprint

1. Create a Blueprint class based on **Character** called `BP_Crab`.
2. **Capsule Component:** Capsule Radius 34, Capsule Half Height 34. The capsule covers the shell. The legs reach past it
    on purpose, as a crab's legs splay wider than its body.
3. **Mesh** component: Skeletal Mesh Asset = `SK_Crab`, Location Z = -34 so the feet sit at the bottom of the capsule.
    Rotate it about Z (yaw) until the eyes and claws point along the blue Arrow component, which is the character's
    forward. Try 0 first, then -90 or 90, depending on what you saw in Step 2. **Collision Presets** on the mesh:
    CharacterMesh, or anything that does not block the capsule.
4. **Character Movement:** Max Walk Speed 50 for a perfect foot match while scuttling.
5. **Crabs walk sideways.** Turn **Orient Rotation to Movement** off, so the crab keeps facing its target and strafes.
    For an AI crab, call **Set Focus** with the penguin as the focus actor so it always faces the player, then move it
    with **AI Move To** or **Add Movement Input**. Movement to the side plays the scuttle, and movement toward the
    player plays the forward walk.

## Step 7: Animation Blueprint

1. Create an **Animation Blueprint** for `SK_Crab_Skeleton` called `ABP_Crab`, and set it as the Anim Class on the
    Mesh component of `BP_Crab`.
2. Make a **Blend Space** (2D) on the same skeleton called **BS_Crab_Locomotion**:
    - Horizontal axis `Side` from -50 to 50, vertical axis `Forward` from 0 to 22.
    - Put Crab_Idle at (0, 0), Crab_Scuttle_Left at (-50, 0), Crab_Scuttle_Right at (50, 0) and Crab_Walk_Forward at (0, 22).
3. In the Event Graph, on **Event Blueprint Update Animation**, get the pawn's velocity and set:
    - `Side` = Velocity · Actor Right Vector (positive when moving to the crab's right).
    - `Forward` = Velocity · Actor Forward Vector, clamped to 0..22.
    - `IsDead` = a bool your crab sets when it dies.
4. In the AnimGraph add a **State Machine** with two states, then a **Default Slot** after it for one-shots:

        Locomotion ──IsDead──▶ Dead

    - **Locomotion** plays BS_Crab_Locomotion with `Side` and `Forward`. Above 50 cm/s sideways, set its Play Rate to
      `max(1, abs(Side) / 50)` so the feet keep up.
    - **Dead** plays Crab_Death once with Loop off. It stops on its last frame, lying on its back.
    - Right-click Crab_Threat, Crab_Attack_Snap and Crab_Hit and choose **Create AnimMontage**. Play them from the crab's
      Blueprint with **Play Anim Montage**; they run through the Default Slot over the locomotion.
5. **AnimNotifies** for sound, effects and damage. Add them in each sequence's or montage's Notifies track:

    | Sequence | Frame | Event |
    |---|---|---|
    | Crab_Scuttle_Left / Right | 1 and 8 | footsteps (each frame plants four legs) |
    | Crab_Walk_Forward | 1 and 13 | footsteps |
    | Crab_Threat | 22 and 34 | claw snap |
    | Crab_Attack_Snap | 13 | hit: claws close, apply damage here |
    | Crab_Death | 25 | lands on its back |

    The same frames are in `Reference/anim_events.json`.

## Step 8: Gameplay tips

- **Attack range.** On the hit notify, the pincer tips are about ATTACK_REACH cm in front of the crab's centre and
  ATTACK_HEIGHT cm above the ground. A sphere overlap of radius 25 at that point catches a penguin standing in front.
- **Threat then attack.** A nice pattern: when the penguin comes within 3 m, play Crab_Threat once, then scuttle
  toward it. Within 60 cm, play Crab_Attack_Snap and wait for the montage to end before the next attack.
- **Getting hit.** Play Crab_Hit as a montage. It is short (0.67 s), so the crab can recover and keep chasing.
- **Death.** Set `IsDead`, stop movement, and set the capsule to ignore pawns so the penguin can walk past the
  upturned crab. The body ends lying on its back, centred near where it stood.
- **Variety.** Scale the actor between 0.6 and 1.4 for small and big crabs. Multiply the walk speeds by the same scale.
- **LODs.** At 33k triangles one crab is cheap. For a beach full of crabs, add LODs in **LOD Settings** (for example
  50%, 25% and 12% triangle targets). Rigid skinning keeps LODs clean.

## Troubleshooting

| Problem | Fix |
|---|---|
| The crab faces sideways in the game | Rotate the Mesh component's yaw in BP_Crab (Step 6). Use the same axis settings for the mesh and the animations. |
| An extra `Armature` bone sits above `root` | Re-import the mesh. The files name the armature so Unreal drops it; a custom pipeline or plugin may keep it. |
| Everything is 100 times too big or too small | Re-import with scale 1.0 and Convert Scene Unit on. |
| The shell looks dented or lit from the wrong side | Use `T_Crab_Normal_DX.png`. The normal map embedded in the FBX is the OpenGL copy for Blender; tick Flip Green Channel on it, or replace it. |
| The crab looks flat and plasticky | Wire the ORM texture (Step 4). Roughness and the baked occlusion give the shell its depth. |
| Feet slide while scuttling | Match Max Walk Speed to 50, or scale the play rate by speed / 50. |
| The crab turns to face where it walks | Turn off Orient Rotation to Movement and give it a focus target (Step 6). |
| Animations import onto a new skeleton | Pick `SK_Crab_Skeleton` in the import dialog (Step 5). |

## Editing the crab

`Source_Blender/Crab.blend` holds the mesh and a posing rig. Drag an `IK_foot` control to place a foot; the leg follows,
and the `POLE_knee` control above it sets the knee direction. Rotate the `claw_*`, `eye.*` and `body` bones directly.
The controls live in the **Controls** bone collection and are never exported. `Source_Blender/Crab_Anims.blend` has the
eight clips as Blender actions. The model and animations come from scripts in the project repository
(`tools/build_crab.py`, `tools/make_crab_anims.py`), so for bigger changes edit those and re-export.
