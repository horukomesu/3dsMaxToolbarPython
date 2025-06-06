import os
import json
import re
import time
from contextlib import contextmanager
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


@contextmanager
def scene_redraw_off():
    """Temporarily disable scene redraw for bulk operations."""
    try:
        rt.disableSceneRedraw()
        yield
    finally:
        rt.enableSceneRedraw()


def profile_time(func):
    """Decorator to measure execution time of heavy functions."""
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        duration = time.perf_counter() - start
        print(f"{func.__name__} took {duration:.3f}s")
        return result
    return wrapper

def load_variants():
    if not os.path.exists(GROUP_TAGS_PATH):
        return []
    with open(GROUP_TAGS_PATH, 'r') as f:
        data = json.load(f)
    return [v.lower() for v in data.get('groups', [])]

@profile_time
def collect_scene_variants():
    variants = set()
    for obj in list(rt.objects):
        if not rt.isValidNode(obj):
            continue
        _, variant = parse_name(obj.name)
        if variant:
            variants.add(variant)
    return sorted(variants)

@profile_time
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

@profile_time
def restore_original_layers():
    lm = rt.LayerManager
    layer_cache = {}
    nodes_by_layer = {}

    for handle, layer_name in list(_original_layers.items()):
        node = rt.maxOps.getNodeByHandle(handle)
        if not (node and rt.isValidNode(node)):
            continue
        lyr = layer_cache.get(layer_name)
        if lyr is None:
            lyr = lm.getLayerFromName(layer_name)
            layer_cache[layer_name] = lyr
        if lyr:
            nodes_by_layer.setdefault(lyr, []).append(node)

    with scene_redraw_off():
        for lyr, nodes in nodes_by_layer.items():
            for node in nodes:
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

@profile_time
def build_structure(variants, assign_wrong=True):
    """Create LOD layers and assign objects in bulk."""
    lm = rt.LayerManager
    parent_layers = {v: get_or_create_layer(v) for v in variants}
    lod_layers = {}
    nodes_by_layer = {}
    wrong_nodes = []
    wrong_layer = get_or_create_layer("WrongNames") if assign_wrong else None

    # Сначала собираем информацию об объектах
    for obj in list(rt.objects):
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
            lod_layer = get_or_create_layer(lod_layer_name)
            lod_layers[lod_layer_name] = lod_layer
            if hasattr(lod_layer, 'setParent'):
                lod_layer.setParent(parent_layers[variant])
        nodes_by_layer.setdefault(lod_layer_name, []).append(obj)

    # Массовое назначение объектов слоям и синхронизация видимости
    with scene_redraw_off():
        for layer_name, nodes in nodes_by_layer.items():
            lyr = lod_layers[layer_name]
            for obj in nodes:
                lyr.addNode(obj)

        if assign_wrong and wrong_layer:
            for obj in wrong_nodes:
                wrong_layer.addNode(obj)

        for layer in parent_layers.values():
            _sync_layer_objects_visibility(layer)
        for layer in lod_layers.values():
            _sync_layer_objects_visibility(layer)
        if wrong_layer:
            _sync_layer_objects_visibility(wrong_layer)

    rt.redrawViews()




@profile_time
def apply_visibility(button_states, variants):
    lm = rt.LayerManager
    layer_cache = {}
    layer_visibility = {}

    # Подготавливаем список слоёв и желаемую видимость
    for variant in variants:
        var_visible = button_states.get(f"btnVar_{variant}", True)
        var_layer = lm.getLayerFromName(variant)
        if var_layer:
            layer_visibility[var_layer] = var_visible
            layer_cache[variant] = var_layer
        for i in range(4):
            name = f"{variant}_LOD{i}"
            layer = lm.getLayerFromName(name)
            if layer:
                layer_visibility[layer] = var_visible and button_states.get(f"btnL{i}", False)
                layer_cache[name] = layer

    with scene_redraw_off():
        for layer, state in layer_visibility.items():
            layer.on = state
        for layer in layer_visibility:
            _sync_layer_objects_visibility(layer)

@profile_time
def apply_filter_from_button_states(button_states):
    """Update layer visibility according to UI states."""
    if not button_states.get('chkEnableFilter', False):
        rt.redrawViews()
        return

    apply_visibility(button_states, _current_variants)
    rt.redrawViews()


@profile_time
def enable_filter():
    """Parse variants, create layers and record assignments."""
    global _current_variants, _track_created
    _current_variants = save_variants()
    with pymxs.undo(True):
        _track_created = True
        build_structure(_current_variants, assign_wrong=True)
        _track_created = False
    rt.redrawViews()


@profile_time
def disable_filter():
    """Restore nodes to their original layers and reset layer visibility."""
    global _track_created
    with pymxs.undo(True):
        restore_original_layers()
        lm = rt.LayerManager

        layers_to_show = []
        for variant in list(_current_variants):
            pl = lm.getLayerFromName(variant)
            if pl:
                layers_to_show.append(pl)
            for i in range(4):
                lyr = lm.getLayerFromName(f"{variant}_LOD{i}")
                if lyr:
                    layers_to_show.append(lyr)

        with scene_redraw_off():
            for lyr in layers_to_show:
                lyr.on = True
            for lyr in layers_to_show:
                _sync_layer_objects_visibility(lyr)

        _created_layers.clear()
        _current_variants.clear()
        _track_created = False
    rt.redrawViews()


@profile_time
def make_layers():
    """Create LOD layers without enabling the filter."""
    global _track_created
    variants = save_variants()
    with pymxs.undo(True):
        _track_created = True
        build_structure(variants, assign_wrong=True)
        _track_created = False
    rt.redrawViews()
