import bpy
from bpy.props import (
    PointerProperty,
    FloatProperty,
    IntProperty,
    EnumProperty,
    BoolProperty,
    StringProperty,
)
from bpy.types import AddonPreferences
from .operators import (
    DS_GetAPIKeyOperator,
    DS_LogIssueOperator,
    DS_FinishOnboardingOperator,
    DS_OpenDocumentationOperator,
    DS_OpenOutputFolderOperator,
    DS_SceneRenderExistingOutputOperator,
    DS_SceneRenderViewportOperator,
    DS_UseRenderFolderOperator,
    DreamStateOperator,
    DS_CancelRenderOperator,
    DS_ContinueRenderOperator,
    DreamRenderOperator,
)

from .ui import (
    AdvancedOptionsPanelSection3DEditor,
    DreamStudio3DPanel,
    DreamStudioImageEditorPanel,
    RenderOptionsPanelSection3DEditor,
    RenderOptionsPanelSectionImageEditor,
    AdvancedOptionsPanelSectionImageEditor,
)
from . import addon_updater_ops
from .dependencies import check_dependencies_installed
import getpass

from .data import (
    INIT_TYPES,
    OUTPUT_LOCATIONS,
    APIType,
    Engine,
    InitType,
    Sampler,
    engine_to_blender_enum,
    enum_to_blender_enum,
    get_image_size_options,
    initialize_sentry,
)
from .prompt_list import (
    PromptList_NewItem,
    PromptList_RemoveItem,
    PromptListItem,
)

# Update the entire UI when this property changes.
def ui_update(self, context):
    for region in context.area.regions:
        region.tag_redraw()
    return None


bl_info = {
    "name": "Stability for Blender",
    "author": "Stability AI",
    "description": "",
    "blender": (2, 80, 0),
    "version": (0, 0, 7),
    "location": "",
    "warning": "",
    "category": "AI",
}


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
        name="Use Recommended Quality Settings",
        default=True,
        description="Use the Stability-recommended quality settings for your current render settings",
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
        min=0,
        max=20,
        description="How much the prompt should influence the resulting image. 7.5 is a good starting point",
    )
    sampler: EnumProperty(
        name="Sampler",
        items=enum_to_blender_enum(Sampler),
        default=Sampler.K_DPMPP_2S_ANCESTRAL.value,
        description="The sampler to use for the diffusion process. The default sampler is recommended for most use cases. Check the documentation for a detailed description of the presets.",
    )
    generation_engine: EnumProperty(
        name="Engine",
        items=engine_to_blender_enum(),
        default=Engine.GENERATE_1_5.value,
        description="The model and configuration options used for generation",
    )
    use_custom_seed: BoolProperty(
        name="Set Seed",
        default=True,
        description="Use a custom seed for the diffusion process. This allows you to reproduce the same results for the same input frame. If unchecked, a different random seed will be used for each frame",
    )
    use_clip_guidance: BoolProperty(name="Use CLIP", default=True)
    # uint32 max value
    seed: IntProperty(
        name="Seed",
        default=0,
        min=0,
        max=2147483647,
        description="The seed fixes which random numbers are used for the diffusion process. This allows you to reproduce the same results for the same input frame. May also help with consistency across frames if you are rendering an animation",
    )

    use_render_resolution: BoolProperty(
        name="Use Render Resolution",
        default=False,
        description="Use the resolution in Blender's Output Properties as the size of the init image.",
    )
    init_image_height: EnumProperty(
        name="Init Image Height",
        default=512,
        items=get_image_size_options,
        description="The height of the image that is sent to the model. The rendered frame will be scaled to this size",
    )
    init_image_width: EnumProperty(
        name="Init Image Width",
        default=512,
        items=get_image_size_options,
        description="The width of the image that is sent to the model. The rendered frame will be scaled to this size",
    )

    # Output settings
    init_type: EnumProperty(
        name="Init Type",
        items=INIT_TYPES,
        default=InitType.TEXTURE.value,
        description="The source of the initial image. Select Scene Render to render the current frame and use that render as the init image, or select Image Editor to use the currently open image in the image editor as the init image. Select None to just use the prompt text to generate the image",
    )
    # Init type settings
    init_animation_folder_path: StringProperty(
        name="Frames Directory",
        subtype="DIR_PATH",
    )
    init_texture_ref: PointerProperty(
        name="Init Source",
        type=bpy.types.Image,
    )
    image_editor_use_init: BoolProperty(
        name="Use Init Image",
        default=True,
        description="Use the currently open image in the image editor as the init image. If unchecked, just use text",
    )
    output_location: EnumProperty(
        name="Open Result In",
        items=OUTPUT_LOCATIONS,
        description="The location to save the output image. The default is to open the result as a new image in the image editor. The other options are to output the images to the file system, and open the explorer to the image when diffusion is complete, or replace the existing image in the image editor.",
    )

    current_time: FloatProperty(name="Current Time", default=0, update=ui_update)


@addon_updater_ops.make_annotations
class DreamStudioPreferences(AddonPreferences):
    bl_idname = __package__

    api_key: StringProperty(name="API Key", default="")

    record_analytics: BoolProperty(
        name="Record and send error data to Stability",
        description="Allow Stability to capture anonymous analytics data. This will only be used for further product development. No personal data will be collected. This will install the Sentry SDK to allow us to capture these errors.",
        default=False,
    )

    base_url: StringProperty(
        name="API Base URL", default="https://api.stability.ai/v1alpha"
    )

    api_type: EnumProperty(
        name="API Protocol",
        items=enum_to_blender_enum(APIType),
        default=APIType.REST.value,
    )

    auto_check_update = bpy.props.BoolProperty(
        name="Auto-check for Update",
        description="If enabled, auto-check for updates using an interval",
        default=True,
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
        default=1,
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
        # Disabled until GRPC is supported.
        # layout.prop(self, "api_type")
        layout.prop(self, "api_key")
        layout.operator(DS_GetAPIKeyOperator.bl_idname, text="Get your API key here", icon="URL")
        layout.prop(self, "base_url")
        layout.prop(self, "record_analytics")
        layout.operator(
            DS_FinishOnboardingOperator.bl_idname,
            text="Reinstall Dependencies",
            icon="CONSOLE",
        )
        addon_updater_ops.update_settings_ui_condensed(self, context)


prompt_list_operators = [
    PromptList_NewItem,
    PromptList_RemoveItem,
    PromptListItem,
]

registered_operators = [
    DS_OpenDocumentationOperator,
    DS_LogIssueOperator,
    DreamStudioSettings,
    DreamRenderOperator,
    DreamStudioImageEditorPanel,
    DS_CancelRenderOperator,
    DS_ContinueRenderOperator,
    DS_SceneRenderExistingOutputOperator,
    DS_SceneRenderViewportOperator,
    DreamStateOperator,
    DreamStudio3DPanel,
    AdvancedOptionsPanelSection3DEditor,
    AdvancedOptionsPanelSectionImageEditor,
    RenderOptionsPanelSection3DEditor,
    RenderOptionsPanelSectionImageEditor,
    DS_FinishOnboardingOperator,
    DS_GetAPIKeyOperator,
    DS_OpenOutputFolderOperator,
    DS_UseRenderFolderOperator
]


def register():

    addon_updater_ops.register(bl_info)
    for op in prompt_list_operators:
        bpy.utils.register_class(op)

    bpy.types.Scene.prompt_list = bpy.props.CollectionProperty(type=PromptListItem)
    bpy.types.Scene.prompt_list_index = bpy.props.IntProperty(
        name="Index for prompt_list", default=0
    )

    if check_dependencies_installed() and not DreamStateOperator.sentry_initialized:
        initialize_sentry()
        DreamStateOperator.sentry_initialized = True

    for op in registered_operators:
        bpy.utils.register_class(op)


    bpy.utils.register_class(DreamStudioPreferences)
    bpy.types.Scene.ds_settings = PointerProperty(type=DreamStudioSettings)

    bpy.context.preferences.use_preferences_save = True

    # hehe
    if getpass.getuser() == "coold":
        prefs = bpy.context.preferences.addons[__package__].preferences
        prefs.api_key = "sk-Yc1fipqiDj98UVwEvVTP6OPgQmRk8cFRUSx79K9D3qCiNAFy"


def unregister():
    for op in registered_operators + prompt_list_operators:
        bpy.utils.unregister_class(op)
    del bpy.types.Scene.ds_settings
    bpy.utils.unregister_class(DreamStudioPreferences)
    addon_updater_ops.unregister()
