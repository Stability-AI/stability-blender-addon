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
    DS_GetAPIKeyOperator,
    DS_GetSupportOperator,
    DS_InstallDependenciesOperator,
    DS_OpenDocumentationOperator,
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
from . import addon_updater_ops

from .data import (
    INIT_SOURCES,
    OUTPUT_LOCATIONS,
    APIType,
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
import sys


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
    steps: IntProperty(
        name="Steps",
        default=50,
        min=10,
        max=100,
        description="The more steps, the higher the resulting image quality",
    )

    # Diffusion settings
    use_recommended_settings: BoolProperty(
        name="Use Recommended Settings", default=True
    )
    init_strength: FloatProperty(
        name="Init Strength",
        default=0.5,
        min=0,
        max=1,
        description="How heavily the resulting generation should follow the input frame. 1 returns the input frame exactly, while 0 does not follow it at all. 0.5-0.6 typically produces good results",
    )
    cfg_scale: FloatProperty(
        name="Prompt Strength",
        default=7.5,
        description="How much the prompt should influence the resulting image. 7.5 is a good starting point",
    )
    sampler: EnumProperty(
        name="Sampler",
        items=enum_to_blender_enum(Sampler),
        default=Sampler.K_DPMPP_2S_ANCESTRAL.value,
        description="The sampler to use for the diffusion process. The default sampler is recommended for most use cases. Check the documentation for a detailed description of the presets.",
    )
    clip_guidance_preset: EnumProperty(
        name="CLIP Preset",
        items=enum_to_blender_enum(ClipGuidancePreset),
        default=ClipGuidancePreset.SIMPLE.value,
        description="The guidance preset to use for the diffusion process. The default is recommended for most use cases. Check the documentation for a detailed description of the presets.",
    )
    use_custom_seed: BoolProperty(name="Use Custom Seed", default=True)
    # uint32 max value
    seed: IntProperty(
        name="Seed",
        default=0,
        min=0,
        max=2147483647,
        description="The seet fixes which random numbers are used for the diffusion process. This allows you to reproduce the same results for the same input frame. May also help with consistency across frames if you are rendering an animation",
    )

    # Render output settings
    re_render: BoolProperty(name="Re-Render Scene", default=True)
    use_render_resolution: BoolProperty(name="Use Render Resolution", default=True)
    init_image_height: EnumProperty(
        name="Init Image Height",
        default=1,
        items=get_image_size_options,
        description="The height of the image that is sent to the model. The rendered frame will be scaled to this size",
    )
    init_image_width: EnumProperty(
        name="Init Image Width",
        default=1,
        items=get_image_size_options,
        description="The width of the image that is sent to the model. The rendered frame will be scaled to this size",
    )

    # 3D View settings
    re_render: BoolProperty(
        name="Re-Render",
        default=True,
        description="Whether to re-render the scene before sending it to the model",
    )

    # Output settings
    init_source: EnumProperty(
        name="Init Source",
        items=INIT_SOURCES,
        default=2,
        description="The source of the initial image. The default is the rendered frame. The other options are the active image or a new image in the image editor.",
    )
    output_location: EnumProperty(
        name="Display output",
        items=OUTPUT_LOCATIONS,
        default=2,
        description="The location to save the output image. The default is to open the result as a new image in the image editor. The other options are to output the images to the file system, and open the explorer to the image when diffusion is complete, or replace the existing image in the image editor.",
    )

    frame_timer: FloatProperty(default=0, update=ui_update)


@addon_updater_ops.make_annotations
class DreamStudioPreferences(AddonPreferences):
    bl_idname = __package__

    api_key: StringProperty(
        name="API Key", default="sk-Yc1fipqiDj98UVwEvVTP6OPgQmRk8cFRUSx79K9D3qCiNAFy"
    )
    base_url: StringProperty(
        name="REST API Base URL", default="https://api.stability.ai/v1alpha"
    )

    api_type: EnumProperty(
        name="API Protocol",
        items=enum_to_blender_enum(APIType),
        default=APIType.REST.value,
    )

    auto_check_update = bpy.props.BoolProperty(
        name="Auto-check for Update",
        description="If enabled, auto-check for updates using an interval",
        default=False,
    )

    updater_interval_months = bpy.props.IntProperty(
        name="Months",
        description="Number of months between checking for updates",
        default=0,
        min=0,
    )

    updater_interval_days = bpy.props.IntProperty(
        name="Days",
        description="Number of days between checking for updates",
        default=7,
        min=0,
        max=31,
    )

    updater_interval_hours = bpy.props.IntProperty(
        name="Hours",
        description="Number of hours between checking for updates",
        default=0,
        min=0,
        max=23,
    )

    updater_interval_minutes = bpy.props.IntProperty(
        name="Minutes",
        description="Number of minutes between checking for updates",
        default=0,
        min=0,
        max=59,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "api_type")
        layout.prop(self, "api_key")
        layout.prop(self, "base_url")
        layout.operator(
            DS_InstallDependenciesOperator.bl_idname,
            text="Reinstall Dependencies",
            icon="CONSOLE",
        )
        addon_updater_ops.update_settings_ui(self, context)


prompt_list_operators = [
    PromptList_NewItem,
    PromptList_RemoveItem,
    PromptListItem,
]

registered_operators = [
    DS_OpenDocumentationOperator,
    DS_GetSupportOperator,
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
    DS_InstallDependenciesOperator,
    DS_GetAPIKeyOperator,
]


def register():

    addon_updater_ops.register(bl_info)
    for op in prompt_list_operators:
        bpy.utils.register_class(op)

    bpy.utils.register_class(DreamStudioPreferences)

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
