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

def get_uv_layer(cls, mesh:bmesh.types.BMesh):
    for i in range(len(mesh.loops.layers.uv)):
        uv = mesh.loops.layers.uv[i]
        if uv.name.lower() == "projected uvs":
            return uv
        
    return mesh.loops.layers.uv.new("Projected UVs")


def generate_uv_map(context, image_tex):
    projected_material = bpy.data.materials.new(name="dreamstudio_projected_material")
    projected_material.use_nodes = True
    texture_node = projected_material.node_tree.nodes.new("ShaderNodeTexImage")
    projected_material.node_tree.links.new(texture_node.outputs[0], projected_material.node_tree.nodes['Principled BSDF'].inputs[0])
    uv_node = projected_material.node_tree.nodes.new("ShaderNodeUVMap")
    uv_node.uv_map = PROJECTED_UV_NAME
    projected_material.node_tree.links.new(uv_node.outputs[0], texture_node.inputs[0]) 

    for obj in bpy.context.selected_objects:
        if not hasattr(obj, "data") or not hasattr(obj.data, "materials"):
            continue
        material_index = len(obj.material_slots)
        obj.data.materials.append(projected_material)
        mesh = bmesh.from_edit_mesh(obj.data)
        # Project from UVs view and update material index
        mesh.verts.ensure_lookup_table()
        mesh.verts.index_update()
        def vert_to_uv(v):
            screen_space = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, obj.matrix_world @ v.co)
            if screen_space is None:
                return None
            return (screen_space[0] / context.region.width, screen_space[1] / context.region.height)
        uv_layer = get_uv_layer(mesh)
        mesh.faces.ensure_lookup_table()
        for face in mesh.faces:
            if face.select:
                for loop in face.loops:
                    uv = vert_to_uv(mesh.verts[loop.vert.index])
                    if uv is None:
                        continue
                    loop[uv_layer].uv = uv
                face.material_index = material_index
        # TODO pass in image
        texture = bpy.data.images.new(name="DS_TEX_IMG", width=image_tex.width, height=image_tex.height)
        texture.name = "DS_TEX"
        projected_material.name = "PROJ_MAT"
        texture.pixels[:] = image_tex.ravel()
        texture.update()
        texture_node.image = texture
        bmesh.update_edit_mesh(obj.data)

# TODO use this in the depth map gen step
def generate_depth_map():
    import numpy as np
    framebuffer = gpu.state.active_framebuffer_get()
    viewport = gpu.state.viewport_get()
    width, height = viewport[2], viewport[3]
    depth = np.array(framebuffer.read_depth(0, 0, width, height).to_list())

    depth = 1 - depth
    depth = np.interp(depth, [np.ma.masked_equal(depth, 0, copy=False).min(), depth.max()], [0, 1]).clip(0, 1)
    return depth
    