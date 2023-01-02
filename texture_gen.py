import datetime
from enum import Enum
import heapq
import subprocess
from typing import List
import bpy
from bpy.props import (
    StringProperty,
    IntProperty,
    CollectionProperty,
    IntProperty,
    PointerProperty,
    EnumProperty,
)
from bpy.types import PropertyGroup, UIList, Operator, Panel, AddonPreferences
import bmesh
import bpy_extras
import sys
import os
import site
from threading import Thread
import time
import webbrowser
from bpy.app.handlers import persistent
from bpy_extras import view3d_utils
import gpu

PROJECTED_UV_NAME = "DreamStudioUVMap"
MATERIAL_NAME = "DreamStudioMaterial"

def getArea(type):
    for screen in bpy.context.workspace.screens:
        for area in screen.areas:
            if area.type == type:
                return area


def generate_uv_map(context, image_tex):
    projected_material = bpy.data.materials.new(name="dreamstudio_projected_material")
    projected_material.use_nodes = True
    texture_node = projected_material.node_tree.nodes.new("ShaderNodeTexImage")
    projected_material.node_tree.links.new(texture_node.outputs[0], projected_material.node_tree.nodes['Principled BSDF'].inputs[0])
    uv_node = projected_material.node_tree.nodes.new("ShaderNodeUVMap")
    uv_node.uv_map = PROJECTED_UV_NAME
    projected_material.node_tree.links.new(uv_node.outputs[0], texture_node.inputs[0]) 
    projected_material.name = MATERIAL_NAME
    texture_node.image = image_tex

    area = None

    for screen_area in bpy.context.screen.areas:
        if screen_area.type == 'VIEW_3D':
            for region in screen_area.regions:
                if region.type == 'WINDOW':
                    area = screen_area

    for ns3d in getArea('VIEW_3D').spaces:
        if ns3d.type == "VIEW_3D":
            break

    for b_obj in bpy.context.selected_objects:
        if b_obj.type != "MESH" or not hasattr(b_obj, "data"):
            continue

        if b_obj.data.uv_layers:
            uv_layers = b_obj.data.uv_layers
            # delete all existing uv maps
            for uv in uv_layers:
                uv_layers.remove(uv)

        # delete all existing materials
        if b_obj.data.materials:
            for material in b_obj.data.materials:
                if material:
                    bpy.data.materials.remove(material, do_unlink=True)

        b_obj.active_material_index = 0
        for i in range(len(b_obj.material_slots)):
            bpy.ops.object.material_slot_remove({'object': b_obj})

        ns3d.region_3d.update()

        bpy.ops.object.mode_set(mode='EDIT')
        # convert to edit mode and generate verts table
        mesh = bmesh.from_edit_mesh(b_obj.data)
        mesh.faces.ensure_lookup_table()
        mesh.verts.ensure_lookup_table()
        mesh.verts.index_update()

        mesh.loops.layers.uv.new(PROJECTED_UV_NAME)
        b_obj.data.materials.append(projected_material)
        # create new uv map
        override = {'area': area, 'region': context.region, 'edit_object': b_obj}
        bpy.ops.uv.project_from_view(override , camera_bounds=False, correct_aspect=True)
        for face in mesh.faces:
            face.material_index = len(b_obj.material_slots)

        bmesh.update_edit_mesh(b_obj.data)
        bpy.ops.object.mode_set(mode='OBJECT')

def generate_depth_map():
    import numpy as np
    from PIL import Image
    framebuffer = gpu.state.active_framebuffer_get()
    viewport = gpu.state.viewport_get()
    width, height = viewport[2], viewport[3]
    fb_list = framebuffer.read_depth(0, 0, width, height).to_list()
    depth = np.array(fb_list)

    depth = 1 - depth
    depth = np.interp(depth, [np.ma.masked_equal(depth, 0, copy=False).min(), depth.max()], [0, 1]).clip(0, 1)
    depth_img = Image.fromarray(depth.astype('uint8'), 'RGB')
    return depth_img
    