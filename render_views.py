"""Render orthographic engineering views of the Volare baseline scene.

    blender -b cad/out/volare_baseline.blend -P cad/blender/render_views.py
    blender -b cad/out/volare_baseline.blend -P cad/blender/render_views.py -- --res 1600

Workbench engine, flat studio lighting, cavity shading on - the point is to read
the geometry, not to look pretty. Renders side / front / top / iso into
cad/out/views/, framing on the physical collections and ignoring the oversized
REFERENCE envelopes so they cannot blow out the framing.
"""
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "cad" / "out" / "views"
import os
OUT = Path(os.environ.get("VOLARE_VIEWS", OUT))

# Collections that define the framing box. REFERENCE holds the 500 mm keep-out
# volume, which is far larger than the boat and would wreck every view.
FRAME_ON = ("SUPPLIED", "COCKPIT", "FRAME", "PROPOSED", "FRAME_V2")

VIEWS = {
    #  name        direction the camera looks along      up axis
    "side":  ((0.0, 1.0, 0.0),  (0.0, 0.0, 1.0)),
    "front": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "top":   ((0.0, 0.0, -1.0), (1.0, 0.0, 0.0)),
    "iso":   ((-0.62, 0.62, -0.48), (0.0, 0.0, 1.0)),
}


def scene_bounds():
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for cname in FRAME_ON:
        coll = bpy.data.collections.get(cname)
        if not coll:
            continue
        for ob in coll.objects:
            if ob.type != "MESH":
                continue
            for corner in ob.bound_box:
                w = ob.matrix_world @ Vector(corner)
                lo = Vector((min(lo[i], w[i]) for i in range(3)))
                hi = Vector((max(hi[i], w[i]) for i in range(3)))
    return lo, hi


def setup_world():
    w = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    if w.node_tree:
        bg = w.node_tree.nodes.get("Background")
        if bg:
            bg.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
            bg.inputs[1].default_value = 1.0


def setup_render(res):
    s = bpy.context.scene
    s.render.engine = "BLENDER_WORKBENCH"
    s.render.resolution_x = res
    s.render.resolution_y = int(res * 0.62)
    s.render.resolution_percentage = 100
    s.render.film_transparent = False
    sh = s.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"
    sh.show_cavity = True
    sh.cavity_type = "BOTH"
    sh.show_object_outline = True
    sh.object_outline_color = (0.10, 0.10, 0.12)
    try:
        sh.show_shadows = True
    except AttributeError:
        pass


def make_camera():
    cam_data = bpy.data.cameras.new("ortho_cam")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("ortho_cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam


def aim(cam, direction, up, centre, radius):
    d = Vector(direction).normalized()
    cam.location = centre - d * (radius * 4.0)
    # build a rotation whose -Z looks along d
    z = -d
    u = Vector(up)
    if abs(z.dot(u.normalized())) > 0.999:
        u = Vector((0.0, 1.0, 0.0))
    x = u.cross(z).normalized()
    y = z.cross(x).normalized()
    cam.matrix_world = (
        __import__("mathutils").Matrix((
            (x.x, y.x, z.x, cam.location.x),
            (x.y, y.y, z.y, cam.location.y),
            (x.z, y.z, z.z, cam.location.z),
            (0.0, 0.0, 0.0, 1.0),
        ))
    )
    cam.data.ortho_scale = radius * 2.15
    cam.data.clip_start = 0.01
    cam.data.clip_end = radius * 20.0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    res = int(argv[argv.index("--res") + 1]) if "--res" in argv else 1600
    OUT.mkdir(parents=True, exist_ok=True)

    setup_world()
    setup_render(res)

    lo, hi = scene_bounds()
    centre = (lo + hi) / 2.0
    radius = max((hi - lo)) / 2.0
    print(f"[render] framing on {[c for c in FRAME_ON]}")
    print(f"[render] bbox {tuple(round(v * 1000, 1) for v in (hi - lo))} mm, "
          f"centre {tuple(round(v * 1000, 1) for v in centre)} mm")

    # REFERENCE holds non-physical envelopes (pilot box, 500 mm keep-out) and the
    # round-pole overlay. display_type='WIRE' is viewport-only - Workbench renders
    # them solid - so hide them from the render unless --refs is passed.
    show_refs = "--refs" in argv
    ref = bpy.data.collections.get("REFERENCE")
    if ref:
        for ob in ref.objects:
            ob.hide_render = not show_refs
    print(f"[render] reference envelopes: {'shown' if show_refs else 'hidden'}"
          f" (pass -- --refs to include them)")

    cam = make_camera()
    for name, (direction, up) in VIEWS.items():
        aim(cam, direction, up, centre, radius)
        path = OUT / f"volare_{name}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print(f"[render] wrote {path}")


if __name__ == "__main__":
    main()
