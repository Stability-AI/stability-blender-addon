from . import addon_updater_ops
import bpy
from bpy.types import Panel
import time

from .prompt_list import MULTIPROMPT_ENABLED, render_prompt_list

from .data import (
    InitSource,
    RenderContext,
    RenderState,
    UIContext,
    check_dependencies_installed,
    get_init_image_dimensions,
    get_preferences,
)
from .operators import (
    DS_CancelRenderOperator,
    DS_GetAPIKeyOperator,
    DS_LogIssueOperator,
    DS_FinishOnboardingOperator,
    DS_OpenDocumentationOperator,
    DS_SceneRenderAnimationOperator,
    DS_SceneRenderFrameOperator,
    DreamRenderOperator,
    DreamStateOperator,
)


DS_CATEGORY = "DreamStudio"
DS_REGION_TYPE = "UI"


class PanelSection3D:
    bl_space_type = "VIEW_3D"
    bl_region_type = DS_REGION_TYPE
    bl_category = DS_CATEGORY


class PanelSectionImageEditor:
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = DS_REGION_TYPE
    bl_category = DS_CATEGORY


def render_in_progress_view(layout):
    state_text = (
        "Rendering..."
        if DreamStateOperator.render_state == RenderState.RENDERING
        else "Diffusing...".format(DreamStateOperator.current_frame_idx)
    )
    if DreamStateOperator.render_context == RenderContext.ANIMATION:
        state_text += " Frame {}/{}".format(
            DreamStateOperator.current_frame_idx, DreamStateOperator.total_frame_count
        )
    if DreamStateOperator.render_start_time:
        state_text += " ({}s)".format(
            round(time.time() - DreamStateOperator.render_start_time, 1)
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
    prefs = get_preferences()
    get_key_row = layout.row()
    get_key_row.label(text="Please enter your API key.")
    get_key_row.operator(
        DS_GetAPIKeyOperator.bl_idname, text="Account Page", icon="URL"
    )
    api_key_row = layout.row()
    api_key_row.use_property_split = False
    api_key_row.use_property_decorate = False
    api_key_row.prop(prefs, "api_key")

    record_toggle_row = layout.row()
    record_toggle_row.use_property_split = False
    record_toggle_row.prop(prefs, "record_analytics")

    get_started_row = layout.row()
    get_started_row.operator(
        DS_FinishOnboardingOperator.bl_idname, text="Get Started", icon="CHECKBOX_HLT"
    )
    get_started_row.enabled = prefs.api_key != ""


def render_links_row(layout):
    links_row = layout.row()
    links_row.operator(
        DS_OpenDocumentationOperator.bl_idname, text="Open Docs", icon="TEXT"
    )
    links_row.operator(DS_LogIssueOperator.bl_idname, text="Log Issue", icon="QUESTION")


def render_output_location_row(layout, settings):
    output_location_row = layout.row()
    output_location_row.alignment = "EXPAND"
    output_location_row.use_property_split = False
    output_location_row.use_property_decorate = False
    output_location_row.prop(settings, "output_location")


# UI for the image editor panel.
class DreamStudioImageEditorPanel(PanelSectionImageEditor, Panel):
    bl_idname = "panel.dreamstudio_image_editor"
    bl_label = "DreamStudio"
    # https://docs.blender.org/api/current/bpy_types_enum_items/space_type_items.html#rna-enum-space-type-items
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = DS_CATEGORY

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ds_settings
        scene = context.scene
        preferences = get_preferences()

        addon_updater_ops.update_notice_box_ui(self, context)

        if preferences and (not preferences.api_key or preferences.api_key == ""):
            DreamStateOperator.render_state = RenderState.ONBOARDING

        if DreamStateOperator.render_state == RenderState.ONBOARDING:
            render_onboard_view(layout)
            return

        if DreamStateOperator.render_state != RenderState.IDLE:
            render_in_progress_view(layout)
            return

        valid = render_validation(layout, settings, scene, UIContext.IMAGE_EDITOR)

        render_prompt_list(context.scene, layout)

        dream_row = layout.row()
        dream_row.operator(DreamRenderOperator.bl_idname, text="Dream (Texture)")
        dream_row.enabled = valid
        render_links_row(layout)


# UI for the scene view panel.
class DreamStudio3DPanel(Panel):
    bl_idname = "panel.dreamstudio"
    bl_label = "DreamStudio"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = DS_CATEGORY

    def draw(self, context):
        settings = context.scene.ds_settings
        scene = context.scene
        preferences = get_preferences()

        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = True

        addon_updater_ops.update_notice_box_ui(self, context)

        if preferences and (not preferences.api_key or preferences.api_key == ""):
            DreamStateOperator.render_state = RenderState.ONBOARDING

        if DreamStateOperator.render_state == RenderState.ONBOARDING:
            render_onboard_view(layout)
            return

        if DreamStateOperator.render_state != RenderState.IDLE:
            render_in_progress_view(layout)
            return

        valid = render_validation(layout, settings, scene, UIContext.SCENE_VIEW)
        render_prompt_list(scene, layout)

        row = layout.row()
        row.scale_y = 2.0
        row.operator(
            DS_SceneRenderAnimationOperator.bl_idname, text="Dream (Animation)"
        )
        row.operator(DS_SceneRenderFrameOperator.bl_idname, text="Dream (Frame)")
        row.enabled = valid
        render_links_row(layout)


# Validation messages should be no longer than 50 chars or so.
def validate_settings(
    settings, scene, ui_render_context: UIContext
) -> tuple[bool, str]:
    width, height = get_init_image_dimensions(settings, scene)
    prompts = scene.prompt_list
    # cannot be > 1 megapixel
    init_source = InitSource[settings.init_source]
    if init_source != InitSource.NONE:
        if (
            ui_render_context == UIContext.IMAGE_EDITOR
            and init_source == InitSource.SCENE_RENDER
        ):
            return False, "Rendering to image editor is not supported."
        if (
            ui_render_context == UIContext.SCENE_VIEW
            and init_source == InitSource.CURRENT_TEXTURE
        ):
            return False, "Rendering from image editor is not supported."
        if width * height > 1_000_000:
            return False, "Init image size cannot be greater than 1 megapixel."

        if not prompts or len(prompts) < 1:
            return False, "Add at least one prompt to the prompt list."

    if not prompts[0] or prompts[0].prompt == "":
        return False, "Enter a prompt."

    if prompts[0] and prompts[0].prompt and len(prompts[0].prompt) > 500:
        return False, "Enter a prompt."

    return True, ""


def render_validation(layout, settings, scene, ui_context: UIContext):
    re_render: bool = settings.re_render
    init_source = InitSource[settings.init_source]
    valid, validation_msg = validate_settings(settings, scene, ui_context)
    if not valid:
        layout.label(text=validation_msg, icon="ERROR")
    else:
        if re_render and init_source == InitSource.SCENE_RENDER:
            layout.label(
                text="Ready! Scene will render first, this will lock Blender.",
                icon="CHECKMARK",
            )
        else:
            layout.label(text="Ready!", icon="CHECKMARK")
    return valid


# Individual panel sections are added by setting bl_parent_id

# Blender requires that we register a different panel type for each UI section -
# so we need to register a panel type for each UI for both the 3D view and the image editor.


class RenderOptionsPanelSectionImageEditor(PanelSectionImageEditor, Panel):

    bl_parent_id = DreamStudioImageEditorPanel.bl_idname
    bl_label = "Texture Options"

    def draw(self, context):
        draw_render_options_panel(self, context)


class RenderOptionsPanelSection3DEditor(PanelSection3D, Panel):

    bl_parent_id = DreamStudio3DPanel.bl_idname
    bl_label = "3D View Options"

    def draw(self, context):
        draw_render_options_panel(self, context)


class AdvancedOptionsPanelSection3DEditor(PanelSection3D, Panel):

    bl_parent_id = DreamStudio3DPanel.bl_idname
    bl_label = "DreamStudio Options"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        draw_advanced_options_panel(self, context)


class AdvancedOptionsPanelSectionImageEditor(PanelSectionImageEditor, Panel):

    bl_parent_id = DreamStudioImageEditorPanel.bl_idname
    bl_label = "DreamStudio Options"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        draw_advanced_options_panel(self, context)


def draw_advanced_options_panel(self, context):
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


def draw_render_options_panel(self, context):
    layout = self.layout
    settings = context.scene.ds_settings
    use_custom_res = not settings.use_render_resolution
    init_source = InitSource[settings.init_source]
    if DreamStateOperator.render_state == RenderState.ONBOARDING:
        return
    layout.prop(settings, "init_source")
    if init_source != InitSource.NONE:
        layout.prop(settings, "init_strength")

    layout.prop(settings, "re_render")
    layout.prop(settings, "use_render_resolution")
    image_size_row = layout.row()
    image_size_row.enabled = use_custom_res
    image_size_row.prop(settings, "init_image_height", text="Height")
    image_size_row.prop(settings, "init_image_width", text="Width")

    render_output_location_row(layout, settings)
