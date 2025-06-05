import os
import json
import re
from pymxs import runtime as rt

BASE_DIR = os.path.dirname(__file__)
GROUP_TAGS_PATH = os.path.join(BASE_DIR, 'nametags.json')

_original_layers = {}
# Matches names like "LOD3_VARIANT_..." or "l0_test_..." (case-insensitive)
# Variant name stops at the first underscore after the LOD index.
_LOD_RE = re.compile(r'^(?:lod|l)(\d+)_([^_]+)_', re.I)

def load_variants():
    if not os.path.exists(GROUP_TAGS_PATH):
        return []
    with open(GROUP_TAGS_PATH, 'r') as f:
        data = json.load(f)
    return [v.lower() for v in data.get('groups', [])]

def collect_scene_variants():
    variants = set()
    for obj in rt.objects:
        if not rt.isValidNode(obj):
            continue
        _, variant = parse_name(obj.name)
        if variant:
            variants.add(variant)
    return sorted(variants)

def save_variants():
    tags = collect_scene_variants()
    with open(GROUP_TAGS_PATH, 'w') as f:
        json.dump({'groups': tags}, f, indent=4)
    return tags

def parse_name(name):
    if not isinstance(name, str):
        return None, None
    m = _LOD_RE.match(name)
    if not m:
        return None, None
    return int(m.group(1)), m.group(2).lower()

def get_or_create_layer(name):
    lm = rt.LayerManager
    lyr = lm.getLayerFromName(name)
    if lyr:
        return lyr
    return lm.newLayerFromName(name)

def record_original_layer(obj):
    if obj.handle not in _original_layers:
        try:
            _original_layers[obj.handle] = obj.layer.name
        except Exception:
            pass

def restore_original_layers():
    lm = rt.LayerManager
    for handle, layer_name in list(_original_layers.items()):
        node = rt.maxOps.getNodeByHandle(handle)
        if node and rt.isValidNode(node):
            lyr = lm.getLayerFromName(layer_name)
            if lyr:
                lyr.addNode(node)
    _original_layers.clear()

def build_structure(variants):
    for obj in rt.objects:
        if not rt.isValidNode(obj):
            continue
        lod, variant = parse_name(obj.name)
        if lod is None or variant not in variants:
            continue
        record_original_layer(obj)
        var_layer = get_or_create_layer(variant)
        lod_layer = get_or_create_layer(f"{variant}_LOD{lod}")
        if hasattr(lod_layer, 'parent'):
            lod_layer.parent = var_layer
        if hasattr(lod_layer, 'addNode'):
            lod_layer.addNode(obj)

def apply_visibility(button_states, variants):
    lm = rt.LayerManager
    for variant in variants:
        var_btn = button_states.get(f"btnVar_{variant}", True)
        var_layer = lm.getLayerFromName(variant)
        if var_layer:
            var_layer.on = var_btn
        for i in range(4):
            lod_layer = lm.getLayerFromName(f"{variant}_LOD{i}")
            visible = var_btn and button_states.get(f"btnL{i}", False)
            if lod_layer:
                lod_layer.on = visible

def apply_filter_from_button_states(button_states):
    if not button_states.get('chkEnableFilter', False):
        variants = load_variants()
        restore_original_layers()
        tmp = {f'btnVar_{v}': True for v in variants}
        tmp.update({f'btnL{i}': True for i in range(4)})
        apply_visibility(tmp, variants)
        rt.redrawViews()
        return

    variants = save_variants()
    build_structure(variants)
    apply_visibility(button_states, variants)
    rt.redrawViews()
