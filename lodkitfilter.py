import os
import json
import re
import pymxs
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

# Track layers created while building structure
_created_layers = set()
_track_created = False

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
    lyr = lm.newLayerFromName(name)
    if _track_created:
        _created_layers.add(name)
    return lyr

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
                try:
                    node.isHidden = not bool(getattr(lyr, 'on', True))
                except Exception:
                    pass
    _original_layers.clear()

def _sync_layer_objects_visibility(layer):
    """Ensure objects in the layer match the layer's visibility."""
    if not layer:
        return
    visible = bool(getattr(layer, 'on', True))
    try:
        for node in list(layer.nodes):
            if rt.isValidNode(node):
                try:
                    node.isHidden = not visible
                except Exception:
                    pass
    except Exception:
        pass

def build_structure(variants, assign_wrong=True):
    """
    Оптимизированная версия build_structure.
    """
    lm = rt.LayerManager
    parent_layers = {}
    lod_layers = {}
    nodes_by_layer = {}  # Слой -> [объекты]
    wrong_nodes = []

    # Создаём родительские слои один раз
    for variant in variants:
        parent_layers[variant] = get_or_create_layer(variant)
    wrong_layer = get_or_create_layer("WrongNames") if assign_wrong else None

    # Сначала группируем объекты по слоям в памяти
    for obj in rt.objects:
        if not rt.isValidNode(obj):
            continue
        lod, variant = parse_name(obj.name)
        if lod is None or variant not in variants:
            if assign_wrong and wrong_layer:
                record_original_layer(obj)
                wrong_nodes.append(obj)
            continue
        record_original_layer(obj)
        lod_layer_name = f"{variant}_LOD{lod}"
        if lod_layer_name not in lod_layers:
            lod_layers[lod_layer_name] = get_or_create_layer(lod_layer_name)
            # Устанавливаем родителя только один раз
            if hasattr(lod_layers[lod_layer_name], 'setParent'):
                lod_layers[lod_layer_name].setParent(parent_layers[variant])
        nodes_by_layer.setdefault(lod_layer_name, []).append(obj)

    # Только теперь назначаем объекты слоям одним bulk-ом
    for layer_name, nodes in nodes_by_layer.items():
        lyr = lod_layers[layer_name]
        if hasattr(lyr, 'addNode'):
            for obj in nodes:
                lyr.addNode(obj)

    if assign_wrong and wrong_layer:
        for obj in wrong_nodes:
            wrong_layer.addNode(obj)

    # Видимость синхронизируем только по одному разу
    for layer in parent_layers.values():
        _sync_layer_objects_visibility(layer)
    for layer in lod_layers.values():
        _sync_layer_objects_visibility(layer)
    if wrong_layer:
        _sync_layer_objects_visibility(wrong_layer)
    rt.redrawViews()




def apply_visibility(button_states, variants):
    lm = rt.LayerManager
    for variant in variants:
        var_btn = button_states.get(f"btnVar_{variant}", True)
        var_layer = lm.getLayerFromName(variant)
        if var_layer:
            var_layer.on = var_btn
            _sync_layer_objects_visibility(var_layer)
        for i in range(4):
            lod_layer = lm.getLayerFromName(f"{variant}_LOD{i}")
            visible = var_btn and button_states.get(f"btnL{i}", False)
            if lod_layer:
                lod_layer.on = visible
                _sync_layer_objects_visibility(lod_layer)

def apply_filter_from_button_states(button_states):
    """Update layer visibility according to UI states."""
    if not button_states.get('chkEnableFilter', False):
        rt.redrawViews()
        return

    apply_visibility(button_states, _current_variants)
    rt.redrawViews()


def enable_filter():
    """Parse variants, create layers and record assignments."""
    global _current_variants, _track_created
    _current_variants = save_variants()
    with pymxs.undo(True):
        _track_created = True
        build_structure(_current_variants, assign_wrong=True)
        _track_created = False
    rt.redrawViews()


def disable_filter():
    """Restore nodes to their original layers and reset layer visibility."""
    global _track_created
    with pymxs.undo(True):
        restore_original_layers()
        lm = rt.LayerManager
        for variant in list(_current_variants):
            for i in range(4):
                lyr = lm.getLayerFromName(f"{variant}_LOD{i}")
                if lyr:
                    lyr.on = True
                    _sync_layer_objects_visibility(lyr)
            pl = lm.getLayerFromName(variant)
            if pl:
                pl.on = True
                _sync_layer_objects_visibility(pl)
        _created_layers.clear()
        _current_variants.clear()
        _track_created = False
    rt.redrawViews()


def make_layers():
    """Create LOD layers without enabling the filter."""
    global _track_created
    variants = save_variants()
    with pymxs.undo(True):
        _track_created = True
        build_structure(variants, assign_wrong=True)
        _track_created = False
    rt.redrawViews()
