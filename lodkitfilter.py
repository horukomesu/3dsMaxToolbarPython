import os
import json
import re
from pymxs import runtime as rt

BASE_DIR = os.path.dirname(__file__)
GROUP_TAGS_PATH = os.path.join(BASE_DIR, 'nametags.json')

# Keeps original layer assignments so they can be restored when disabling the filter
_original_layers = {}
# Current list of variants parsed when the filter was enabled
_current_variants = []
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

from pymxs import runtime as rt

def build_structure(variants):
    """
    Для каждого варианта создаёт родительский слой (variant).
    Для каждого variant_LODX создаёт слой и назначает ему parent через setParent().
    Объекты сцены назначаются в слой variant_LODX.
    """
    lm = rt.LayerManager
    parent_layers = {}
    # Создаём родительские слои
    for variant in variants:
        parent_layers[variant] = get_or_create_layer(variant)
    # Собираем все объекты и создаём LOD-слои
    for obj in rt.objects:
        if not rt.isValidNode(obj):
            continue
        lod, variant = parse_name(obj.name)
        if lod is None or variant not in variants:
            continue
        record_original_layer(obj)
        var_layer = parent_layers[variant]
        lod_layer_name = f"{variant}_LOD{lod}"
        lod_layer = get_or_create_layer(lod_layer_name)
        # Устанавливаем родителя через setParent
        if hasattr(lod_layer, 'setParent'):
            lod_layer.setParent(var_layer)
        # Назначаем объект в слой
        if hasattr(lod_layer, 'addNode'):
            lod_layer.addNode(obj)
    # Обновляем отображение
    rt.redrawViews()



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
    """Update layer visibility according to UI states."""
    if not button_states.get('chkEnableFilter', False):
        rt.redrawViews()
        return

    apply_visibility(button_states, _current_variants)
    rt.redrawViews()


def enable_filter():
    """Parse variants, create layers and record assignments."""
    global _current_variants
    _current_variants = save_variants()
    build_structure(_current_variants)
    rt.redrawViews()


def disable_filter():
    """Restore nodes to their original layers and show all custom layers."""
    restore_original_layers()
    lm = rt.LayerManager
    for variant in list(_current_variants):
        lyr = lm.getLayerFromName(variant)
        if lyr:
            lyr.on = True
        for i in range(4):
            l2 = lm.getLayerFromName(f"{variant}_LOD{i}")
            if l2:
                l2.on = True
    _current_variants.clear()
    rt.redrawViews()
