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

from .prompt_list import render_prompt_list

from .data import InitSource, RenderState
from .operators import (
    DS_CancelRenderOperator,
    DS_SceneRenderAnimationOperator,
    DS_SceneRenderFrameOperator,
    DreamRenderOperator,
    DreamStateOperator,
)
from .send_to_stability import render_img2img, render_text2img
import multiprocessing as mp
import threading
import glob
import platform
import tempfile
import time

DS_CATEGORY = "DreamStudio"
DS_REGION_TYPE = "UI"

# Render the list of prompts.
def render_in_progress_view(layout):
    state_text = (
        "Rendering..."
        if DreamStateOperator.render_state == RenderState.RENDERING
        else "Diffusing... Frame: {}".format(DreamStateOperator.current_frame_idx)
    )
    layout.label(text=state_text)
    cancel_text = (
        "Cancel Render"
        if DreamStateOperator.render_state == RenderState.RENDERING
        else "Cancel Diffusion"
    )
    layout.operator(DS_CancelRenderOperator.bl_idname, text=cancel_text)
    return


# UI for the image editor panel.
class DreamStudioImageEditorPanel(Panel):
    bl_idname = "panel.dreamstudio_image_editor"
    bl_label = "DreamStudio"
    # https://docs.blender.org/api/current/bpy_types_enum_items/space_type_items.html#rna-enum-space-type-items
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = DS_CATEGORY

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ds_settings
        init_source = InitSource[settings.init_source]

        if DreamStateOperator.render_state != RenderState.IDLE:
            render_in_progress_view(layout)
            return

        layout.prop(settings, "init_source")
        if init_source != InitSource.NONE:
            layout.prop(settings, "init_strength")

        render_prompt_list(context.scene, layout)

        layout.operator(DreamRenderOperator.bl_idname, text="Dream (Texture)")


# UI for the scene view panel.
class DreamStudio3DPanel(Panel):
    bl_idname = "panel.dreamstudio"
    bl_label = "DreamStudio"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = DS_CATEGORY

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
            render_in_progress_view(layout)
            return

        render_prompt_list(scene, layout)

        valid, validation_msg = validate_settings(settings, scene)

        if not valid:
            layout.label(text=validation_msg, icon="ERROR")
        else:
            layout.label(text="Ready to render!", icon="CHECKMARK")

        row = layout.row()
        row.scale_y = 2.0
        row.operator(
            DS_SceneRenderAnimationOperator.bl_idname, text="Dream (Animation)"
        )
        row.operator(DS_SceneRenderFrameOperator.bl_idname, text="Dream (Frame)")
        row.enabled = valid


# Individual panel sections are added by setting bl_parent_id
class PanelSection:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = DS_CATEGORY


# Validation messages should be no longer than 50 chars or so.
def validate_settings(settings, scene) -> tuple[bool, str]:
    width, height = int(settings.init_image_width), int(settings.init_image_height)
    if settings.use_render_resolution:
        width, height = int(scene.render.resolution_x), int(scene.render.resolution_y)
    prompts = scene.prompt_list
    # cannot be > 1 megapixel
    if width * height > 1_000_000:
        return False, "Image size cannot be greater than 1 megapixel."

    if not prompts or len(prompts) < 1:
        return False, "Add at least one prompt to the prompt list."

    return True, ""


class RenderOptionsPanelSection(PanelSection, Panel):

    bl_parent_id = DreamStudio3DPanel.bl_idname
    bl_label = "Render Options"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ds_settings
        use_custom_res = not settings.use_render_resolution
        layout.prop(settings, "re_render")
        layout.prop(settings, "use_render_resolution")
        image_size_row = layout.row()
        image_size_row.enabled = use_custom_res
        image_size_row.prop(settings, "init_image_height", text="Height")
        image_size_row.prop(settings, "init_image_width", text="Width")


class AdvancedOptionsPanelSection(PanelSection, Panel):

    bl_parent_id = DreamStudio3DPanel.bl_idname
    bl_label = "Advanced Options"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ds_settings
        layout.prop(settings, "clip_guidance_preset")
        layout.prop(settings, "cfg_scale", text="Prompt Strength")
        layout.prop(settings, "steps", text="Steps")
        layout.prop(settings, "seed")
        layout.prop(settings, "sampler")
        layout.prop(settings, "output_location")
