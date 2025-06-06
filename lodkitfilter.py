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

# Caches for faster operations
_layer_cache = {}
_layer_nodes = {}
_layer_visible = {}
_last_button_states = {}


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

def collect_scene_variants():
    variants = set()
    for obj in list(rt.objects):
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
    lyr = _layer_cache.get(name)
    if not lyr:
        lyr = lm.getLayerFromName(name)
        if lyr:
            _layer_cache[name] = lyr
    if lyr:
        return lyr
    lyr = lm.newLayerFromName(name)
    if _track_created:
        _created_layers.add(name)
    _layer_cache[name] = lyr
    return lyr

def get_layer_cached(name):
    lyr = _layer_cache.get(name)
    if lyr:
        return lyr
    lyr = rt.LayerManager.getLayerFromName(name)
    if lyr:
        _layer_cache[name] = lyr
    return lyr

def record_original_layer(obj):
    if obj.handle not in _original_layers:
        try:
            _original_layers[obj.handle] = obj.layer.name
        except Exception:
            pass

def restore_original_layers():
    lm = rt.LayerManager
    _layer_nodes.clear()
    layer_cache = {}
    nodes_by_layer = {}

    for handle, layer_name in list(_original_layers.items()):
        node = rt.maxOps.getNodeByHandle(handle)
        if not (node and rt.isValidNode(node)):
            continue
        lyr = layer_cache.get(layer_name)
        if lyr is None:
            lyr = get_layer_cached(layer_name)
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

def _collect_layer_handles(layer):
    """Return cached node handles for the given layer."""
    handles = _layer_nodes.get(layer.name)
    if handles is None:
        try:
            handles = [n.handle for n in list(layer.nodes) if rt.isValidNode(n)]
        except Exception:
            handles = []
        _layer_nodes[layer.name] = handles
    return handles

def _bulk_set_hidden(handles, hidden):
    if not handles:
        return
    state = "true" if hidden else "false"
    handle_list = ",".join(str(h) for h in handles)
    cmd = (
        f"for h in #({handle_list}) do ("
        f"local n = maxOps.getNodeByHandle h; if isValidNode n do n.isHidden = {state})"
    )
    try:
        rt.ExecuteMAXScriptScript(cmd)
    except Exception:
        pass

def _sync_layer_objects_visibility(layer):
    """Sync node hidden state with layer visibility using caching."""
    if not layer:
        return
    visible = bool(getattr(layer, 'on', True))
    handles = _collect_layer_handles(layer)
    _bulk_set_hidden(handles, not visible)

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
            _layer_nodes[layer_name] = [o.handle for o in nodes]
            _layer_visible[layer_name] = bool(getattr(lyr, 'on', True))

        if assign_wrong and wrong_layer:
            for obj in wrong_nodes:
                wrong_layer.addNode(obj)
            _layer_nodes[wrong_layer.name] = [o.handle for o in wrong_nodes]
            _layer_visible[wrong_layer.name] = bool(getattr(wrong_layer, 'on', True))

        for layer in parent_layers.values():
            _sync_layer_objects_visibility(layer)
            _layer_visible[layer.name] = bool(getattr(layer, 'on', True))
        for name, layer in lod_layers.items():
            _sync_layer_objects_visibility(layer)
        if wrong_layer:
            _sync_layer_objects_visibility(wrong_layer)

    rt.redrawViews()




def apply_visibility(button_states, variants):
    global _last_button_states
    if button_states == _last_button_states:
        return False
    _last_button_states = dict(button_states)

    layer_visibility = {}
    for variant in variants:
        var_visible = button_states.get(f"btnVar_{variant}", True)
        var_layer = get_layer_cached(variant)
        if var_layer:
            layer_visibility[var_layer] = var_visible
        for i in range(4):
            name = f"{variant}_LOD{i}"
            layer = get_layer_cached(name)
            if layer:
                layer_visibility[layer] = var_visible and button_states.get(f"btnL{i}", False)

    handles_to_hide = []
    handles_to_show = []

    changed = False
    with scene_redraw_off():
        for layer, state in layer_visibility.items():
            prev = _layer_visible.get(layer.name)
            if prev == state:
                continue
            layer.on = state
            _layer_visible[layer.name] = state
            handles = _collect_layer_handles(layer)
            if state:
                handles_to_show.extend(handles)
            else:
                handles_to_hide.extend(handles)
            changed = True

        _bulk_set_hidden(handles_to_hide, True)
        _bulk_set_hidden(handles_to_show, False)
    return changed

def apply_filter_from_button_states(button_states):
    """Update layer visibility according to UI states."""
    if not button_states.get('chkEnableFilter', False):
        rt.redrawViews()
        return

    if apply_visibility(button_states, _current_variants):
        rt.redrawViews()


def enable_filter():
    """Parse variants, create layers and record assignments."""
    global _current_variants, _track_created
    _current_variants = save_variants()
    _layer_cache.clear()
    _layer_nodes.clear()
    _layer_visible.clear()
    _last_button_states.clear()
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

        _layer_cache.clear()
        _layer_nodes.clear()
        _layer_visible.clear()
        _last_button_states.clear()

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
