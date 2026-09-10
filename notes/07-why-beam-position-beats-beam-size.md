---
tags: [volare, structures, frame, explainer]
---

# 07 — Why Beam Position Beats Beam Size (plain version)

Parent: [[00 - Master Brief]] · Numbers in [[02 - Support Frame Design]]

## 1. The sawhorse analogy

Put a plank across two sawhorses and stand in the middle. It sags. Now slide the sawhorses closer together and stand on it again — it barely moves. **You didn't change the plank. You changed where it's held.**

That's the whole idea. But the reason it matters so much is that the relationship isn't gentle:

$$\delta \propto \frac{W L^3}{EI}$$

Sag goes as **length cubed**. Double the span, and it sags **eight times** as much. Halve the span, and it sags to **one eighth**.

## 2. What's happening on your boat

Your two crossbeams (the ones running side-to-side between the hulls) sit **3.0 m apart** — one at X = +1942, one at X = −1056. The two rails (running front-to-back, carrying the cockpit) bridge that 3.0 m gap.

But your cockpit is only **2.54 m long**, and it isn't centred on that gap. The aft crossbeam sits **1.1 m behind the cockpit's tail.**

So:

- You're carrying 1.1 m of aluminium tube that holds nothing up
- Worse: because the rails have to bridge 3.0 m instead of the ~1.8 m they actually need to, they have to be much beefier to avoid sagging

> **The relocation option is dead** — crossbeam stations on the hulls are fixed, so the 3.0 m span cannot change. The span principle in §1–2 is still the right mental model, and the same ~10 kg is still recoverable by other means: see [[08 - Frame Solution at Fixed Span]].

## 3. The numbers, plainly

Take the sag target as 10 mm — about the thickness of a pencil, over a 3 m span. Here's how stiff the rail needs to be to hit that, at different spans:

| Rail span | Stiffness needed (I) | What tube that means |
|---|---|---|
| 3.0 m (as drawn) | 135 cm⁴ | 120 × 60 × 4 mm — **11.1 kg each** |
| 2.4 m | 86 cm⁴ | 100 × 50 × 4 mm — 9.1 kg each |
| **1.8 m** | **47 cm⁴** | **80 × 40 × 3 mm — 3.3 kg each** |

Same load. Same sag. **A third of the metal**, purely from moving where it's held.

Why the drop is so steep: shortening 3.0 m to 1.8 m is a factor of 0.6 in length, and 0.6³ = **0.22**. The rail only needs 22% of its original stiffness. And because stiffness itself climbs fast with tube size, a small drop in required stiffness lets you step down two whole tube sizes.

**That's the ~10 kg.** Not from a cleverer material or a lighter alloy — from putting the supports where the weight actually sits.

## 4. The correction: the outboard changes this

That advice was written before I saw the Competr datasheet. **It needs amending.**

The outboard is 25 kg plus a 10 kg trim assembly, mounted at the stern, producing up to ~2800 N of thrust at launch and 100 N·m of reaction torque, with ±40° of steering swing. At 40° of helm the sideways force is roughly **1800 N**, and the thrust acting 705 mm below the mount produces about **1974 N·m** of overturning moment.

So the aft crossbeam **cannot** move inboard — the drive has to hang off the stern.

### Revised architecture: three beams, two jobs

Stop trying to make two beams do everything. Split the functions:

**Beam 1 + 2 — cockpit frame.** Positioned to bracket the pod's actual load points, roughly 1.8 m apart, both **80 × 40 × 3 mm** (or 90 × 45 × 3 for margin). These carry the pilot, shell and pack. Nothing else.

**Beam 3 — drive beam.** At the stern, carrying only the outboard. Sized for torsion, not bending: **120 × 60 × 5 mm closed section**, ~4.6 kg/m. Bending stress works out at ~17 MPa against 260 MPa yield, so it is torsion and joint stiffness that govern, not stress. It must be a **closed** box — an open channel or angle will twist under the steering moment and the helm will feel vague and delayed.

Why this is better than the original two-beam layout, even though it adds a beam:

1. Drive loads never pass through the cockpit frame. Right now, every bit of thrust and steering torque travels up the rails and through the pod's mounting points.
2. Each beam is sized for one job instead of the worst case of several.
3. The stern beam can be short and stiff; the cockpit beams can be light.
4. You can tune the cockpit's fore-aft position independently of the drive.

Net mass comes out about the same as the two-beam relocation (~26 kg vs 23 kg) — but you get a drive mount that actually works, which the original layout never had.

## 5. The one-line version

**Sag grows with the cube of the span, so where you put the supports matters far more than how thick you make what spans between them.** Your rails were spanning 3.0 m to hold up a 2.5 m cockpit, with 1.1 m of that span doing nothing. Fix the geometry first; only then pick the tube.
