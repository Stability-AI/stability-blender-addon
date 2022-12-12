import bpy
from bpy.types import Panel

from .prompt_list import MULTIPROMPT_ENABLED, render_prompt_list

from .data import (
    InitSource,
    RenderState,
    check_dependencies_installed,
    get_init_image_dimensions,
)
from .operators import (
    DS_CancelRenderOperator,
    DS_ExportKeyframesOperator,
    DS_GetAPIKeyOperator,
    DS_GetSupportOperator,
    DS_InstallDependenciesOperator,
    DS_OpenDocumentationOperator,
    DS_SceneRenderAnimationOperator,
    DS_SceneRenderFrameOperator,
    DS_SceneRenderVideoInitOperator,
    DreamRenderOperator,
    DreamStateOperator,
)


DS_CATEGORY = "DreamStudio"
DS_REGION_TYPE = "UI"


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


def render_onboard_view(layout):
    layout.label(text="Please enter your API key.")
    layout.label(text="Enter in File -> Preferences -> Add-ons -> AI: Dream Studio")
    layout.label(text="You can find it by pressing the button below:")
    layout.operator(DS_GetAPIKeyOperator.bl_idname, text="Get API Key", icon="URL")
    layout.label(text="Then, install SDK dependencies.")
    layout.operator(
        DS_InstallDependenciesOperator.bl_idname, text="Install", icon="CONSOLE"
    )


def render_links_row(layout):
    links_row = layout.row()
    links_row.operator(
        DS_OpenDocumentationOperator.bl_idname, text="Open Docs", icon="TEXT"
    )
    links_row.operator(
        DS_GetSupportOperator.bl_idname, text="Get Support", icon="QUESTION"
    )


def render_output_location_row(layout, settings):
    output_location_row = layout.row()
    output_location_row.alignment = "EXPAND"
    output_location_row.use_property_split = False
    output_location_row.use_property_decorate = False
    output_location_row.prop(settings, "output_location")


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

        preferences = bpy.context.preferences.addons[__package__].preferences

        if not preferences.api_key or preferences.api_key == "":
            DreamStateOperator.render_state = RenderState.ONBOARDING

        if not check_dependencies_installed():
            DreamStateOperator.render_state = RenderState.ONBOARDING

        if DreamStateOperator.render_state == RenderState.ONBOARDING:
            render_onboard_view(layout)
            return

        if DreamStateOperator.render_state != RenderState.IDLE:
            render_in_progress_view(layout)
            return

        render_links_row(layout)

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
        preferences = bpy.context.preferences.addons[__package__].preferences

        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = True

        if not preferences.api_key or preferences.api_key == "":
            DreamStateOperator.render_state = RenderState.ONBOARDING

        if not check_dependencies_installed():
            DreamStateOperator.render_state = RenderState.ONBOARDING

        layout.operator(DS_ExportKeyframesOperator.bl_idname, text="Export Keyframes")

        if DreamStateOperator.render_state == RenderState.ONBOARDING:
            render_onboard_view(layout)
            return

        if DreamStateOperator.render_state != RenderState.IDLE:
            render_in_progress_view(layout)
            return

        render_links_row(layout)

        valid, validation_msg = validate_settings(settings, scene)

        render_prompt_list(scene, layout)

        if not valid:
            layout.label(text=validation_msg, icon="ERROR")
        else:
            layout.label(text="Ready to dream!", icon="CHECKMARK")

        dream_btn_row = layout.row()
        dream_btn_row.scale_y = 2.0
        dream_btn_row.operator(
            DS_SceneRenderAnimationOperator.bl_idname, text="Dream (Animation)"
        )
        dream_btn_row.operator(
            DS_SceneRenderFrameOperator.bl_idname, text="Dream (Frame)"
        )
        dream_btn_row.operator(
            DS_SceneRenderVideoInitOperator.bl_idname, text="Dream (Video)"
        )
        dream_btn_row.enabled = valid


# Validation messages should be no longer than 50 chars or so.
def validate_settings(settings, scene) -> tuple[bool, str]:
    width, height = get_init_image_dimensions(settings, scene)
    prompts = scene.prompt_list
    # cannot be > 1 megapixel
    if width * height > 1_000_000:
        return False, "Image size cannot be greater than 1 megapixel."

    if not prompts or len(prompts) < 1:
        return False, "Add at least one prompt to the prompt list."

    if not MULTIPROMPT_ENABLED:
        if not prompts[0] or prompts[0].prompt == "":
            return False, "Enter a prompt."

        if prompts[0] and prompts[0].prompt and len(prompts[0].prompt) > 500:
            return False, "Enter a prompt."

    return True, ""


# Individual panel sections are added by setting bl_parent_id
class PanelSection:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = DS_CATEGORY


class RenderOptionsPanelSection(PanelSection, Panel):

    bl_parent_id = DreamStudio3DPanel.bl_idname
    bl_label = "Blender Options"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ds_settings
        use_custom_res = not settings.use_render_resolution
        init_source = InitSource[settings.init_source]
        layout.prop(settings, "init_source")
        if init_source != InitSource.NONE:
            layout.prop(settings, "init_strength")

        if DreamStateOperator.render_state == RenderState.ONBOARDING:
            return

        layout.prop(settings, "re_render")
        layout.prop(settings, "use_render_resolution")
        image_size_row = layout.row()
        image_size_row.enabled = use_custom_res
        image_size_row.prop(settings, "init_image_height", text="Height")
        image_size_row.prop(settings, "init_image_width", text="Width")

        render_output_location_row(layout, settings)


class AnimationOptionsPanelSection(PanelSection, Panel):

    bl_parent_id = DreamStudio3DPanel.bl_idname
    bl_label = "Animation Options"
    bl_options = {"DEFAULT_CLOSED"}


class AdvancedOptionsPanelSection(PanelSection, Panel):

    bl_parent_id = DreamStudio3DPanel.bl_idname
    bl_label = "DreamStudio Options"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ds_settings
        use_recommended = settings.use_recommended_settings

        if DreamStateOperator.render_state == RenderState.ONBOARDING:
            return

        layout.prop(settings, "cfg_scale", text="Prompt Strength")

        seed_row = layout.row()
        seed_row.prop(settings, "use_custom_seed")
        seed_input_row = seed_row.row()
        seed_input_row.enabled = settings.use_custom_seed
        seed_input_row.prop(settings, "seed")

        layout.prop(
            settings,
            "use_recommended_settings",
        )

        steps_row = layout.row()
        steps_row.prop(settings, "steps", text="Steps")
        steps_row.enabled = not use_recommended

        # Disallow interpolating these params
        engine_selection_row = layout.row()
        engine_selection_row.use_property_split = False
        engine_selection_row.use_property_decorate = False
        engine_selection_row.prop(settings, "generation_engine")
        engine_selection_row.enabled = not use_recommended
        engine_selection_row.scale_x = 0.5
        engine_selection_row.prop(settings, "use_clip_guidance")

        sampler_row = layout.row()
        sampler_row.prop(settings, "sampler")
        sampler_row.enabled = not use_recommended
