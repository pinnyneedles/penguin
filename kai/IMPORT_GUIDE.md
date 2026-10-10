# Kai: import into Unreal Engine 5

Kai is a young island sailor boy for a platformer, built in a Wind Waker-style toon look: red sailor shirt with a navy
collar, yellow sash and neckerchief, rolled khaki trousers and sandals. He is modular. Every clothing piece, both
hairstyles and the body parts are separate skeletal meshes on one shared 85-bone skeleton that uses the Unreal 5
Mannequin bone names, so you can swap parts and retarget Mannequin animations onto him. Steps 1 to 6 take you from the
zip to Kai standing in your level with a toon material, swappable parts and a working face. Plan on about 30 to 45
minutes the first time. The package has no animations yet; Step 7 covers retargeting.

> These files were checked by re-importing them into a clean Blender scene (`Reference/verify_report.json`), not inside
> an Unreal project. The steps use settings that work with both Unreal FBX importers, and several steps include a quick
> check so you can confirm the result in your own editor. Node and option names can differ slightly between engine
> versions.

---

## What is in the zip

| Folder | Contents |
|---|---|
| `Content/Meshes` | `SK_Kai.fbx`: the whole default outfit as one skeletal mesh (quick start). `SK_Kai_<Part>.fbx`: each part on its own, for a modular character (see the table below). Textures are embedded in every file |
| `Content/Textures` | One colour texture per part (`T_Kai_<Part>_BaseColor.png`) and `T_Kai_Eye_BaseColor.png` for the eyes and mouth |
| `Reference` | `bones.csv` (every bone, its parent and what it is for), `parts.csv`, `materials.csv`, `face_rig.json` (eyelid angles, eye and brow bones, mouth morph targets), `mesh_stats.json`, `verify_report.json` and the clipping reports |
| `Previews` | Renders: turnaround, close-ups of the face, ears and feet, the parts sheet and the face controls |
| `Source_Blender` | `Kai.blend`: every part, the skeleton and a posing rig (foot and hand IK, knee and elbow poles, eye look target) |

**The parts**

| File | Part | In the default outfit | Triangles | Material slots |
|---|---|---|---|---|
| `SK_Kai_Head.fbx` | Head, ears, eyes, eyelids, brows, mouth | yes | 21,066 | `M_Kai_Head`, `M_Kai_Eye` |
| `SK_Kai_Hair_Tousled.fbx` | Tousled hair | yes | 8,000 | `M_Kai_Hair_Tousled` |
| `SK_Kai_Hair_Spiky.fbx` | Spiky hair (alternate) | no | 8,000 | `M_Kai_Hair_Spiky` |
| `SK_Kai_Arms.fbx` | Arms and hands | yes | 9,000 | `M_Kai_Arms` |
| `SK_Kai_Tunic.fbx` | Shirt with sailor collar | yes | 13,000 | `M_Kai_Tunic` |
| `SK_Kai_Pants.fbx` | Rolled trousers | yes | 6,000 | `M_Kai_Pants` |
| `SK_Kai_Legs.fbx` | Calves | yes | 3,000 | `M_Kai_Legs` |
| `SK_Kai_Sandals.fbx` | Feet and sandals (one piece, so the straps never cut into the feet) | yes | 9,000 | `M_Kai_Sandals` |
| `SK_Kai_Sash.fbx` | Waist sash | yes | 3,000 | `M_Kai_Sash` |
| `SK_Kai_Neckerchief.fbx` | Neckerchief | yes | 1,600 | `M_Kai_Neckerchief` |
| `SK_Kai.fbx` | All of the default outfit in one mesh | | 73,666 | all of the above except the spiky hair |

**Kai facts**

| | |
|---|---|
| Size | 102.9 cm tall, standing on the origin in an A pose (arms 40° down) |
| Skeleton | 85 bones. The body uses the Unreal 5 Mannequin names (`root`, `pelvis`, `spine_01` to `spine_05`, `neck_01`, `neck_02`, `head`, clavicles, arms, 15 finger bones per hand, `thigh`, `calf`, `foot`, `ball`) and the Mannequin IK goal bones (`ik_foot_root`, `ik_foot_l/r`, `ik_hand_root`, `ik_hand_gun`, `ik_hand_l/r`). Extra bones: eyes, eyelids and brows; hair (`hair_front`, `hair_top`, `hair_back_01/02`, `hair_side_l/r`); sash tails (`sash_a_01..03`, `sash_b_01..03`); `collar_back`; `neckerchief`. See `Reference/bones.csv` |
| Skinning | Up to 4 bone influences per vertex. The skirt of the shirt follows the thighs toward its hem and the sash rides on it, so legs can run, jump, crouch, kick and step out without the clothes clipping (see Step 6) |
| Face | Eyes rotate on their bones and the lids close by bone rotation. Five mouth morph targets: `Mouth_Smile`, `Mouth_Open`, `Mouth_Shout`, `Mouth_O`, `Mouth_Frown` |
| Normals | The ears and the skin round the eyes carry custom normals for clean toon shading. Import them (Step 2) |
| Units | Centimetres, Z up, 30 fps |

---

## Step 1: Make a folder in your project

In the Content Browser make `Characters/Kai` with subfolders `Meshes`, `Textures` and `Materials`.

## Step 2: Import the meshes on one skeleton

All the parts share one skeleton. Import one file first to create it, then import the others onto it.

1. Open `Characters/Kai/Meshes`, click **Import**, and pick `Content/Meshes/SK_Kai_Tunic.fbx` only.
2. Set the options. Which dialog you see depends on your engine version and settings:

    **If the dialog has sections called Common, Common Meshes and Skeletal Meshes (Interchange importer):**

    - Common Skeletal Meshes and Animations: **Import Only Animations** off, **Skeleton** empty (a new skeleton is
      created), **Use T0 As Ref Pose** off.
    - Skeletal Meshes: **Import Skeletal Meshes** on, **Import Content Type** = Geometry and Skinning Weights,
      **Create Physics Asset** on, **Import Morph Targets** on, **Update Skeleton Reference Pose** off.
    - Common Meshes: **Recompute Normals** off and **Recompute Tangents** off (or **Normal Import Method** =
      Import Normals, if your version shows that option).
    - Animations: **Import Animations** off (the files have none).
    - Common: **Offset Uniform Scale** 1.0. Leave the offsets at zero.

    **If you see the older FBX Import Options dialog:**

    - Mesh: **Skeletal Mesh** on, **Skeleton** None, **Import Mesh** on, **Create Physics Asset** on,
      **Import Morph Targets** on, **Update Skeleton Reference Pose** off, **Use T0 As Ref Pose** off,
      **Normal Import Method** = Import Normals.
    - Transform: **Import Uniform Scale** 1.0.
    - Miscellaneous: **Convert Scene** on, **Convert Scene Unit** on, **Force Front XAxis** off.
    - Animation: **Import Animations** off.

3. Click **Import**. You get `SK_Kai_Tunic`, a skeleton (rename it `SK_Kai_Skeleton`) and a physics asset.
4. Import the other part files the same way, but set **Skeleton** to `SK_Kai_Skeleton` and turn
   **Create Physics Asset** off. If you only want one mesh, import `SK_Kai.fbx` instead of the parts.
5. **Check it.** Open `SK_Kai_Head`:
    - He should stand on the grid, about 103 cm tall. If he is tiny or 100 times too big, re-import with the scale at
      1.0 and Convert Scene Unit on.
    - In the Skeleton Tree the top bone is `root` with `pelvis`, `ik_foot_root` and `ik_hand_root` below it, 85 bones
      in all. If you see an extra bone called `Armature` above `root`, re-import the mesh.
    - In the Morph Target Previewer, `Mouth_Smile` should widen the mouth into a smile.
    - The ears should shade as a clean rim with a crescent, not in streaks. Streaks mean the normals were recomputed;
      re-import with Import Normals.
    - Note which way the face points. That is Kai's front, and you need it in Step 5.

## Step 3: Textures

The textures are embedded in the FBX files, so the importer may already have created them. If not, import everything
in `Content/Textures` into `Characters/Kai/Textures`. They are colour (sRGB) textures with no normal or ORM maps: in
this style, shape and colour carry the look, and the light comes from the toon material.

## Step 4: Toon material

Kai is designed for two-tone cel shading with dark outlines, like Wind Waker. A plain lit material also works and looks
soft and clean, but the toon setup is what the previews show.

**Two-tone material (`M_Kai_Toon`, one parent for every part):**

1. Create a material, **Shading Model** = Unlit.
2. Add a **Texture Sample** parameter `BaseColor` and a **Vector** parameter `ShadowTint` = (0.62, 0.56, 0.70).
3. Light direction: add a **Material Parameter Collection** `MPC_Toon` with a vector `SunDirection` (the direction
   *toward* the sun, normalised; set it from your directional light in the level Blueprint, or leave it at
   (−0.45, −0.62, 0.64)).
4. `Dot(PixelNormalWS, SunDirection)` → **SmoothStep** (Min −0.03, Max 0.03) → **Lerp** A = `BaseColor × ShadowTint`,
   B = `BaseColor`, Alpha = the SmoothStep result → **Emissive Color**.
5. Make one **Material Instance** per material slot (`MI_Kai_Head`, `MI_Kai_Eye`, `MI_Kai_Tunic`, and so on), set its
   `BaseColor` to the matching texture, and assign them in each skeletal mesh. `M_Kai_Eye` uses
   `T_Kai_Eye_BaseColor` for the eyes and mouth.

**Outlines.** Two common ways:

- Post-process outlines: a post-process material that draws dark lines where scene depth or normals change. One
  material covers everything on screen.
- Inverted hull (what the previews use): a second material on each part, **Two Sided** on, **Blend Mode** Masked,
  **Opacity Mask** = `1 − TwoSidedSign` clamped so only back faces draw, Emissive = (0.17, 0.11, 0.09), and
  **World Position Offset** = `VertexNormalWS × 0.2` (0.16 for the head). Add it as an extra material element or as a
  second skeletal mesh component that follows the first.

## Step 5: Character Blueprint with swappable parts

1. Create a Blueprint Class from **Character**, name it `BP_Kai`.
2. Capsule: **Half Height** 52, **Radius** 20.
3. Select the **Mesh** component, set it to `SK_Kai_Tunic`, **Location Z** −52, and rotate it about Z (yaw) until Kai's
   face points along the blue Arrow component, the character's forward direction. Try −90 first; if he then faces
   backwards or sideways, try 90 or 180.
4. Add a **Skeletal Mesh** component under Mesh for each other part: `Head`, `Hair`, `Arms`, `Pants`, `Legs`,
   `Sandals`, `Sash`, `Neckerchief`. Leave their transforms at zero.
5. In the Construction Script, call **Set Leader Pose Component** on each part component with **New Leader Bone
   Component** = Mesh. Every part then follows the Mesh's animation at no extra cost.
6. Swapping parts: call **Set Skeletal Mesh Asset** on a component (for example `Hair` to `SK_Kai_Hair_Spiky`), or hide
   a component (for example `Sash`) with **Set Visibility**. Every part is built to fit the others in any combination
   without clipping.
7. **Check it.** Drop `BP_Kai` in a level. All parts should line up exactly, with no gaps at the wrists, neck or
   ankles.

## Step 6: Face, hair and cloth

**Eyes.** `eye_l` and `eye_r` turn the eyeballs (the iris moves across the eye white). In an Animation Blueprint, a
**Look At** node on each eye bone with a target in front of the face makes him look around. Keep the angles small
(about ±20° side to side, ±12° up and down) so the iris stays inside the eye.

**Blinking.** Rotate `eyelid_upper_l` and `eyelid_upper_r` about their X axis by −68° to close the eyes; the lids slide
exactly over the eye. Rotate `eyelid_lower_l/r` by about +16° (up to +35°) for squints and smiles. Exact angles are in
`Reference/face_rig.json`. A **Transform (Modify) Bone** node driven by an animation curve such as `Blink` works well.

**Brows.** Move `brow_l` and `brow_r` up a little (about 1 cm along their Z) for surprise, and roll them for angry or
worried looks.

**Mouth.** Drive the five morph targets from animation curves of the same names, or with **Set Morph Target** in
Blueprint. They mix: `Mouth_Smile` at 0.5 with `Mouth_Open` at 0.3 gives a happy talking mouth.

**Hair, sash, collar and neckerchief.** These have their own bones for secondary motion. Add **AnimDynamics** nodes
in the Anim Blueprint (or a post-process Anim Blueprint on the parts): one per hair bone (Chain off, angular limits
about ±15°), the sash tails as chains (`sash_a_01` to `sash_a_03`, and the same for `sash_b`), `collar_back` and
`neckerchief` with limits about ±20°. The sash tail bones hang from the left thigh so the tails ride along when he
lifts his knee.

**Range of motion.** The shirt, sash and trousers stay clear of each other for running, jumping, crouch landings,
knee lifts up to 70°, leg swings back to 40° and side steps out to 45° (`Reference/pose_check.txt`). Deeper climbing
poses, with a thigh raised to about 80° or more, push the thigh into the front of the shirt. For those, add
**Chaos Cloth** to the shirt's skirt, or keep climbing animations below that angle.

## Step 7: Animations (retargeting)

The package has no animation clips yet. Because the body bones use the Mannequin names, Mannequin animations can be
retargeted:

1. Create an **IK Rig** for `SK_Kai_Tunic` (or `SK_Kai`) with chains Spine (`spine_01` to `spine_05`), Neck, Head,
   LeftArm and RightArm (`upperarm` to `hand`), LeftLeg and RightLeg (`thigh` to `ball`) and the fingers, with
   `pelvis` as the retarget root.
2. Create an **IK Retargeter** from the UE5 Mannequin IK Rig to Kai's. Kai is a child with a big head and short limbs,
   so turn on IK for the legs (planted feet) and lower the arm chains' FK blend if the hands drift. Line up both rest
   poses: Kai stands in an A pose with arms 40° down.
3. Export the retargeted clips onto `SK_Kai_Skeleton` and play them on `BP_Kai`. Every part follows through Leader Pose.

You can also animate in Blender with the posing rig in `Source_Blender/Kai.blend`: move the `CTRL_foot` and `CTRL_hand`
controls, the knee and elbow poles, and `CTRL_look` for the eyes. Export animations as FBX with **Armature** and
**Deform Bones Only** on, onto the same skeleton.

## Troubleshooting

| Problem | Fix |
|---|---|
| Kai faces sideways in the game | Rotate the Mesh component's yaw in BP_Kai (Step 5). |
| An extra `Armature` bone sits above `root` | Re-import the mesh. The files name the armature so Unreal drops it; a custom pipeline or plugin may keep it. |
| Everything is 100 times too big or too small | Re-import with scale 1.0 and Convert Scene Unit on. |
| Each part made its own skeleton | Re-import the parts with Skeleton = `SK_Kai_Skeleton` (Step 2). |
| Parts drift apart when he moves | Set Leader Pose Component on every part (Step 5). |
| Streaky shading on the ears or round the eyes | The custom normals were recomputed. Re-import with Import Normals and Recompute Normals off (Step 2). |
| The mouth does not move | Re-import `SK_Kai_Head` with Import Morph Targets on. |
| The eyes close only part way, or the lids show at rest | Rotate the upper lids about their own X axis by the angle in `face_rig.json` and start from the rest pose. |
| The shirt pokes through in a deep climb | See Range of motion in Step 6. |

## Editing Kai

Everything is generated from scripts in the repository's `tools` folder:

| Script | What it does |
|---|---|
| `kai_geometry.py` | Every shape (signed distance functions), the skeleton and the face rig. Proportions are at the top. |
| `kai_textures.py` | Colours and painted details. |
| `build_kai.py` | Meshes, skin weights, textures, morph targets, posing rig and FBX export: `python3 tools/build_kai.py --out kai` |
| `render_kai.py` | The preview renders. |
| `kai_clearance.py`, `kai_pose_check.py`, `verify_kai.py` | Checks for clipping at rest, clipping in leg poses, and the exported files. |
| `package_kai_unreal.py` | Builds this zip. |
