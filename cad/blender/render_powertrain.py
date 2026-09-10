"""
render_powertrain.py -- orthographic views of the powertrain.

    blender --background --python blender/render_powertrain.py

Opens out/volare_powertrain.blend and renders side, plan, front and iso views
to out/views_powertrain/.

Orthographic on purpose. A perspective render of an engineering layout invites
people to judge clearances by eye, and eye is wrong about perspective. These
are for reading positions off, so parallel projection with a stated scale is
the only honest choice.
"""

import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "out")
VIEWS = os.path.join(OUT, "views_powertrain")

RES = (1600, 1000)


def scene_bounds():
    """Extent of everything actually drawn.

    Curves are converted to their evaluated mesh rather than trusted to
    report a bounding box. A beveled POLY curve's bound_box comes back
    wildly oversized -- the powertrain cables reported Z from -255 to
    1945 mm for runs that span 200 mm -- and framing the camera on that
    would leave the model a speck in the middle of the render.
    """
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))

    deps = bpy.context.evaluated_depsgraph_get()

    for obj in bpy.context.scene.objects:
        if obj.type not in {"MESH", "CURVE"}:
            continue

        ev = obj.evaluated_get(deps)

        try:
            me = ev.to_mesh()
        except RuntimeError:
            me = None

        if me is not None and len(me.vertices):
            pts = [ev.matrix_world @ v.co for v in me.vertices]
            ev.to_mesh_clear()
        else:
            if me is not None:
                ev.to_mesh_clear()
            pts = [ev.matrix_world @ Vector(c) for c in ev.bound_box]

        for w in pts:
            for i in range(3):
                lo[i] = min(lo[i], w[i])
                hi[i] = max(hi[i], w[i])

    return lo, hi


def setup_world():
    scn = bpy.context.scene
    scn.render.engine = "BLENDER_WORKBENCH"
    scn.render.resolution_x, scn.render.resolution_y = RES
    scn.render.film_transparent = False

    shading = scn.display.shading
    shading.light = "STUDIO"
    shading.color_type = "MATERIAL"
    shading.show_cavity = True
    shading.show_object_outline = True

    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (
        0.05, 0.06, 0.07, 1.0)
    scn.world = world


def add_camera(name, direction, up, lo, hi, margin=1.12):
    """One orthographic camera looking along `direction`."""
    cam_data = bpy.data.cameras.new(name)
    cam_data.type = "ORTHO"

    centre = (lo + hi) / 2.0
    span = hi - lo

    d = Vector(direction).normalized()
    u = Vector(up).normalized()
    right = d.cross(u).normalized()
    u = right.cross(d).normalized()

    # The orthographic scale must cover the projected extent, which is the
    # box measured along the camera's own right and up axes -- not the
    # world axes. Getting that wrong crops the model, and a cropped
    # engineering view is a misleading one.
    w = sum(abs(right[i]) * span[i] for i in range(3))
    h = sum(abs(u[i]) * span[i] for i in range(3))

    cam_data.ortho_scale = max(w, h) * margin

    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.scene.collection.objects.link(cam)

    dist = max(span) * 3.0
    cam.location = centre - d * dist

    rot = d.to_track_quat("-Z", "Y").to_euler()
    cam.rotation_euler = rot

    # Re-aim so the requested `up` really is up in frame.
    m = cam.matrix_world.to_3x3()
    if (m @ Vector((0, 1, 0))).dot(u) < 0.99:
        q = d.to_track_quat("-Z", "Y")
        cam.rotation_euler = q.to_euler()

    return cam


def render(cam, path):
    scn = bpy.context.scene
    scn.camera = cam
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def main():
    blend = os.path.join(OUT, "volare_powertrain.blend")

    if not os.path.isfile(blend):
        print(f"ERROR: {blend} not found.")
        print("Run:  blender --background --python blender/build_powertrain.py")
        sys.exit(1)

    bpy.ops.wm.open_mainfile(filepath=blend)

    setup_world()
    os.makedirs(VIEWS, exist_ok=True)

    lo, hi = scene_bounds()

    print()
    print("=" * 70)
    print(" POWERTRAIN VIEWS")
    print("=" * 70)
    print(f" extent  X {lo.x*1000:8.0f} .. {hi.x*1000:8.0f} mm")
    print(f"         Y {lo.y*1000:8.0f} .. {hi.y*1000:8.0f} mm")
    print(f"         Z {lo.z*1000:8.0f} .. {hi.z*1000:8.0f} mm")

    # X forward, Y port, Z up. "Starboard side" means looking from -Y.
    views = [
        ("side_starboard", (0, 1, 0), (0, 0, 1)),
        ("plan_from_above", (0, 0, -1), (1, 0, 0)),
        ("front_from_bow", (-1, 0, 0), (0, 0, 1)),
        ("iso", (-0.6, 0.62, -0.5), (0, 0, 1)),
    ]

    for name, d, up in views:
        cam = add_camera(f"cam_{name}", d, up, lo, hi)
        p = render(cam, os.path.join(VIEWS, name + ".png"))
        print(f" rendered {os.path.basename(p)}  "
              f"ortho scale {cam.data.ortho_scale*1000:.0f} mm")

    # --- internals -------------------------------------------------------
    #
    # The container and the PDU are the two things worth seeing inside, and
    # a solid box hides exactly the parts that were placed with the most
    # care. Hide the enclosures and render the same two views again.
    hidden = []
    for obj in bpy.context.scene.objects:
        if obj.get("is_enclosure"):
            obj.hide_render = True
            hidden.append(obj.name)

    if hidden:
        for name, d, up in views[:2]:
            cam = bpy.data.objects[f"cam_{name}"]
            p = render(cam, os.path.join(VIEWS, name + "_internals.png"))
            print(f" rendered {os.path.basename(p)}  "
                  f"({len(hidden)} enclosure(s) hidden)")


    print(f"\n {VIEWS}")
    print("=" * 70)


if __name__ == "__main__":
    main()
