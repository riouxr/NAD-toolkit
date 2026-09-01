import bpy
import re
import bmesh
import math
from collections import defaultdict

OVERLAP_THRESHOLD = 1e-4
MAX_IDX = 8

_sanity_results = []

SUFFIXES = ['SD', 'GL', 'EM', 'DC']
SUFFIX_DESCRIPTIONS = {
    'SD': "Static/Diffuse",
    'GL': "Glass",
    'EM': "Emissive",
    'DC': "Decal",
}


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------

def _join_name_parts(*parts):
    return "_".join(p for p in parts if p)


def _current_suffix(scene):
    for key in SUFFIXES:
        if getattr(scene, f"nad_suffix_{key.lower()}"):
            return key
    return ""


def _make_suffix_update(key):
    prop_name = f"nad_suffix_{key.lower()}"

    def _update(self, context):
        if getattr(self, prop_name):
            for other in SUFFIXES:
                if other != key:
                    setattr(self, f"nad_suffix_{other.lower()}", False)

    return _update


class NAD_OT_Rename(bpy.types.Operator):
    bl_idname = "nad.rename_objects"
    bl_label = "Name"
    bl_description = (
        "Rename the selected objects to SM_Name1_Name2_Name3_Suffix_## "
        "(empty name fields and no suffix are skipped), numbering each "
        "selected object after the highest existing match"
    )

    def execute(self, context):
        scene = context.scene
        base = _join_name_parts(scene.nad_name1, scene.nad_name2, scene.nad_name3)
        suffix = _current_suffix(scene)
        objs = context.selected_objects
        selected_set = set(objs)

        full_base = _join_name_parts(base, suffix)
        print(f"[NAD] name parts: '{scene.nad_name1}' '{scene.nad_name2}' '{scene.nad_name3}'  base: '{base}'  suffix: '{suffix}'")
        print(f"[NAD] selected objects: {[o.name for o in objs]}")

        pattern = re.compile(rf"^SM_{re.escape(full_base)}_(\d+)$")
        print(f"[NAD] pattern: {pattern.pattern}")

        max_num = 0
        for obj in context.scene.objects:
            if obj in selected_set:
                continue
            m = pattern.match(obj.name)
            if m:
                print(f"[NAD] matched existing: '{obj.name}' -> num {int(m.group(1))}")
                max_num = max(max_num, int(m.group(1)))

        print(f"[NAD] max existing num: {max_num}, starting from: {max_num + 1}")

        for i, obj in enumerate(objs, max_num + 1):
            old_name = obj.name
            obj.name = f"SM_{full_base}_{i:02d}"
            print(f"[NAD] renamed '{old_name}' -> '{obj.name}'")

        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Sanity Check helpers
# ---------------------------------------------------------------------------

def _fmt(indices):
    sample = indices[:MAX_IDX]
    suffix = "…" if len(indices) > MAX_IDX else ""
    return ", ".join(str(i) for i in sample) + suffix


def _check_name(obj):
    # Accept SM_Xxx_## or SM_Xxx[_Yyy][_Zzz]_SD/GL/EM/DC_##
    if not re.match(r'^SM_[^_]+(?:_[^_]+){0,2}(?:_(?:SD|GL|EM|DC))?_\d{2}$', obj.name):
        return "Bad name format (expected SM_Xxx[_Yyy][_Zzz]_## or SM_Xxx[_Yyy][_Zzz]_SD/GL/EM/DC_##)"
    return None


def _check_ngons(bm):
    faces = [f.index for f in bm.faces if len(f.verts) > 4]
    if faces:
        return f"nGons: {len(faces)} face(s) [{_fmt(faces)}]"
    return None


def _check_missing_normals(bm):
    faces = [f.index for f in bm.faces if f.calc_area() < 1e-8]
    if faces:
        return f"Missing normals (zero-area faces): {len(faces)} [{_fmt(faces)}]"
    return None


def _check_flipped_normals(obj, bm):
    issues = []
    s = obj.scale
    if s.x * s.y * s.z < 0:
        issues.append("Normals flipped (negative scale)")
    if bm.faces:
        center = sum((f.calc_center_median() for f in bm.faces),
                     bm.faces[0].calc_center_median() * 0) / len(bm.faces)
        inward = [f.index for f in bm.faces
                  if (f.calc_center_median() - center).dot(f.normal) < -1e-4]
        if len(inward) > len(bm.faces) * 0.5:
            issues.append(f"Normals flipped (inside-out): {len(inward)} face(s) [{_fmt(inward)}]")
    return issues or None


def _check_udim_crossing(obj):
    mesh = obj.data
    if not mesh.uv_layers or not mesh.uv_layers.active:
        return None
    uv_layer = mesh.uv_layers.active
    crossing = []
    for poly in mesh.polygons:
        uvs = [uv_layer.data[li].uv for li in poly.loop_indices]
        if len({math.floor(uv.x) for uv in uvs}) > 1 or len({math.floor(uv.y) for uv in uvs}) > 1:
            crossing.append(poly.index)
    if crossing:
        return f"UVs crossing UDIMs: {len(crossing)} face(s) [{_fmt(crossing)}]"
    return None


def _check_concave(bm):
    concave = []
    for face in bm.faces:
        if len(face.verts) < 4:
            continue
        verts = [v.co.copy() for v in face.verts]
        n = face.normal
        for i in range(len(verts)):
            a, b, c = verts[i], verts[(i+1) % len(verts)], verts[(i+2) % len(verts)]
            if (b - a).cross(c - b).dot(n) < -1e-6:
                concave.append(face.index)
                break
    if concave:
        return f"Concave polys: {len(concave)} face(s) [{_fmt(concave)}]"
    return None


def _check_overlapping_verts(bm):
    buckets = defaultdict(list)
    t = OVERLAP_THRESHOLD
    for v in bm.verts:
        key = (round(v.co.x / t), round(v.co.y / t), round(v.co.z / t))
        buckets[key].append(v.index)
    hot = [idxs for idxs in buckets.values() if len(idxs) > 1]
    if hot:
        return f"Overlapping vertices: {len(hot)} location(s) [e.g. vert {_fmt([i[0] for i in hot])}]"
    return None


def _check_overlapping_faces(bm):
    seen = {}
    dupes = []
    for face in bm.faces:
        key = frozenset(v.index for v in face.verts)
        if key in seen:
            dupes.append(face.index)
        else:
            seen[key] = face.index
    if dupes:
        return f"Overlapping faces: {len(dupes)} face(s) [{_fmt(dupes)}]"
    return None


# ---------------------------------------------------------------------------
# Sanity Check popup
# ---------------------------------------------------------------------------

class NAD_OT_SanityCheckPopup(bpy.types.Operator):
    bl_idname = "nad.sanity_check_popup"
    bl_label = "Sanity Check Results"
    bl_description = "Show the issues found by the last Sanity Check run"

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=660)

    def draw(self, context):
        layout = self.layout
        if not _sanity_results:
            layout.label(text="No issues found!", icon='CHECKMARK')
            return
        for line in _sanity_results:
            if line.startswith("["):
                layout.separator(factor=0.5)
                row = layout.row()
                row.alert = True
                row.label(text=line, icon='OBJECT_DATA')
            else:
                layout.label(text=line, icon='ERROR')


# ---------------------------------------------------------------------------
# Sanity Check operator
# ---------------------------------------------------------------------------

class NAD_OT_SanityCheck(bpy.types.Operator):
    bl_idname = "nad.sanity_check"
    bl_label = "Sanity Check"
    bl_options = {'REGISTER'}
    bl_description = (
        "Scan every mesh object in the scene for naming-convention "
        "violations, nGons, zero-area faces, concave polygons, flipped "
        "normals, overlapping verts/faces, and UVs crossing UDIM borders"
    )

    def execute(self, context):
        global _sanity_results
        _sanity_results = []

        mesh_objects = [o for o in context.scene.objects if o.type == 'MESH']
        print(f"[NAD Sanity] Checking {len(mesh_objects)} mesh object(s)…")

        for obj in mesh_objects:
            obj_issues = []

            name_issue = _check_name(obj)
            if name_issue:
                obj_issues.append(f"  • {name_issue}")

            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bm.faces.ensure_lookup_table()
            bm.verts.ensure_lookup_table()

            for fn in (_check_ngons, _check_missing_normals, _check_concave,
                       _check_overlapping_verts, _check_overlapping_faces):
                result = fn(bm)
                if result:
                    obj_issues.append(f"  • {result}")

            flip_issues = _check_flipped_normals(obj, bm)
            if flip_issues:
                for fi in flip_issues:
                    obj_issues.append(f"  • {fi}")

            bm.free()

            udim_issue = _check_udim_crossing(obj)
            if udim_issue:
                obj_issues.append(f"  • {udim_issue}")

            if obj_issues:
                print(f"[NAD Sanity] {obj.name}: {len(obj_issues)} issue(s)")
                _sanity_results.append(f"[{obj.name}]")
                _sanity_results.extend(obj_issues)
            else:
                print(f"[NAD Sanity] {obj.name}: OK")

        print(f"[NAD Sanity] Done.")
        bpy.ops.nad.sanity_check_popup('INVOKE_DEFAULT')
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class NAD_PT_Toolset(bpy.types.Panel):
    bl_label = "NAD Toolset"
    bl_idname = "NAD_PT_toolset"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "nad_name1")
        layout.prop(scene, "nad_name2")
        layout.prop(scene, "nad_name3")

        # Suffix toggle row
        row = layout.row(align=True)
        for key in SUFFIXES:
            row.prop(scene, f"nad_suffix_{key.lower()}", text=key, toggle=True)

        layout.operator("nad.rename_objects")
        layout.separator()
        layout.operator("nad.sanity_check", icon='VIEWZOOM')


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

classes = (
    NAD_OT_Rename,
    NAD_OT_SanityCheckPopup,
    NAD_OT_SanityCheck,
    NAD_PT_Toolset,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.nad_name1 = bpy.props.StringProperty(
        name="Name 1",
        description="First part of the object name (e.g. asset name). Leave empty to skip it")
    bpy.types.Scene.nad_name2 = bpy.props.StringProperty(
        name="Name 2",
        description="Second part of the object name, joined after Name 1 with an underscore. Leave empty to skip it")
    bpy.types.Scene.nad_name3 = bpy.props.StringProperty(
        name="Name 3",
        description="Third part of the object name, joined after Name 2 with an underscore. Leave empty to skip it")
    for key in SUFFIXES:
        setattr(bpy.types.Scene, f"nad_suffix_{key.lower()}", bpy.props.BoolProperty(
            name=key,
            description=f"Add the '{key}' ({SUFFIX_DESCRIPTIONS[key]}) suffix to the name. "
                        f"Selecting it deselects the other suffixes; deselect it for no suffix",
            default=False, update=_make_suffix_update(key)))


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.nad_name1
    del bpy.types.Scene.nad_name2
    del bpy.types.Scene.nad_name3
    for key in SUFFIXES:
        delattr(bpy.types.Scene, f"nad_suffix_{key.lower()}")


if __name__ == "__main__":
    register()
