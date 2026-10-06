# Penguin Level Kit: import into Unreal Engine 5

This kit has 22 static meshes for penguin levels: ice blocks, ramps, slide-chute track pieces, an igloo,
ice floes, snow mounds, rocks, icicles and a fish collectible. Every mesh comes with its collision, and
the track pieces and igloo come with sockets. All pieces share three tileable texture sets. This guide
takes you from the zip to pieces placed in a level. Plan on about 15 minutes the first time.

> These files were checked by re-importing them into a clean Blender scene, not inside an Unreal
> project. The steps below use settings that work with both Unreal FBX importers. Step 4 includes
> a quick check so you can confirm the result in your own editor.

---

## What is in the zip

| Folder | Contents |
|---|---|
| `Content/Meshes` | 22 `SM_*.fbx` files. Each has the mesh, its `UCX_` collision shapes and any `SOCKET_` points |
| `Content/Textures` | `T_Ice_*`, `T_Snow_*` and `T_Rock_*` texture sets, each with BaseColor, Normal_DX and ORM |
| `Reference` | `props.csv` and `props_stats.json`: size, triangles, pivot, collision and sockets for every piece |
| `Previews` | `Kit_Sheet.png` (every piece), `Kit_Vignette.png` (a small level), `Igloo_Views.png` |
| `Source_Blender` | `Penguin_Kit.blend` with all pieces, plus the OpenGL normal maps it uses |

**Kit facts**

| | |
|---|---|
| Units | Centimetres, Z up. Pieces are sized on a 100 cm grid |
| Triangles | 36 (ramps) to about 10,900 (igloo); most pieces are under 1,300 |
| Collision | Custom convex shapes (`UCX_`) in every FBX, so Unreal doesn't need to generate any |
| Materials | `M_Ice`, `M_Snow`, `M_Rock`, `M_Fish` and `M_FishEye` slots |
| Textures | 1024 px and tileable. UVs are world-scaled: one tile covers 200 cm of ice or snow, or 100 cm of rock |
| Scale | Pebble Chick is 152 cm tall with a capsule radius of 45 cm. The chute channel is 200 cm wide, and the igloo doorway is 140 cm wide and 179 cm high |

---

## Step 1: Make a folder in your project

In the Content Browser create `Content/Environment/PenguinKit` with three sub-folders:
`Meshes`, `Textures` and `Materials`. The rest of this guide assumes those names.

## Step 2: Import the textures

1. Open `PenguinKit/Textures`, click **Import**, and pick all nine PNG files in `Content/Textures`.
2. Open each `T_*_Normal_DX` texture and check **Compression Settings** = Normalmap and **sRGB** off.
    Unreal often detects normal maps on import; if it did not, set these two by hand. Leave
    **Flip Green Channel** off, because these files already use Unreal's DirectX convention.
3. Open each `T_*_ORM` texture and set **Compression Settings** = Masks (no sRGB), which also turns sRGB off.
    The channels are R = ambient occlusion, G = roughness, B = metallic.
4. The `T_*_BaseColor` textures keep the defaults (sRGB on).

## Step 3: Build one master material and three instances

1. In `Materials`, create a material called **M_PenguinKit_Master** and open it:
    - A **Texture Sample Parameter 2D** named `BaseColor`, set to `T_Snow_BaseColor`, into **Base Color**.
    - A **Texture Sample Parameter 2D** named `Normal`, set to `T_Snow_Normal_DX` (sampler type Normal), into **Normal**.
    - A **Texture Sample Parameter 2D** named `ORM`, set to `T_Snow_ORM` (sampler type Masks). Wire its
      **R** into **Ambient Occlusion**, **G** into **Roughness** and **B** into **Metallic**.
    - Optional ice glow: a **Fresnel** node (exponent 3) multiplied by a **Vector Parameter** `RimColor`
      (0.25, 0.55, 0.75) and a **Scalar Parameter** `RimStrength` (default 0), into **Emissive Color**.
2. Save it, then right-click it and choose **Create Material Instance** three times:
    - **MI_Ice**: the `T_Ice_` textures, and `RimStrength` 0.3 if you added the glow.
    - **MI_Snow**: the `T_Snow_` textures (the defaults).
    - **MI_Rock**: the `T_Rock_` textures.

The fish uses flat colours, so its materials come straight from the FBX in Step 4.

## Step 4: Import the meshes

1. Open `PenguinKit/Meshes`, click **Import**, and pick all 22 files in `Content/Meshes` at once.
2. Set the options. Which dialog you see depends on your engine version and settings:

    **If the dialog has sections called Common, Common Meshes and Static Meshes (Interchange importer):**

    - Common Meshes: **Force All Meshes as Type** = Static Mesh.
    - Static Meshes: **Import Static Meshes** on, **Combine Static Meshes** on,
      **Import Collision According to Mesh Name** on (this reads the `UCX_` shapes), **Import Sockets** on.
      If your version also offers to generate collision, turn that off: the `UCX_` shapes are the collision.
    - Materials: on. Unreal creates placeholder materials named after the slots, and Step 5 swaps them for your instances.
    - Textures: off. The meshes don't reference textures; the materials do.
    - Common: **Offset Uniform Scale** 1.0. Leave the offsets at zero.

    **If you see the older FBX Import Options dialog:**

    - Mesh: **Skeletal Mesh** off, **Auto Generate Collision** off, **One Convex Hull Per UCX** on,
      **Combine Meshes** on. **Generate Lightmap UVs** is only needed if you bake lighting; leave it off for Lumen.
    - Transform: **Import Uniform Scale** 1.0.
    - Miscellaneous: **Convert Scene** on, **Convert Scene Unit** on, **Force Front XAxis** off.
    - Material: **Material Import Method** = Create New Materials, **Import Textures** off.

3. Click **Import**. You get 22 static meshes and five placeholder materials: `M_Ice`, `M_Snow`, `M_Rock`,
    `M_Fish` and `M_FishEye`.
4. **Check it.**
    - Open `SM_IceBlock_200`. It should be 200 × 200 × 200 cm, shown as Approx Size in the Details panel. If it is
      100 times too big or small, re-import with the scale at 1.0 and Convert Scene Unit on.
    - In the same editor, turn on **Show > Simple Collision**. You should see one box hugging the block.
      If you see a box drawn by Unreal or no collision at all, the `UCX_` shapes weren't picked up; re-import with
      the collision options above.
    - Open `SM_SlideChute_Straight_400`. The **Socket Manager** should list `SOCKET_Start` and `SOCKET_End`.
    - Open `SM_Igloo` with Simple Collision on. The wall should be covered in convex pieces, with the doorway,
      tunnel and room left open.

## Step 5: Swap in your materials (all meshes at once)

Every mesh that uses ice now points at the placeholder `M_Ice`. Replacing that one asset fixes all of them:

1. In `Materials`, select both **M_Ice** and **MI_Ice**, then right-click and choose
    **Asset Actions > Replace References**.
2. In the dialog, pick **MI_Ice** as the asset to keep and confirm. Every mesh now uses `MI_Ice`, and the
    placeholder is removed.
3. Do the same for `M_Snow` with `MI_Snow`, and for `M_Rock` with `MI_Rock`.
4. Keep `M_Fish` and `M_FishEye`. They already have the fish colours: gold (0.90, 0.40, 0.05) at
    roughness 0.3, and near-black (0.01, 0.01, 0.012) at roughness 0.1.

If **Replace References** isn't in your menu, open each mesh and set its slots in **Material Slots** instead.

## Step 6: Build a level

**Snapping.** Turn on grid snapping at 50 or 100 and rotation snapping at 90°. Blocks, ramps and chute
pieces are multiples of 100 cm, so they line up exactly.

**Pivots**

| Pieces | Pivot |
|---|---|
| Blocks, slab, ramps, mounds, rocks, floes | On the floor at the centre of the footprint |
| Slide-chute pieces | Centre of the entrance floor. The chute runs along +X |
| Igloo | Floor centre of the dome. The entrance tunnel points along +X |
| Icicles | Top centre, so they hang from wherever you place them |
| Fish | Centre |

**Chaining the slide track.** Each chute piece ends where the next one starts. Place the next piece at the
previous piece's `SOCKET_End`:

| Piece | `SOCKET_End` relative to the piece | Turn |
|---|---|---|
| `SM_SlideChute_Straight_400` | (400, 0, 0) | none |
| `SM_SlideChute_CurveLeft_90` | (400, 400, 0) | +90° yaw |
| `SM_SlideChute_CurveRight_90` | (400, −400, 0) | −90° yaw |
| `SM_SlideChute_Slope_400x100` | (400, 0, −100) | none (drops 100 cm, level at both ends) |
| `SM_SlideChute_Kicker_400` | (400, 0, 30) | launches 25° upward; end the track here |

By hand: move the next piece by the offset, rotated by the previous piece's yaw, and add the turn to its yaw.
With grid snapping on, every joint lands on the grid.

In a Blueprint: make an Actor with an array of Static Mesh assets. In the Construction Script, add a Static
Mesh Component for each entry. Set its transform to the previous component's
**Get Socket Transform** (`SOCKET_End`, World Space). The track rebuilds whenever you edit the array.

**The igloo.** The room is 500 cm across and 264 cm high, and the doorway is 140 × 179 cm, so the chick can
walk in. Inside there is a 45 cm snow bench against the back wall, and one ice block in the back wall serves
as a window. It has three sockets:

- `SOCKET_Entrance` at the tunnel mouth, for a door trigger or spawn point.
- `SOCKET_Interior` at the centre of the floor.
- `SOCKET_Bench` on top of the bench, for a sleeping or resting spot.

**Other pieces**

- Ice floes: place them in water with about a third below the surface.
- Icicles: to make them a hazard, set the collision preset to OverlapAllDynamic and handle **On Component
  Begin Overlap** to damage the player.
- Fish: make a Blueprint with the fish mesh (collision preset OverlapAllDynamic) and a Rotating Movement
  component. On overlap with the player, add to the score and destroy the actor.

## Step 7: Optional polish

- **Nanite.** The igloo and rocks are the densest pieces. Turning on Nanite for them (Static Mesh editor,
  **Nanite Settings**) is safe, because all the kit materials are opaque.
- **LODs.** Without Nanite, give `SM_Igloo` three LODs (**LOD Settings > Number of LODs** = 3).
- **Scaling pieces.** UVs are world-scaled, so a piece scaled non-uniformly stretches its texture. If you scale
  pieces a lot, switch the master material to **World Aligned Texture** nodes.

## Troubleshooting

| Problem | Fix |
|---|---|
| A piece is 100 times too big or small | Re-import with Import Uniform Scale 1.0 and Convert Scene Unit on |
| No collision, or a single box around a chute or the igloo | The `UCX_` shapes were not used. Re-import with Import Collision According to Mesh Name (Interchange) or One Convex Hull Per UCX with Auto Generate Collision off (older dialog) |
| Bumps look lit from the wrong side | A `_Normal_GL` texture was used. Use the `_Normal_DX` files in `Content/Textures` |
| ORM looks washed out or too shiny | The ORM texture still has sRGB on. Set Compression Settings to Masks (no sRGB) |
| Chute pieces don't meet | Chute pivots are at the entrance floor, not the middle. Use the socket offsets above |
| The chick can't get into the igloo | Check that the mesh uses its simple collision (Show > Simple Collision). The doorway is 140 cm wide, so a capsule radius above 70 won't fit |
