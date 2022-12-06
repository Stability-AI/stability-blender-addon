from enum import Enum
import heapq
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

from .data import InitSource, RenderState
from .operators import DS_CancelRenderOperator, DS_SceneRenderAnimationOperator, DS_SceneRenderFrameOperator, DreamRenderOperator, DreamStateOperator
from .send_to_stability import render_img2img, render_text2img
import multiprocessing as mp
import threading
import glob
import platform
import tempfile
import time

# UI for the image editor panel.
class DreamStudioImageEditorPanel(Panel):
    bl_idname = "panel.dreamstudio_image_editor"
    bl_label = "DreamStudio"
    # https://docs.blender.org/api/current/bpy_types_enum_items/space_type_items.html#rna-enum-space-type-items
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "DreamStudio"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ds_settings
        init_source = InitSource[settings.init_source]

        if DreamStateOperator.render_state == RenderState.RENDERING:
            layout.label(text="Rendering...")
            layout.operator(DS_CancelRenderOperator.bl_idname)
            return
        elif DreamStateOperator.render_state == RenderState.DIFFUSING:
            layout.label(text="Diffusing...")
            layout.operator(DS_CancelRenderOperator.bl_idname)
            return

        layout.prop(settings, "init_source")
        if init_source != InitSource.NONE:
            layout.prop(settings, "init_strength")
        layout.prop(settings, "cfg_scale")
        layout.prop(settings, "guidance_strength")
        layout.prop(settings, "steps")
        layout.prop(settings, "seed")
        layout.prop(settings, "sampler")
        layout.prop(settings, "clip_guidance_preset")
        layout.prop(settings, "output_location")

        render_prompt_list(context.scene, layout)

        layout.operator(DreamRenderOperator.bl_idname, text="Dream (Texture)")


# UI for the scene view panel.
class DreamStudio3DPanel(Panel):
    bl_idname = "panel.dreamstudio"
    bl_label = "DreamStudio"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "DreamStudio"

    def redraw():
        for region in bpy.context.area.regions:
            if region.type == "UI":
                region.tag_redraw()

    def draw(self, context):
        settings = context.scene.ds_settings
        scene = context.scene
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = True

        if DreamStateOperator.render_state != RenderState.IDLE:
            state_text = (
                "Rendering..."
                if DreamStateOperator.render_state == RenderState.RENDERING
                else "Diffusing... Frame: {}".format(
                    DreamStateOperator.current_frame_idx
                )
            )
            layout.label(text=state_text)
            cancel_text = (
                "Cancel Render"
                if DreamStateOperator.render_state == RenderState.RENDERING
                else "Cancel Diffusion"
            )
            layout.operator(DS_CancelRenderOperator.bl_idname, text=cancel_text)
            return

        layout.prop(settings, "init_strength")
        layout.prop(settings, "cfg_scale")
        layout.prop(settings, "guidance_strength")
        layout.prop(settings, "seed")
        layout.prop(settings, "frame_limit")
        layout.prop(settings, "sampler")
        layout.prop(settings, "clip_guidance_preset")
        layout.prop(settings, "re_render")
        layout.prop(settings, "steps")
        layout.prop(settings, "output_location")

        # Just for padding purposes
        layout.label(text="")

        render_prompt_list(scene, layout)

        layout.operator(
            DS_SceneRenderAnimationOperator.bl_idname, text="Dream (Animation)"
        )
        layout.operator(DS_SceneRenderFrameOperator.bl_idname, text="Dream (Frame)")


# Render the list of prompts.
def render_prompt_list(scene, layout):

    title_row = layout.row()
    title_row.label(text="Prompts")
    title_row.operator("prompt_list.new_item", text="Add", icon="ADD")

    for i in range(len(scene.prompt_list)):
        item = scene.prompt_list[i]

        row = layout.row(align=True)

        row.alignment = "EXPAND"
        row.use_property_split = False
        row.prop(item, "prompt")
        row.prop(item, "strength")
        delete_op = row.operator(
            "prompt_list.remove_item", text="Remove", icon="REMOVE"
        )
        delete_op.index = i
