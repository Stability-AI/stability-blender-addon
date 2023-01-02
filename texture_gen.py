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

def get_uv_layer(mesh:bmesh.types.BMesh):
    for i in range(len(mesh.loops.layers.uv)):
        uv = mesh.loops.layers.uv[i]
        if uv.name.lower() == PROJECTED_UV_NAME.lower():
            return uv
        
    return mesh.loops.layers.uv.new(PROJECTED_UV_NAME)


def generate_uv_map(context, image_tex):
    projected_material = bpy.data.materials.new(name="dreamstudio_projected_material")
    projected_material.use_nodes = True
    texture_node = projected_material.node_tree.nodes.new("ShaderNodeTexImage")
    projected_material.node_tree.links.new(texture_node.outputs[0], projected_material.node_tree.nodes['Principled BSDF'].inputs[0])
    uv_node = projected_material.node_tree.nodes.new("ShaderNodeUVMap")
    uv_node.uv_map = PROJECTED_UV_NAME
    projected_material.node_tree.links.new(uv_node.outputs[0], texture_node.inputs[0]) 

    tex_w, tex_h = image_tex.size[0], image_tex.size[1]
    region_w, region_h = context.region.width, context.region.height

    w_scale, h_scale = region_w / tex_w, region_h / tex_h
    print(f"Scale: {w_scale}, {h_scale} ({region_w}, {region_h}) -> ({tex_w}, {tex_h})")

    area = None

    for screen_area in bpy.context.screen.areas:
        if screen_area.type == 'VIEW_3D':
            for region in screen_area.regions:
                if region.type == 'WINDOW':
                    area = screen_area

    for obj in bpy.context.selected_objects:
        if not hasattr(obj, "data") or not hasattr(obj.data, "materials"):
            continue
        material_index = len(obj.material_slots)
        obj.data.materials.append(projected_material)
        mesh = bmesh.from_edit_mesh(obj.data)
        # Project from UVs view and update material index
        mesh.verts.ensure_lookup_table()
        mesh.verts.index_update()
        uv_layer = get_uv_layer(mesh)
        mesh.faces.ensure_lookup_table()
        override = {'area': area, 'region': context.region, 'edit_object': obj}
        bpy.ops.uv.project_from_view(override , camera_bounds=False, correct_aspect=True)
        for face in mesh.faces:
            if face.select:
                face.material_index = material_index
        projected_material.name = "PROJ_MAT"
        texture_node.image = image_tex
        bmesh.update_edit_mesh(obj.data)

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
    