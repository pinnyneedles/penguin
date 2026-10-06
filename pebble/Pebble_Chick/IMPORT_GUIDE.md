# Pebble Chick: import into Unreal Engine 5

A brown king penguin chick, ready for a third-person game: one skeletal mesh, a 16-bone skeleton,
eleven animation clips, and the textures for its down. This guide takes you from the zip to a
walking, jumping, belly-sliding character. Plan on about 20 minutes the first time.

> These files were checked by re-importing them into a clean Blender scene, not inside an
> Unreal project. The steps below use settings that work with both Unreal FBX importers. Step 2
> includes a quick check so you can confirm the result in your own editor.

---

## What is in the zip

| Folder | Contents |
|---|---|
| `Content/Meshes` | `SK_Pebble_Chick.fbx`: skeletal mesh and skeleton in the rest pose, textures embedded |
| `Content/Animations` | Eleven `AN_Pebble_Chick_*.fbx` clips, skeleton only, one clip per file |
| `Content/Textures` | `T_Chick_Body_BaseColor.png` (colour) and `T_Chick_Body_Normal_DX.png` (normal map for Unreal) |
| `Reference` | `materials.csv`, `animations.csv`, `anim_events.json` and the validation report |
| `Previews` | Renders and GIFs of the model and every animation |
| `Source_Blender` | The editable Blender scenes, if you want to change the model or animations |

**Character facts**

| | |
|---|---|
| Height | 152 cm (about 1.5 m, a large stylised chick; scale it in Unreal if you want it smaller) |
| Width | 84 cm body, 91 cm flipper to flipper |
| Triangles | 49,124, eight material slots |
| Skeleton | 16 bones, top bone `root`, no extra armature bone |
| Units | centimetres, Z up, 30 fps |

---

## Step 1: Make a folder in your project

In the Content Browser create `Content/Characters/PebbleChick` with four sub-folders:
`Meshes`, `Animations`, `Textures` and `Materials`. The rest of this guide assumes those names.

## Step 2: Import the skeletal mesh

1. Open `Characters/PebbleChick/Meshes`, click **Import**, and pick `Content/Meshes/SK_Pebble_Chick.fbx`.
2. Set the options. Which dialog you see depends on your engine version and settings:

    **If the dialog has sections called Common, Common Meshes and Skeletal Meshes (Interchange importer):**

    - Common Skeletal Meshes and Animations: **Import Only Animations** off, **Skeleton** empty (a new skeleton is created).
    - Skeletal Meshes: **Import Skeletal Meshes** on, **Import Content Type** = Geometry and Skinning Weights,
      **Create Physics Asset** on (you can tidy it later), **Import Morph Targets** off,
      **Update Skeleton Reference Pose** off. Common Skeletal Meshes and Animations: **Use T0 As Ref Pose** off.
    - Animations: **Import Animations** off (the mesh file has none).
    - Common: **Offset Uniform Scale** 1.0. Leave the offsets at zero.
    - Materials and textures: on is fine; you will replace the body material in Step 4.

    **If you see the older FBX Import Options dialog:**

    - Mesh: **Skeletal Mesh** on, **Skeleton** None, **Import Mesh** on, **Create Physics Asset** on,
      **Import Morph Targets** off, **Update Skeleton Reference Pose** off, **Use T0 As Ref Pose** off.
    - Transform: **Import Uniform Scale** 1.0.
    - Miscellaneous: **Convert Scene** on, **Convert Scene Unit** on, **Force Front XAxis** off.
    - Animation: **Import Animations** off.

3. Click **Import**. You get `SK_Pebble_Chick`, `SK_Pebble_Chick_Skeleton` and `SK_Pebble_Chick_PhysicsAsset`
    (names can vary slightly by version).
4. **Check it.** Open the skeletal mesh:
    - The chick should stand on the grid and be about 152 cm tall. If it is tiny or 100 times too big, re-import
      with the scale at 1.0 and Convert Scene Unit on.
    - In the Skeleton Tree, the top bone should be `root` with `pelvis` below it. If you see an extra bone
      called `Armature` above `root`, re-import the mesh. That bone would block root motion.
    - Note which way the bill points. You need it in Step 6.

## Step 3: Import the textures

1. Open `Characters/PebbleChick/Textures` and import both PNG files from `Content/Textures`.
2. Open `T_Chick_Body_Normal_DX` and check **Compression Settings** = Normalmap and **sRGB** off.
    Unreal often detects normal maps on import; if it did not, set these two by hand. Leave **Flip Green Channel** off,
    because this file is already in Unreal's DirectX convention.
3. `T_Chick_Body_BaseColor` keeps the defaults (sRGB on).

## Step 4: Set up the materials

The FBX import may have created materials automatically. You can keep them for the seven flat-colour
slots, but build the body material yourself so the normal map is right.

1. In `Materials`, create **M_Chick_Body**:
    - Texture Sample `T_Chick_Body_BaseColor` into **Base Color**.
    - Texture Sample `T_Chick_Body_Normal_DX` (sampler type Normal) into **Normal**.
    - Constant 0.8 into **Roughness**, 0 into **Metallic**.
    - Optional soft fuzz: set **Shading Model** to Cloth, plug a Constant3Vector (0.55, 0.38, 0.24) into
      **Fuzz Color** and a constant 0.2 into **Cloth**. With Substrate, use a Slab with a little Fuzz Amount instead.
2. For the other slots, make simple materials, or one master material with a colour and roughness parameter
    plus instances. The values are linear colours, which is what a Constant3Vector expects:

    | Slot (as named on the mesh) | Used for | Base Color (linear) | Roughness |
    |---|---|---|---|
    | M_Chick_Body | down: body, flippers, tail | the two textures above | 0.80 |
    | M_Chick_Foot | legs, feet, eyelids | 0.030, 0.028, 0.030 | 0.62 |
    | M_Chick_Claw | claws | 0.075, 0.070, 0.065 | 0.35 |
    | M_Chick_Iris | eyeballs | 0.030, 0.016, 0.009 | 0.12 |
    | M_Chick_Pupil | pupils | 0.009, 0.008, 0.010 | 0.19 |
    | M_Chick_Glint | eye highlights | 1.000, 0.980, 0.900 | 0.20 |
    | M_Chick_Bill | upper bill | 0.022, 0.019, 0.021 | 0.32 |
    | M_Chick_BillLower | lower bill | 0.050, 0.043, 0.043 | 0.38 |

    No surface is metallic. The same values are in `Reference/materials.csv`.

3. Open `SK_Pebble_Chick`, and in **Material Slots** assign each material to the slot with the same name.

## Step 5: Import the animations

1. Open `Characters/PebbleChick/Animations` and import all eleven files from `Content/Animations` in one go.
2. Settings:
    - **Interchange dialog:** Common Skeletal Meshes and Animations: **Import Only Animations** on and
      **Skeleton** = `SK_Pebble_Chick_Skeleton`. Animations: **Import Animations** on, **Import Bone Tracks** on,
      **Animation Length** = the source or exported timeline option (not Set Range), **Snap to Closest Frame Boundary** on.
    - **Older dialog:** Mesh: **Import Mesh** off, **Skeleton** = `SK_Pebble_Chick_Skeleton`.
      Animation: **Import Animations** on, **Animation Length** = Exported Time. The clips are 30 fps, so the sample-rate option can stay at its default.
      Use the same Miscellaneous axis settings as the mesh in Step 2.
3. You get eleven Animation Sequences. Rename them if you like; this guide uses the names below.

    | Sequence | Frames | Length | Loops | What it does |
    |---|---|---|---|---|
    | Chick_Idle | 91 | 3.0 s | yes | breathing, weight shift, a slow glance; feet planted |
    | Chick_Waddle | 33 | 1.07 s | yes | walk cycle in place; feet match the ground at 23.25 cm/s |
    | Chick_Waddle_RootMotion | 33 | 1.07 s | yes | same walk; the root bone carries 24.8 cm per cycle |
    | Chick_Jump_Start | 10 | 0.30 s | no | crouch and launch |
    | Chick_Jump_Loop | 25 | 0.80 s | yes | in the air, rising or falling |
    | Chick_Jump_Land | 18 | 0.57 s | no | feet plant on frame 3, squash, settle |
    | Chick_BellySlide_Start | 28 | 0.93 s | no | crouch, lunge, flop onto the belly (impact on frame 17) |
    | Chick_BellySlide_Loop | 65 | 2.13 s | yes | push left (frame 10), push right (frame 20), glide; head sways with the rocking |
    | Chick_BellySlide_Loop_LeanLeft | 65 | 2.13 s | yes | the slide banked into a left turn |
    | Chick_BellySlide_Loop_LeanRight | 65 | 2.13 s | yes | the slide banked into a right turn |
    | Chick_BellySlide_End | 28 | 0.93 s | no | push up with the flippers and stand |

4. Open **Chick_Waddle_RootMotion** and tick **Enable Root Motion**. Leave it off on every other clip;
    they are in place and your Character Movement moves the capsule.
5. Quick test: drag `SK_Pebble_Chick` into a level, select it, set **Animation Mode** = Use Animation Asset and
    pick any clip. It should play with feet on the ground and no pops at the loop point.

Looping clips repeat their first pose as their last frame, which is what Unreal expects for a seamless loop.
Every one-shot clip starts or ends on the idle's first pose or on its loop's first frame, so they chain cleanly.

## Step 6: Character Blueprint

1. Create a Blueprint class based on **Character** called `BP_PebbleChick`.
2. **Capsule Component:** Capsule Half Height 76, Capsule Radius 45.
3. **Mesh** component: Skeletal Mesh Asset = `SK_Pebble_Chick`, Location Z = -76 so the feet sit at the bottom
    of the capsule. Rotate it about Z (yaw) until the bill points along the blue Arrow component, which is the
    character's forward. Try 0 first, then -90 or 90, depending on what you saw in Step 2.
    **Collision Presets** on the mesh: CharacterMesh, or anything that does not block the capsule.
4. **Character Movement:** Max Walk Speed 23.25 for a perfect foot match. For a faster chick, use a higher
    speed and scale the waddle's play rate by speed / 23.25 (see Step 7). Jump Z Velocity is up to your game.

## Step 7: Animation Blueprint

1. Create an **Animation Blueprint** for `SK_Pebble_Chick_Skeleton` called `ABP_PebbleChick`, and set it as
    the Anim Class on the Mesh component of `BP_PebbleChick`.
2. Make two Blend Spaces 1D on the same skeleton:
    - **BS_Chick_Locomotion**: horizontal axis `Speed` from 0 to 23.25. Put Chick_Idle at 0 and Chick_Waddle at 23.25.
    - **BS_Chick_Slide**: axis `Steer` from -1 to 1. Put Chick_BellySlide_Loop_LeanRight at -1,
      Chick_BellySlide_Loop at 0 and Chick_BellySlide_Loop_LeanLeft at 1. The three clips have the same length
      and timing, so they blend cleanly.
3. In the Event Graph, on **Event Blueprint Update Animation**, set these variables from the owning pawn:
    - `Speed` = length of the velocity in XY.
    - `IsFalling` = Character Movement **Is Falling**.
    - `IsSliding` = a bool your character sets while sliding.
    - `Steer` = your turn input, -1 for right to +1 for left.
4. In the AnimGraph add a **State Machine**:

        Locomotion ──IsFalling──▶ JumpStart ──(time remaining < 0.1)──▶ JumpLoop ──!IsFalling──▶ JumpLand ──(time remaining < 0.1)──▶ Locomotion
        Locomotion ──IsSliding──▶ SlideStart ──(time remaining < 0.1)──▶ Sliding ──!IsSliding──▶ SlideEnd ──(time remaining < 0.1)──▶ Locomotion

    - **Locomotion** plays BS_Chick_Locomotion with `Speed`. For speeds above 23.25 cm/s, set its Play Rate to
      `max(1, Speed / 23.25)` so the feet keep up.
    - **JumpStart, JumpLand, SlideStart and SlideEnd** play their clip once (Loop off).
    - **JumpLoop** plays Chick_Jump_Loop looping. **Sliding** plays BS_Chick_Slide with `Steer`.
    - A blend time of 0.1 to 0.2 s on the transitions works well.
5. **AnimNotifies** for sound and effects. Add them in each sequence's Notifies track:

    | Sequence | Frame | Event |
    |---|---|---|
    | Chick_Waddle | 1 and 17 | footstep (left, right) |
    | Chick_Jump_Land | 3 | landing thump |
    | Chick_BellySlide_Start | 17 | belly hits the snow |
    | Chick_BellySlide_Loop | 10 and 20 | push (left foot, right foot) |

    The same frames are in `Reference/anim_events.json`.

## Step 8: Gameplay tips

- **Belly slide.** While sliding, lower the capsule to about half-height 57 and radius 55, because the lying body
  is about 148 cm wide, 184 cm long and 105 cm tall, centred over the root. For a push-and-glide feel, give the
  character a short burst of speed on each push notify (frames 10 and 20) and let friction slow it in between.
  The belly sits 1 cm below the root on purpose, to read as pressing into snow. On a hard floor, raise the mesh
  by 1 cm while sliding.
- **Jump.** The clips have no height in them; your Jump Z Velocity does the lifting. Jump_Start is short
  (0.3 s) so the jump feels responsive.
- **Root motion.** If you prefer root-motion walking, use Chick_Waddle_RootMotion in the locomotion state and
  set **Root Motion Mode** in the Anim Blueprint's class defaults to Root Motion from Everything. (Root Motion
  from Montages Only works only if you play the clip as an Anim Montage.)
- **LODs.** At 49k triangles the chick is fine as a player character. For crowds, open the skeletal mesh and
  add LODs in **LOD Settings** (for example 50%, 25% and 12% triangle targets).
- **Fur.** The geometry and normal map carry the down. For extra wispy fuzz up close, add a Groom bound to
  the mesh. The reference notes in the repository explain the Blender-to-Groom workflow.

## Troubleshooting

| Problem | Fix |
|---|---|
| The chick faces sideways in the game | Rotate the Mesh component's yaw in BP_PebbleChick (Step 6). Use the same axis settings for the mesh and the animations. |
| An extra `Armature` bone sits above `root` | Re-import the mesh. The files name the armature so Unreal drops it; a custom pipeline or plugin may keep it. |
| Everything is 100 times too big or too small | Re-import with scale 1.0 and Convert Scene Unit on. |
| The down looks dented or lit from the wrong side | Use `T_Chick_Body_Normal_DX.png`, or tick Flip Green Channel on a normal map that came out of the FBX. |
| Two materials per slot, or untextured body | Delete the auto-created materials and assign the ones from Step 4. |
| Feet slide while walking | Match Max Walk Speed to 23.25, or scale the waddle's play rate by speed / 23.25. |
| The walk drifts forward on its own | Root motion is on for a clip that should be in place. Only Chick_Waddle_RootMotion uses it. |
| Animations import onto a new skeleton | Pick `SK_Pebble_Chick_Skeleton` in the import dialog (Step 5). |

## Editing the character

`Source_Blender/Pebble_Chick_Anims.blend` holds the mesh, rig and all eleven animations as Blender actions.
The model and animations are generated by scripts in the project repository (`tools/build_pebble_chick.py`,
`tools/make_chick_anims.py`), so change them there and re-export rather than editing the baked keys by hand.
