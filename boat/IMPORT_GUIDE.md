# Kai's boat: import into Unreal Engine 5 and drive it

A small toon motorboat for Kai: a short, chubby cream-and-red wooden skiff with a navy rub rail, a retro red outboard
motor, and a little rounded helm console with a cream steering wheel and a throttle. Kai climbs in, sits at the wheel and drives. He leans and looks
into turns, the wheel turns, the outboard swings and the propeller spins. The boat floats, bobs, turns, coasts to a
stop and carries Kai with it.

Everything is set up for Blueprints:

- **Meshes:** four static meshes (hull, motor, propeller, wheel). Simple convex collision and 21 named sockets are
  already inside the files.
- **Animations:** five driving poses for Kai on his skeleton, for a blend space.
- **This guide:** builds `BP_KaiBoat`, a Pawn with physics buoyancy, thrust and water drag. It works on any water that
  is a flat surface at a known height, with optional waves. Enhanced Input controls it, and Kai gets in and out with
  one button.

Plan on about an hour the first time. You need Kai imported first (`Kai_Unreal.zip`, Steps 1 to 5 of its guide).

> These files were checked by re-importing them into a clean Blender scene (`Reference/verify_report.json`). The
> Blueprint's physics was checked by simulating the same forces in Python, at 30, 60 and 120 frames per second
> (`Reference/physics_tuning.json`). None of this was run inside an Unreal project, so each step ends with a quick
> check you can do in your own editor. Node and option names can differ slightly between engine versions.

---

## What is in the zip

| Folder | Contents |
|---|---|
| `Content/Meshes` | `SM_Boat_Hull.fbx` (with 22 collision pieces and 21 sockets), `SM_Boat_Motor.fbx` (2 collision pieces, sockets `Propeller` and `Exhaust`), `SM_Boat_Propeller.fbx`, `SM_Boat_Wheel.fbx` |
| `Content/Animations` | `AN_Kai_Boat_Drive`, `AN_Kai_Boat_Steer_Left`, `AN_Kai_Boat_Steer_Left_Half`, `AN_Kai_Boat_Steer_Right_Half`, `AN_Kai_Boat_Steer_Right` (animation only, for `SK_Kai_Skeleton`) |
| `Content/Textures` | One colour texture per mesh (`T_Boat_*_BaseColor`) |
| `Reference` | `sockets.csv` (every socket in Unreal coordinates), `physics_tuning.json` (the Blueprint values and the simulated results), check reports |
| `Previews` | Renders of the boat and of Kai driving |
| `Source_Blender` | `Boat.blend` (the boat) and `Kai_Boat.blend` (Kai seated at the wheel with the five poses) |

## The boat at a glance

| | |
|---|---|
| Size | 2.0 m long, 1.2 m wide, sides 35 to 63 cm high; Kai (103 cm) sits at the wheel near the stern |
| Hull origin | On the centreline at the bottom of the keel, amidships. The bow points along +X, the actor's forward. |
| Floats at | 5 cm up the keel (the design waterline, just below the red-and-navy stripe), with the floorboards dry |
| Motor | Origin on its steering axis. Turn it about Z (yaw) to steer, up to 25° each way. |
| Propeller | Origin at the hub. Spin it about X (roll). |
| Wheel | Origin at the hub, X along the steering column. Turn it about X (roll), up to 60° each way. |
| Triangles | Hull 17,189 · motor 6,000 · propeller 1,600 · wheel 4,000 |

**Sockets on the hull** (positions in `Reference/sockets.csv`):

| Socket | Use |
|---|---|
| `Seat_Driver` | Attach Kai's actor here when he drives. It is his capsule centre, so his root lands on `Driver_Root`. |
| `Driver_Root` | Where Kai's root bone sits while driving (feet on the floorboards) |
| `Seat_Passenger` | The same for a passenger on the middle seat |
| `Board_Stand` | A standing spot inside the boat |
| `Exit_Port`, `Exit_Starboard` | Where Kai steps off, beside the boat; the Blueprint traces down from here for ground |
| `Motor_Mount` | Attach `SM_Boat_Motor` |
| `Wheel` | Attach `SM_Boat_Wheel` |
| `Throttle` | The throttle knob, for a hand effect or sound |
| `Camera_Boom` | Attach the spring arm |
| `Pontoon_Bow`, `_FL`, `_FR`, `_ML`, `_MR`, `_SL`, `_SR` | The seven buoyancy points |
| `Bow_Spray_L`, `Bow_Spray_R`, `Wake` | Spray and wake effects (`Wake` faces backwards) |
| `Bow_Light` | The red and green bow light, for a small point light |

---

## Step 1: Import the meshes

1. In the Content Browser make `Vehicles/KaiBoat` with subfolders `Meshes`, `Textures`, `Materials` and `Animations`.
2. In `Meshes`, click **Import** and pick the four files in `Content/Meshes`.
3. Set the options. Which dialog you see depends on your engine version and settings:

    **If the dialog has sections called Common, Common Meshes and Static Meshes (Interchange importer):**

    - Static Meshes: **Import Static Meshes** on, **Combine Static Meshes** off, **Import Collision** on,
      **Import Collision According To Mesh Name** on, **One Convex Hull Per UCX** on. The `UCX_` pieces then
      replace any generated collision, whatever the Collision type dropdown says, and the sockets import by
      themselves.
    - Common Meshes: **Recompute Normals** off, **Recompute Tangents** off.
    - Common: **Offset Uniform Scale** 1.0.

    If an option isn't in your version's dialog, skip it.

    **If you see the older FBX Import Options dialog:**

    - Mesh: **Auto Generate Collision** off, **One Convex Hull Per UCX** on, **Combine Meshes** off,
      **Normal Import Method** = Import Normals.
    - Transform: **Import Uniform Scale** 1.0.
    - Miscellaneous: **Convert Scene** on, **Convert Scene Unit** on, **Force Front XAxis** off.

4. **Check it.** Open `SM_Boat_Hull`:
    - It should be 2.0 m long with the bow pointing along the red X arrow. If it is 100 times too big or too small,
      re-import with scale 1.0 and Convert Scene Unit on.
    - **Show → Simple Collision** should show 22 green shapes: the bottom, the sides, the solid bow, the transom, the
      seats and the console. If you see one blob around the whole boat, collision was auto-generated. Re-import with
      Auto Generate Collision off.
    - **Window → Socket Manager** should list 21 sockets.
    - Open `SM_Boat_Motor`. Its pivot should be on the vertical tube in the middle of the motor's clamp, and it should
      have the sockets `Propeller` and `Exhaust`.

## Step 2: Materials

The boat uses the same toon material as Kai. If you made `M_Kai_Toon` (Kai's guide, Step 4), make four
**Material Instances** of it in `Materials`: `MI_Boat_Hull`, `MI_Boat_Motor`, `MI_Boat_Propeller` and `MI_Boat_Wheel`.
Set each one's `BaseColor` to the matching `T_Boat_*_BaseColor`, then assign it to the mesh. Any plain lit material
with the colour texture also works.

For outlines, the previews use the inverted hull with a width of 0.32 cm on the hull and 0.2 cm on the motor. A
post-process outline also works.

## Step 3: Kai's driving animations

1. Open `Animations` and **Import** the five files in `Content/Animations`.
2. Options: **Skeleton** = `SK_Kai_Skeleton`, **Import Mesh** (or Import Skeletal Meshes) off,
   **Import Animations** on. In the Interchange dialog, also turn **Import Only Animations** on. Leave the scale at 1.0.
3. Each clip is a held pose, two frames long. The blend space plays them on a loop (the **Loop** pin on its player
   node is on by default), so nothing needs changing on the clips.
4. Create a **Blend Space 1D** on `SK_Kai_Skeleton`, named `BS_Kai_Boat_Steer`. It is under **Animation**, or
   **Animation → Legacy** in recent 5.x versions. Set the horizontal axis name to
   `Steer`, Minimum −1, Maximum 1, Grid Divisions 4. Place the samples:

    | Steer | Animation |
    |---|---|
    | −1 | `AN_Kai_Boat_Steer_Left` |
    | −0.5 | `AN_Kai_Boat_Steer_Left_Half` |
    | 0 | `AN_Kai_Boat_Drive` |
    | 0.5 | `AN_Kai_Boat_Steer_Right_Half` |
    | 1 | `AN_Kai_Boat_Steer_Right` |

5. **Check it.** Preview the blend space on `SK_Kai_Tunic`. Kai should sit with his thighs level and his hands
   reaching forward and closed as if holding a wheel. Moving the Steer slider, he should lean and look left at −1 and
   right at 1.

The poses were fitted to this boat: his hands close on the wheel's rim, his feet rest on the floorboards, he sits on
the stern seat, and his clothes clear each other. Halfway between two samples his hands stay within about 3 mm of the
rim (`Reference/driving_check.json`).

## Step 4: Kai's Anim Blueprint

Kai's Anim Blueprint (the one on his `Mesh` component in `BP_Kai`) needs two variables and one blend:

1. Add a **Boolean** variable `IsDriving` and a **Float** variable `BoatSteer`.
2. In the **AnimGraph**, put a **Blend Poses by bool** just before the Output Pose:
    - **Active Value** = `IsDriving`
    - **True Pose** = `BS_Kai_Boat_Steer`, with its Steer input = `BoatSteer`
    - **False Pose** = your usual locomotion
    - **Blend Time** about 0.25 on both.

The boat sets these variables. If Kai has no Anim Blueprint yet, create one on `SK_Kai_Skeleton` (`ABP_Kai`) with just
this blend: an idle animation as the False Pose. Then set it as the Mesh component's **Anim Class** in `BP_Kai`.

## Step 5: Input

Create these with **Enhanced Input** in a folder `Input`:

| Asset | Type | Mappings |
|---|---|---|
| `IA_Boat_Throttle` | Input Action, Value Type **Axis1D (float)** | W; S with a **Negate** modifier; **Gamepad Right Trigger Axis**; **Gamepad Left Trigger Axis** with **Negate** (the plain Trigger keys are on/off only) |
| `IA_Boat_Steer` | Input Action, **Axis1D (float)** | D; A with **Negate**; Gamepad Left Thumbstick X-Axis with a **Dead Zone** modifier |
| `IA_Boat_Exit` | Input Action, **Digital (bool)** | E; Gamepad Face Button Left |
| `IMC_Boat` | Input Mapping Context | the three actions above |

Kai needs one action to get in, `IA_Interact` (Digital, E / Gamepad Face Button Left), in his own mapping context. If
he already has an interact action, use that.

## Step 6: The boat Blueprint

Create a Blueprint Class from **Pawn**, named `BP_KaiBoat`. In **Class Defaults**:

- Pawn: untick **Use Controller Rotation Pitch**, **Yaw** and **Roll**. Otherwise the controller sets the boat's
  rotation every frame and it can't turn.
- Pawn: **Auto Possess AI** = Disabled, so no AI controller takes the boat at the start.

### Components

Build this tree. "Socket" means the **Parent Socket** field in the component's Details, under Sockets.

```
Hull            Static Mesh   SM_Boat_Hull        (make it the root: drag it onto DefaultSceneRoot)
├─ Motor        Static Mesh   SM_Boat_Motor       socket Motor_Mount
│  └─ Propeller Static Mesh   SM_Boat_Propeller   socket Propeller
├─ Wheel        Static Mesh   SM_Boat_Wheel       socket Wheel
├─ BoardingZone Box Collision                     location (0, 0, 40), Box Extent (230, 160, 70)
└─ SpringArm    Spring Arm                        socket Camera_Boom
   └─ Camera    Camera
```

Leave every component's location and rotation at zero, apart from the BoardingZone's location and the SpringArm's
pitch.

**Hull** (Details panel):

| Setting | Value |
|---|---|
| Physics → Simulate Physics | on |
| Physics → Mass (kg) | tick the box, 150 (the boat, motor and driver) |
| Physics → Linear Damping | 0.05 |
| Physics → Angular Damping | 1.2 |
| Physics → Enable Gravity | on |
| Physics (advanced) → Center Of Mass Offset | X −5.3, Y 0, Z −9.5 (moves the centre of mass aft and down, to where the outboard and driver put it) |
| Collision → Collision Presets | PhysicsActor |

**Motor, Propeller and Wheel:** Collision Presets **NoCollision** (they must not add mass or push the hull),
Simulate Physics off.

**BoardingZone:** Collision Presets **OverlapAllDynamic**, Generate Overlap Events on.

**SpringArm:** Target Arm Length 420, Socket Offset Z 60, Rotation Y (pitch) −15, Do Collision Test on, Enable Camera
Lag on (speed 6), Enable Camera Rotation Lag on (speed 4), Inherit Pitch off, Inherit Roll off, Inherit Yaw on, Use
Pawn Control Rotation off. Turning off Inherit Pitch and Roll keeps the camera steady while the boat rocks.

**Camera:** Field Of View 80.

### Variables

Make each one **Instance Editable**, so you can tune boats in the level. Defaults are from the simulation.

| Variable | Type | Default | What it does |
|---|---|---|---|
| `WaterHeight` | Float | 0 | Z of the water surface. Put your water plane at this height. |
| `WaveHeight` | Float | 0 | Swell size in cm (try 3); 0 for flat water |
| `WaveLength` | Float | 600 | cm between swell crests |
| `WavePeriod` | Float | 2.4 | seconds between crests |
| `BuoyStiffness` | Float | 4200 | Upward push per cm a pontoon is under water (kg/s²) |
| `BuoyDamping` | Float | 270 | Slows the bob (kg/s) |
| `BuoyMaxDepth` | Float | 40 | A pontoon pushes no harder below this depth (cm) |
| `Thrust` | Float | 67000 | Propeller push at full throttle (kg·cm/s², Unreal's force unit) |
| `ReverseScale` | Float | 0.35 | Reverse thrust compared with forward |
| `DragLinear` | Float | 60 | Forward water drag, linear part (kg/s); lets the boat glide to a stop |
| `DragQuadratic` | Float | 0.03 | Forward water drag, quadratic part (kg/cm); with DragLinear, sets the top speed |
| `SideDrag` | Float | 1500 | Sideways water drag (kg/s): grip in turns, and steadies the boat |
| `KeelSpacing` | Float | 40 | The side drag acts this far ahead of and behind the centre of mass (cm) |
| `MotorMaxYaw` | Float | 25 | Outboard swing at full lock (degrees) |
| `WheelMaxRoll` | Float | 60 | Wheel turn at full lock (degrees) |
| `ThrottleRate` | Float | 2.5 | How fast the throttle follows the stick |
| `SteerRate` | Float | 4 | How fast the steering follows the stick |
| `PontoonSockets` | Name array | `Pontoon_Bow`, `Pontoon_FL`, `Pontoon_FR`, `Pontoon_ML`, `Pontoon_MR`, `Pontoon_SL`, `Pontoon_SR` | Buoyancy points |
| `ThrottleInput`, `SteerInput` | Float | 0 | Raw input |
| `Throttle`, `Steer` | Float | 0 | Smoothed input |
| `WetFraction` | Float | 0 | Share of pontoons under water (0 to 1) |
| `Driver` | Character (object reference) | none | Kai, while he drives |

### Functions

**`GetWaterHeight`** (input `Location` Vector, output `Height` Float, mark it Pure):

    Height = WaterHeight + WaveHeight × Sin(360 × (Location.X / WaveLength − GetGameTimeInSeconds / WavePeriod))

Use **Sin (Degrees)**. If your water plane has animated waves, match WaveHeight, WaveLength and WavePeriod to them.

**`ApplyBuoyancy`**:

1. Set a local integer `Wet` = 0.
2. **For Each Loop** over `PontoonSockets`:
    - `P` = Hull → **Get Socket Location** (socket = array element)
    - `Depth` = GetWaterHeight(P) − P.Z
    - **Branch** on `Depth > 0`. If true:
        - `Vz` = Hull → **Get Physics Linear Velocity at Point** (Point = P) → Z
        - `Push` = **Max**(0, BuoyStiffness × **Min**(Depth, BuoyMaxDepth) − BuoyDamping × Vz)
        - Hull → **Add Force at Location** (Force = (0, 0, Push), Location = P)
        - `Wet` = Wet + 1
3. `WetFraction` = **To Float**(Wet) ÷ **To Float**(length of `PontoonSockets`). Convert both first: integer
   division in Blueprints rounds down to 0.

At rest each pontoon is 5 cm under water. 7 × 4200 × 5 = 147,000, which carries 150 kg against Unreal's gravity of
980 cm/s².

**`ApplyThrust`**:

1. `P` = Propeller → **Get World Location**.
2. **Branch** on `P.Z < GetWaterHeight(P)`; out of the water the propeller pushes nothing. If true:
    - `Power` = Throttle × (Throttle ≥ 0 ? 1 : ReverseScale). Use a **Select Float** on `Throttle >= 0`.
    - Hull → **Add Force at Location** (Force = Motor → **Get Forward Vector** × Power × Thrust, Location = P)

Steering comes from this: when the motor is turned, the push at the stern swings the boat round.

**`ApplyWaterDrag`**:

1. `V` = Hull → **Get Physics Linear Velocity**, `Fwd` = Hull → **Get Forward Vector**,
   `Right` = Hull → **Get Right Vector**, `CoM` = Hull → **Get Center Of Mass**.
2. Forward drag: `S` = **Dot**(V, Fwd).
   Hull → **Add Force** (Force = Fwd × −(DragLinear × S + DragQuadratic × S × **Abs**(S)) × WetFraction).
3. Keel drag, at two points, `K` = CoM + Fwd × KeelSpacing and `K` = CoM − Fwd × KeelSpacing (do both):
    - `Vk` = Hull → **Get Physics Linear Velocity at Point** (K)
    - Hull → **Add Force at Location** (Force = Right × −0.5 × SideDrag × **Dot**(Vk, Right) × WetFraction,
      Location = K)

**`UpdateVisuals`** (input `DeltaTime`):

- Motor → **Set Relative Rotation** (Roll 0, Pitch 0, Yaw = −MotorMaxYaw × Steer).
- Wheel → **Set Relative Rotation** (Roll = −WheelMaxRoll × Steer, Pitch 0, Yaw 0).
- Propeller → **Add Local Rotation** (Roll = (300 + 1500 × **Abs**(Throttle)) × DeltaTime).
- If `Driver` is valid: Driver → Get Mesh → **Get Anim Instance** → **Cast to** Kai's Anim Blueprint → set
  `BoatSteer` = Steer.

### Event Graph

**Event Tick:**

1. `Throttle` = **FInterp To** (Current Throttle, Target ThrottleInput, Delta Time, Interp Speed ThrottleRate).
2. `Steer` = **FInterp To** (Steer, SteerInput, Delta Time, SteerRate).
3. ApplyBuoyancy → ApplyThrust → ApplyWaterDrag → UpdateVisuals(Delta Time).

Keep the actor's Tick Group at its default, **Pre Physics**. Forces added on Tick then go into that frame's physics
step.

**Input events** (Right-click → Enhanced Action Events):

- **IA_Boat_Throttle**: Triggered → set ThrottleInput = Action Value; Completed → set ThrottleInput = 0.
- **IA_Boat_Steer**: Triggered → set SteerInput = Action Value; Completed → set SteerInput = 0.
- **IA_Boat_Exit**: Started → ExitBoat.

**Event Possessed** (New Controller): cast to **Player Controller** → **Get Enhanced Input Local Player Subsystem**
→ **Add Mapping Context** (IMC_Boat, Priority 1).

### Getting in: `EnterBoat` (input `NewDriver`, Character)

1. **Branch**: only continue if `Driver` is not valid (the boat is free).
2. Set `Driver` = NewDriver. Store NewDriver → **Get Controller** in a local `PC`.
3. NewDriver → **Get Character Movement** → **Stop Movement Immediately**, then **Disable Movement**.
4. NewDriver → **Set Actor Enable Collision** (false). The physics hull must not push against Kai's capsule.
5. NewDriver → **Attach Actor To Component** with these settings:
    - Parent = Hull, Socket Name = `Seat_Driver`
    - Location Rule and Rotation Rule = **Snap to Target**, Scale Rule = **Keep World**
    - Weld Simulated Bodies off
6. NewDriver → Get Mesh → Get Anim Instance → Cast to Kai's Anim Blueprint → set `IsDriving` = true.
7. `PC` → **Possess** (Self).

In **BP_Kai**, add **IA_Interact** (Started):
- Call **Get Overlapping Actors** (Class Filter `BP_KaiBoat`).
- If the array has an element: **Get** (index 0) → **Cast To BP_KaiBoat** → **EnterBoat** with NewDriver = Self.
  The array holds plain Actors even with the filter, so the cast is needed.

The BoardingZone reaches about a metre round the boat, so Kai can board from a jetty or the shore.

### Getting out: `ExitBoat`

1. **Branch**: only continue if `Driver` is valid.
2. Find a place to stand. For each of `Exit_Port` and `Exit_Starboard`:
    - `Start` = Hull → Get Socket Location.
    - **Line Trace By Channel** from Start to Start − (0, 0, 300), channel Visibility, Actors to Ignore = Self and
      Driver.
    - Use the first hit whose Impact Point Z is more than 5 above GetWaterHeight(Impact Point). That is ground, not
      water. `Spot` = Impact Point + (0, 0, Driver → Get Capsule Component → **Get Scaled Capsule Half Height** + 2).
3. If neither side hits ground, stay in the boat: **Return**. Optionally play a "can't get off here" sound.
4. Driver → **Detach From Actor** (Keep World for location, rotation and scale).
5. Driver → **Teleport** to Spot. Dest Rotation = **Make Rotator** (Roll 0, Pitch 0, Yaw = Hull → Get World
   Rotation → Yaw). Rotator pins run Roll, Pitch, Yaw.
6. Driver → **Set Actor Enable Collision** (true). Driver → Get Character Movement → **Set Movement Mode** (Walking).
7. Driver's Anim Blueprint → set `IsDriving` = false.
8. **Get Controller** (of Self) → **Cast To PlayerController**, store it in a local `PC`:
    - `PC` → Get Enhanced Input Local Player Subsystem → **Remove Mapping Context** (IMC_Boat).
    - Then `PC` → **Possess** (Driver).
9. Set ThrottleInput, SteerInput, Throttle and Steer to 0, and `Driver` to none.

### Check it

Put a large plane at Z = 0 with a water-blue material and set its **Collision Presets** to **NoCollision**: buoyancy
is all that holds the boat up, and a solid plane would hold it instead. Place `BP_KaiBoat` on it, then press Play.

- **Floating:** the boat should drop, bob once or twice and settle level within about a second, with the navy stripe
  just above the water. If the bow sits low, make the Center Of Mass Offset X more negative (−30). If the stern sits
  low, make it less negative.
- **Boarding:** walk Kai up to the boat and press E. He should snap onto the stern seat with his hands on the wheel,
  and the camera should move behind the boat.
- **Throttle:** hold W. The propeller should spin and the boat should speed up to about 7.5 m/s in four seconds.
- **Steering:** hold D. The top of the wheel should turn right, and the back of the outboard's cowl should swing to
  the right. The boat should turn right, and Kai should lean and look right. If the wheel turns the wrong way, use
  +WheelMaxRoll in UpdateVisuals. If the boat turns left on D, use +MotorMaxYaw. Both depend on how your engine version
  shows the imported axes; the boat physics follows the motor.
- **Coasting:** let go. The boat should coast to walking pace in about six seconds.
- **Getting out:** press E next to a jetty or shore. Kai should step off and walk again.

## Step 7: Effects and sound (optional)

| Effect | How |
|---|---|
| Bow spray | Niagara systems on `Bow_Spray_L` and `Bow_Spray_R`. Scale their spawn rate by forward speed (0 below 150 cm/s, full at 700). |
| Wake | A Niagara ribbon or decal trail on `Wake`, which points backwards |
| Exhaust puffs | A small smoke burst on the motor's `Exhaust` socket, faster with throttle |
| Bow light | A Point Light on `Bow_Light`: radius 150, intensity 2, warm white. It is lovely at dusk. |
| Engine | An Audio component on the Motor, looping. Pitch Multiplier = 0.8 + 0.6 × Abs(Throttle), Volume = 0.5 + 0.5 × Abs(Throttle). |
| Splash on landing | When the hull's vertical velocity goes from below −200 to above 0, spawn a splash at the hull's location. |

## Using Unreal's Water plugin instead (optional)

The Blueprint above works on any flat water at `WaterHeight`. With the Water plugin, either:

- Keep this Blueprint and read the height from the water body. Recent engine versions have a Blueprint node on the
  Water Body component that returns the surface location under a point (look for **Get Water Surface Info at
  Location**). Use its Z inside `GetWaterHeight`.
- Or replace `ApplyBuoyancy` with the plugin's **Buoyancy** component. Add it to `BP_KaiBoat` and add one pontoon per
  `Pontoon_*` socket, radius about 15. Then tune its buoyancy coefficient until the boat floats at the stripe. Keep
  `ApplyThrust` and `ApplyWaterDrag`, but set the component's own drag low so the two don't double up.

## Tuning

| To make it... | Change |
|---|---|
| Faster | Raise Thrust (top speed grows with roughly the square root of thrust) |
| Quicker to stop | Raise DragLinear |
| Turn tighter | Raise MotorMaxYaw (up to 35), or lower SideDrag a little (it will slide more) |
| Slide less in turns | Raise SideDrag |
| Bob more (bouncier, toy-like) | Lower BuoyDamping (150) |
| Sit higher or lower | Change BuoyStiffness: higher rides higher. At 4200 it floats on the design waterline. |
| Feel heavier | Raise Mass and BuoyStiffness by the same factor, and Thrust with them |

**Simulated with the default values** (`Reference/physics_tuning.json`, same at 30, 60 and 120 fps):

| Test | Result |
|---|---|
| Floats at | 5.0 cm up the keel, level (0.0° pitch and roll) |
| Settles after a 10 cm drop | 0.7 s |
| Top speed | 7.45 m/s (27 km/h), 90% of it in 3.8 s |
| Full lock at full throttle | 59°/s, a 5.7 m turning circle at 5.9 m/s, 1° of heel |
| Coasting from top speed to 0.5 m/s | 5.9 s |
| Reverse | 3.0 m/s |
| Righting from 20° of heel | upright within 2 s |
| 4 cm swell | the boat rides it, bobbing 6.8 cm and pitching 4.5° |

## Troubleshooting

| Problem | Fix |
|---|---|
| The boat sinks | `WaterHeight` doesn't match your water, or the Mass override is off (Unreal then uses a much heavier mass from the collision). |
| The boat sits on the water like a block and never bobs | The water mesh has collision. Set it to NoCollision (Step 6, Check it). |
| The boat won't turn, or snaps to face the camera | Untick Use Controller Rotation Pitch, Yaw and Roll in the Pawn's Class Defaults (Step 6). |
| Drag disappears when the boat rocks | WetFraction uses integer division. Convert to float first (ApplyBuoyancy, step 3). |
| The boat shoots into the air | BuoyStiffness or Thrust has an extra zero, or ApplyBuoyancy runs more than once per tick. |
| It bounces forever | Raise BuoyDamping. Check that Linear Damping is 0.05, not 0. |
| It spins on the spot when turning | SideDrag is 0, or the keel points are not set (ApplyWaterDrag step 3). |
| It slides sideways like ice | Raise SideDrag. |
| Water shows inside the boat | WaterHeight is too high for the boat's float height, or the boat is overloaded. The floorboards are 2 cm above the design waterline. |
| Kai stands, floats or faces sideways in the boat | Kai's Anim Blueprint is not in the driving state (Step 4), or BP_Kai's Mesh yaw is not set (Kai's guide, Step 5). |
| Kai jitters or pushes the boat | His collision is still on. Set Actor Enable Collision (false) when he gets in. |
| The motor, wheel or propeller wobbles the boat | Their collision must be NoCollision. |
| Kai can't get out | There is no ground under `Exit_Port` or `Exit_Starboard`. Pull up next to a jetty or shore. |
| One blob of collision round the hull | Re-import with Auto Generate Collision off (Step 1). |

## Editing the boat

Everything is generated by scripts in the repository's `tools` folder:

| Script | What it does |
|---|---|
| `boat_geometry.py` | Hull shape, seats, console, wheel, motor, propeller, fittings, sockets and pontoons. Sizes are at the top. |
| `boat_textures.py` | Colours and painted details |
| `build_boat.py` | Meshes, UVs, textures, collision, sockets and FBX export: `python3 tools/build_boat.py --out boat` |
| `kai_boat_pose.py` | Seats Kai in the boat, fits his grip to the wheel, checks clearances and exports the driving poses |
| `boat_sim.py` | The physics simulation behind the tuning values |
| `render_boat.py`, `verify_boat.py` | Preview renders, and the checks on the exported files |
| `package_boat_unreal.py` | Builds this zip |
