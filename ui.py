from datetime import timedelta, datetime
from .requests import get_account_details
from . import addon_updater_ops
from bpy.types import Panel
import time
import os
from glob import glob
import bpy

from .prompt_list import render_prompt_list

from .data import (
    SUPPORTED_RENDER_FILE_TYPES,
    InitType,
    OutputDisplayLocation,
    RenderState,
    UIContext,
    ValidationState,
    get_anim_images,
    get_init_image_dimensions,
    get_init_type,
    get_preferences,
)
from .operators import (
    CancelRenderOperator,
    DS_OpenPresetsFileOperator,
    GetAPIKeyOperator,
    DS_LogIssueOperator,
    FinishOnboardingOperator,
    DS_OpenDocumentationOperator,
    OpenOutputFolderOperator,
    SceneRenderExistingOutputOperator,
    SceneRenderViewportOperator,
    UseRenderFolderOperator,
    StateOperator,
)


ADDON_CATEGORY = "Stability"
DS_REGION_TYPE = "UI"


class PanelSection3D:
    bl_space_type = "VIEW_3D"
    bl_region_type = DS_REGION_TYPE
    bl_category = ADDON_CATEGORY


class PanelSectionImageEditor:
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = DS_REGION_TYPE
    bl_category = ADDON_CATEGORY


def draw_in_progress_view(layout, ui_context: UIContext):
    init_type = get_init_type()
    state_text = (
        "Rendering..."
        if StateOperator.render_state == RenderState.RENDERING
        else "Diffusing...".format(StateOperator.current_frame_idx)
    )
    if StateOperator.render_start_time:
        state_text += " ({}s)".format(
            round(time.time() - StateOperator.render_start_time, 1)
        )
    if (
        init_type == InitType.ANIMATION
        and ui_context == UIContext.SCENE_VIEW
        and not StateOperator.rendering_from_viewport
    ):
        state_text += " (frame {} / {})".format(
            StateOperator.current_frame_idx, StateOperator.total_frame_count
        )
    layout.label(text=state_text)
    cancel_text = (
        "Cancel Render"
        if StateOperator.render_state == RenderState.RENDERING
        else "Cancel Diffusion"
    )
    layout.operator(CancelRenderOperator.bl_idname, text=cancel_text)
    return


def draw_onboard_view(layout):
    prefs = get_preferences()
    get_key_row = layout.row()
    get_key_row.label(text="Enter your API key to begin.")
    get_key_row.operator(GetAPIKeyOperator.bl_idname, text="Get Key", icon="URL")
    api_key_row = layout.row()
    api_key_row.use_property_split = False
    api_key_row.use_property_decorate = False
    api_key_row.prop(prefs, "api_key")

    record_toggle_row = layout.row()
    record_toggle_row.use_property_split = False
    record_toggle_row.prop(prefs, "record_analytics")

    get_started_row = layout.row()
    get_started_row.operator(
        FinishOnboardingOperator.bl_idname, text="Get Started", icon="CHECKBOX_HLT"
    )
    get_started_row.enabled = prefs.api_key != "" and len(prefs.api_key) > 30


def draw_links_row(layout):
    links_row = layout.row()
    links_row.operator(
        DS_OpenDocumentationOperator.bl_idname, text="Open Docs", icon="TEXT"
    )
    links_row.operator(DS_LogIssueOperator.bl_idname, text="Log Issue", icon="QUESTION")
    links_row.operator(
        DS_OpenPresetsFileOperator.bl_idname, text="Edit Presets", icon="PRESET"
    )


def draw_init_type(layout, settings):
    row = layout.row()
    row.use_property_split = False
    row.use_property_decorate = False
    row.prop(settings, "init_type")


def draw_output_location_row(layout, settings):
    output_location_row = layout.row()
    output_location_row.alignment = "EXPAND"
    output_location_row.use_property_split = False
    output_location_row.use_property_decorate = False
    output_location_row.prop(settings, "output_location")


def draw_account_details(layout, settings):
    prefs = get_preferences()
    if StateOperator.account and StateOperator.account.logged_in:
        account_row = layout.row()
        account_row.label(text="Logged in as: {}".format(StateOperator.account.email))
        account_row.label(
            text="Balance: {} credits".format(StateOperator.account.credits)
        )
    if not StateOperator.account:
        StateOperator.account = get_account_details(prefs.base_url, prefs.api_key)


# UI for the image editor panel.
class StabilityImageEditorPanel(PanelSectionImageEditor, Panel):
    bl_idname = "panel.stability_image_editor"
    bl_label = "Stability"
    # https://docs.blender.org/api/current/bpy_types_enum_items/space_type_items.html#rna-enum-space-type-items
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = ADDON_CATEGORY

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ds_settings
        scene = context.scene
        preferences = get_preferences()

        addon_updater_ops.update_notice_box_ui(self, context)

        if preferences and (not preferences.api_key or preferences.api_key == ""):
            StateOperator.render_state = RenderState.ONBOARDING

        if StateOperator.render_state == RenderState.ONBOARDING:
            draw_onboard_view(layout)
            return

        if StateOperator.render_state != RenderState.IDLE:
            draw_in_progress_view(layout, UIContext.IMAGE_EDITOR)
            return

        draw_account_details(layout, settings)
        render_prompt_list(layout, context)

        draw_dream_row(layout, settings, scene, UIContext.IMAGE_EDITOR)
        draw_links_row(layout)


# UI for the scene view panel.
class Stability3DPanel(Panel):
    bl_idname = "panel.stability_3D"
    bl_label = "Stability"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = ADDON_CATEGORY

    def draw(self, context):
        settings = context.scene.ds_settings
        scene = context.scene
        preferences = get_preferences()

        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = True

        addon_updater_ops.update_notice_box_ui(self, context)

        if preferences and (not preferences.api_key or preferences.api_key == ""):
            StateOperator.render_state = RenderState.ONBOARDING

        if StateOperator.render_state == RenderState.ONBOARDING:
            draw_onboard_view(layout)
            return

        if StateOperator.render_state != RenderState.IDLE:
            draw_in_progress_view(layout, UIContext.SCENE_VIEW)
            return

        draw_account_details(layout, settings)
        render_prompt_list(layout, context)
        draw_dream_row(layout, settings, scene, UIContext.SCENE_VIEW)


TITLES = {
    InitType.ANIMATION.value: "Dream (Animation)",
    InitType.TEXT.value: "Dream (Prompt Only)",
    InitType.TEXTURE.value: "Dream (Texture)",
}


def draw_dream_row(layout, settings, scene, ui_context: UIContext):
    dream_row = layout.row()
    dream_row.scale_y = 2.0
    valid = render_validation(layout, settings, scene, ui_context)
    if ui_context == UIContext.IMAGE_EDITOR:
        dream_row.operator(
            SceneRenderExistingOutputOperator.bl_idname, text="Dream (Image Editor)"
        )
        dream_row.enabled = valid == ValidationState.VALID
    else:
        viewport_col = dream_row.column()
        viewport_col.operator(
            SceneRenderViewportOperator.bl_idname, text="Dream (Viewport)"
        )
        viewport_col.enabled = valid in (
            ValidationState.VALID,
            ValidationState.RENDER_SETTINGS,
        )
        render_col = dream_row.column()
        init_type = get_init_type()
        render_col.operator(
            SceneRenderExistingOutputOperator.bl_idname, text=TITLES[init_type.value]
        )
        render_col.enabled = valid == ValidationState.VALID


# Validation messages should be no longer than 50 chars or so.
def validate_settings(
    settings, scene, ui_context: UIContext, init_type: InitType
) -> tuple[ValidationState, str]:
    width, height = get_init_image_dimensions(settings, scene)
    prompts = scene.prompt_list
    # cannot be > 1 megapixel
    init_type = get_init_type()
    if init_type != InitType.TEXT:
        if width * height > 1_000_000:
            return (
                ValidationState.RENDER_SETTINGS,
                "Init image size cannot be greater than 1 megapixel.",
            )

    if not prompts or len(prompts) < 1:
        return False, "Press 'Add' to add a prompt to the list."

    if init_type in (InitType.ANIMATION, InitType.TEXTURE):
        render_file_type = scene.render.image_settings.file_format
        if render_file_type not in SUPPORTED_RENDER_FILE_TYPES:
            return ValidationState.RENDER_SETTINGS, (
                f"Unsupported render file type: {render_file_type}. Supported types: {SUPPORTED_RENDER_FILE_TYPES}"
            )

    render_file_type = scene.render.image_settings.file_format
    if init_type == InitType.TEXTURE:
        if not settings.init_texture_ref:
            return (
                ValidationState.RENDER_SETTINGS,
                "Init texture is not set.",
            )

    if init_type == InitType.ANIMATION:

        init_img_paths, render_dir = get_anim_images()

        # filepath is a directory in this case
        if not os.path.isdir(render_dir):
            return (
                ValidationState.RENDER_SETTINGS,
                "Input directory does not exist.",
            )
        if len(init_img_paths) < 1:
            return (
                ValidationState.RENDER_SETTINGS,
                "No images found in input directory with the set file type.",
            )

    for p in prompts:
        if not p or p.prompt == "":
            return ValidationState.DS_SETTINGS, "One or more prompts is empty."

        if p and p.prompt and len(p.prompt) > 500:
            return ValidationState.DS_SETTINGS, "One of your prompts is too long!"

    return ValidationState.VALID, ""


def credit_estimate(settings, scene, init_type: InitType):
    width, height = get_init_image_dimensions(settings, scene)
    pixels = width * height
    steps = int(settings.steps)
    credit_estimate = (pixels - 169527) * steps / 30 * 2.16e-08
    if init_type == InitType.ANIMATION:
        credit_estimate *= len(get_anim_images()[0])
    return round(credit_estimate * 100, 2)


def render_validation(layout, settings, scene, ui_context: UIContext):
    init_type = get_init_type()
    valid_state, validation_msg = validate_settings(
        settings, scene, ui_context, init_type
    )
    if valid_state != ValidationState.VALID:
        layout.label(text=validation_msg, icon="ERROR")
    else:
        if init_type == InitType.VIEWPORT:
            layout.label(
                text="Ready! Rendering from viewport.",
                icon="CHECKMARK",
            )
        else:
            cost = credit_estimate(settings, scene, init_type)
            layout.label(text=f"Ready! Cost: {cost} credits.", icon="CHECKMARK")
    return valid_state


# Individual panel sections are added by setting bl_parent_id

# Blender requires that we register a different panel type for each UI section -
# so we need to register a panel type for each UI for both the 3D view and the image editor.


class RenderOptionsPanelSectionImageEditor(PanelSectionImageEditor, Panel):

    bl_parent_id = StabilityImageEditorPanel.bl_idname
    bl_label = "Texture Options"

    def draw(self, context):
        draw_render_options_panel(self, context, UIContext.IMAGE_EDITOR)


class RenderOptionsPanelSection3DEditor(PanelSection3D, Panel):

    bl_parent_id = Stability3DPanel.bl_idname
    bl_label = "Init Options"

    def draw(self, context):
        draw_render_options_panel(self, context, UIContext.SCENE_VIEW)


class AdvancedOptionsPanelSection3DEditor(PanelSection3D, Panel):

    bl_parent_id = Stability3DPanel.bl_idname
    bl_label = "Generation Options"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        draw_advanced_options_panel(self, context)


class AdvancedOptionsPanelSectionImageEditor(PanelSectionImageEditor, Panel):

    bl_parent_id = StabilityImageEditorPanel.bl_idname
    bl_label = "Input Options"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        draw_advanced_options_panel(self, context)


def draw_advanced_options_panel(self, context):
    layout = self.layout
    settings = context.scene.ds_settings
    use_recommended = settings.use_recommended_settings

    if StateOperator.render_state == RenderState.ONBOARDING:
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

    draw_links_row(layout)


def draw_render_options_panel(self, context, ui_context: UIContext):
    layout = self.layout
    settings = context.scene.ds_settings
    use_custom_res = not settings.use_render_resolution
    init_type = get_init_type()
    if StateOperator.render_state == RenderState.ONBOARDING:
        return

    draw_init_type(layout, settings)

    if init_type != InitType.TEXT:
        layout.prop(settings, "init_strength")

    if init_type == InitType.TEXTURE:
        layout.template_ID(
            settings, "init_texture_ref", open="image.open", new="image.new"
        )
        if (
            ui_context == UIContext.SCENE_VIEW
            and init_type == InitType.TEXTURE
            and not settings.init_texture_ref
        ):
            layout.label(
                text="Select 'Render Result' above to use a rendered frame. Render first!"
            )

    if init_type == InitType.ANIMATION:
        init_folder_row = layout.row()
        init_folder_row.prop(settings, "init_animation_folder_path")
        init_folder_row.operator(UseRenderFolderOperator.bl_idname)

    use_resolution_label = "Use Render Resolution"
    if ui_context == UIContext.IMAGE_EDITOR:
        use_resolution_label = "Use Texture Resolution"
    layout.prop(settings, "use_render_resolution", text=use_resolution_label)
    image_size_row = layout.row()
    image_size_row.enabled = use_custom_res
    image_size_row.prop(settings, "init_image_height", text="Height")
    image_size_row.prop(settings, "init_image_width", text="Width")

    output_location: OutputDisplayLocation = OutputDisplayLocation[
        settings.output_location
    ]
    draw_output_location_row(layout, settings)
    if output_location == OutputDisplayLocation.FILE_SYSTEM:
        layout.operator(OpenOutputFolderOperator.bl_idname, text="Open Output Folder")
