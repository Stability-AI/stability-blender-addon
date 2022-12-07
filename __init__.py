from enum import Enum
import bpy
from bpy.props import (
    PointerProperty,
    FloatProperty,
    IntProperty,
    EnumProperty,
    BoolProperty,
    StringProperty,
    CollectionProperty,
)
from bpy.types import AddonPreferences
import os
from .operators import (
    DS_SceneRenderAnimationOperator,
    DS_SceneRenderFrameOperator,
    DreamStateOperator,
    DS_CancelRenderOperator,
    DS_ContinueRenderOperator,
    UIContext,
    DreamRenderOperator,
)

from .ui import (
    AdvancedOptionsPanelSection,
    DreamStudio3DPanel,
    DreamStudioImageEditorPanel,
    RenderOptionsPanelSection,
)

from .data import (
    INIT_SOURCES,
    OUTPUT_LOCATIONS,
    ClipGuidancePreset,
    Sampler,
    enum_to_blender_enum,
    get_image_size_options,
)
from .send_to_stability import render_img2img, render_text2img
from .prompt_list import (
    PromptList_NewItem,
    PromptList_RemoveItem,
    PromptListItem,
    PromptListUIItem,
)
import threading
import glob


bl_info = {
    "name": "Dream Studio",
    "author": "Stability AI",
    "description": "",
    "blender": (2, 80, 0),
    "version": (0, 0, 1),
    "location": "",
    "warning": "",
    "category": "AI",
}

# Update the entire UI when this property changes.
def ui_update(self, context):
    for region in context.area.regions:
        if region.type == "UI":
            region.tag_redraw()
    print("update ui")
    return None


class DreamStudioSettings(bpy.types.PropertyGroup):

    # Global settings
    steps: IntProperty(name="Steps", default=50, min=10, max=100)

    # Diffusion settings
    init_strength: FloatProperty(name="Init Strength", default=0.5, min=0, max=1)
    cfg_scale: FloatProperty(name="CFG Scale", default=7.5)
    frame_limit: IntProperty(name="Frame Limit", default=1000)
    sampler: EnumProperty(
        name="Sampler",
        items=enum_to_blender_enum(Sampler),
        default=Sampler.K_DPMPP_2S_ANCESTRAL.value,
    )
    clip_guidance_preset: EnumProperty(
        name="CLIP Preset",
        items=enum_to_blender_enum(ClipGuidancePreset),
        default=ClipGuidancePreset.SIMPLE.value,
    )
    seed: IntProperty(name="Seed", default=0, min=0, max=1000000)

    # Render output settings
    re_render: BoolProperty(name="Re-Render Scene", default=True)
    use_render_resolution: BoolProperty(name="Use Render Resolution", default=True)
    init_image_height: EnumProperty(
        name="Init Image Height", default=1, items=get_image_size_options
    )
    init_image_width: EnumProperty(
        name="Init Image Width", default=1, items=get_image_size_options
    )

    # 3D View settings
    re_render: BoolProperty(name="Re-Render", default=True)

    # Output settings
    init_source: EnumProperty(name="Init Source", items=INIT_SOURCES, default=2)
    output_location: EnumProperty(
        name="Output Location", items=OUTPUT_LOCATIONS, default=2
    )

    frame_timer: FloatProperty(default=0, update=ui_update)


class DreamStudioPreferences(AddonPreferences):
    bl_idname = __package__

    api_key: StringProperty(
        name="API Key", default="sk-Yc1fipqiDj98UVwEvVTP6OPgQmRk8cFRUSx79K9D3qCiNAFy"
    )
    base_url: StringProperty(
        name="API Base URL", default="https://api.stability.ai/v1alpha"
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "api_key")
        layout.prop(self, "base_url")


prompt_list_operators = [
    PromptList_NewItem,
    PromptList_RemoveItem,
    PromptListItem,
]

registered_operators = [
    DreamStudioPreferences,
    DreamStudioSettings,
    DreamRenderOperator,
    DreamStudioImageEditorPanel,
    DS_CancelRenderOperator,
    DS_ContinueRenderOperator,
    DS_SceneRenderAnimationOperator,
    DS_SceneRenderFrameOperator,
    DreamStateOperator,
    DreamStudio3DPanel,
    AdvancedOptionsPanelSection,
    RenderOptionsPanelSection,
]


def register():
    for op in prompt_list_operators:
        bpy.utils.register_class(op)

    bpy.types.Scene.prompt_list = bpy.props.CollectionProperty(
        type=prompt_list.PromptListItem
    )
    bpy.types.Scene.prompt_list_index = bpy.props.IntProperty(
        name="Index for prompt_list", default=0
    )

    for op in registered_operators:
        bpy.utils.register_class(op)

    bpy.types.Scene.ds_settings = PointerProperty(type=DreamStudioSettings)


def unregister():
    for op in registered_operators + prompt_list_operators:
        bpy.utils.unregister_class(op)
    del bpy.types.Scene.ds_settings
