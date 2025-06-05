# lodkitfilter.py
# -*- coding: utf-8 -*-
"""
LOD/Kit/Component Layer Organizer for 3ds Max with dynamic group detection and filtering.
"""

from typing import List
from pymxs import runtime as rt
import os
import json

BASE_DIR = os.path.dirname(__file__)
SETTINGS_PATH = os.path.join(BASE_DIR, 'settings.json')
GROUP_TAGS_PATH = os.path.join(BASE_DIR, 'nametags.json')


def get_setting(section, key, default=None):
    if not os.path.exists(SETTINGS_PATH):
        return default
    with open(SETTINGS_PATH, 'r') as f:
        data = json.load(f)
    return data.get(section, {}).get(key, default)



def save_unique_component_tags():
    unique_tags = set()
    for obj in rt.objects:
        if not rt.isValidNode(obj):
            continue
        
        parts = obj.name.lower().split('_')
        if len(parts) >= 2:
            unique_tags.add(parts[1])

    base = get_setting("kits", "Base", "base")
    wheel = get_setting("kits", "Wheel", "wheel")
    interior = get_setting("kits", "Interior", "interior")

    tags = [base, wheel, interior] + sorted(unique_tags - {base, wheel, interior})

    with open(GROUP_TAGS_PATH, 'w') as f:
        json.dump({"groups": tags}, f, indent=4)

    print("Saved group tags to nametags.json:", tags)


def load_component_tags():
    save_unique_component_tags()
    with open(GROUP_TAGS_PATH, 'r') as f:
        data = json.load(f)
    return data.get("groups", [])


class NameParser:
    def __init__(self, raw_name: str):
        self.raw_name = raw_name
        self.parts = self._split_parts(raw_name)

    def _split_parts(self, name: str) -> List[str]:
        if not isinstance(name, str):
            return []
        return [part.strip().lower() for part in name.split('_') if part.strip()]

    def get_component_tag(self) -> str:
        return self.parts[1] if len(self.parts) >= 2 else ""


class LayerBuilder:
    def __init__(self, enabled_indices: List[int]):
        self.enabled_indices = enabled_indices
        self.layer_manager = rt.LayerManager
        self.tags = load_component_tags()

    def get_or_create_layer(self, name: str):
        existing = self.layer_manager.getLayerFromName(name)
        if existing:
            return existing
        return self.layer_manager.newLayerFromName(name)

    def assign_object_to_layer(self, obj, layer):
        if rt.isProperty(layer, 'addNode'):
            layer.addNode(obj)

    def build_layers(self):
        for obj in rt.objects:
            if not rt.isValidNode(obj):
                continue

            parser = NameParser(obj.name)
            comp_tag = parser.get_component_tag()
            if comp_tag not in self.tags:
                continue

            tag_index = self.tags.index(comp_tag)
            if tag_index not in self.enabled_indices:
                continue

            print(f"Placing {obj.name} into layer: {comp_tag}")
            layer = self.get_or_create_layer(comp_tag)
            self.assign_object_to_layer(obj, layer)


class SceneLayerOrganizer:
    def __init__(self, enabled_indices: List[int]):
        self.layer_builder = LayerBuilder(enabled_indices)

    def apply(self):
        self.layer_builder.build_layers()
        rt.redrawViews()


def apply_filter_from_button_states(button_states: dict):
    if not button_states.get("chkEnableFilter", False):
        print("Filter not enabled, skipping.")
        return

    tags = load_component_tags()
    print("Loaded tags:", tags )
    enabled_indices = []

    if button_states.get("btnBase", False):
        enabled_indices.append(0)
    if button_states.get("btnWheel", False):
        enabled_indices.append(1)
    if button_states.get("btnInterior", False):
        enabled_indices.append(2)

    for i in range(4):
        if button_states.get(f"btnKit{i}", False):
            index = i + 3
            if index < len(tags):
                enabled_indices.append(index)

    print("Enabled indices:", enabled_indices)
    organizer = SceneLayerOrganizer(enabled_indices)
    organizer.apply()
