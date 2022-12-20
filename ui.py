from .requests import get_account_details
from . import addon_updater_ops
from bpy.types import Panel
import time
import os
from glob import glob

from .prompt_list import render_prompt_list

from .data import (
    SUPPORTED_RENDER_FILE_TYPES,
    InitType,
    RenderState,
    UIContext,
    ValidationState,
    get_anim_images,
    get_init_image_dimensions,
    get_init_type,
    get_preferences,
)
from .operators import (
    DS_CancelRenderOperator,
    DS_GetAPIKeyOperator,
    DS_LogIssueOperator,
    DS_FinishOnboardingOperator,
    DS_OpenDocumentationOperator,
    DS_OpenOutputFolderOperator,
    DS_SceneRenderExistingOutputOperator,
    DS_SceneRenderViewportOperator,
    DS_UseRenderFolderOperator,
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


def render_in_progress_view(layout, ui_context: UIContext):
    init_type = get_init_type()
    state_text = (
        "Rendering..."
        if DreamStateOperator.render_state == RenderState.RENDERING
        else "Diffusing...".format(DreamStateOperator.current_frame_idx)
    )
    if DreamStateOperator.render_start_time:
        state_text += " ({}s)".format(
            round(time.time() - DreamStateOperator.render_start_time, 1)
        )
    if init_type == InitType.ANIMATION and ui_context == UIContext.SCENE_VIEW and not DreamStateOperator.rendering_from_viewport:
        state_text += " (frame {} / {})".format(
            DreamStateOperator.current_frame_idx, DreamStateOperator.total_frame_count
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
    get_key_row.label(text="Enter your key first.")
    get_key_row.operator(DS_GetAPIKeyOperator.bl_idname, text="Get Key", icon="URL")
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
    get_started_row.enabled = prefs.api_key != "" and len(prefs.api_key) > 30


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

def render_account_details(layout, settings):
    prefs = get_preferences()
    if DreamStateOperator.account:
        account_row = layout.row()
        account_row.label(text="Logged in as: {}".format(DreamStateOperator.account.email))
        account_row.label(text="Balance: {} credits".format(DreamStateOperator.account.credits))
    if not DreamStateOperator.account or DreamStateOperator.last_account_check_time + 60 < time.time():
        DreamStateOperator.account = get_account_details(prefs.base_url, prefs.api_key)
        DreamStateOperator.last_account_check_time = time.time()

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
            render_in_progress_view(layout, UIContext.IMAGE_EDITOR)
            return


        render_account_details(layout, settings)
        render_prompt_list(context.scene, layout)

        render_dream_row(layout, settings, scene, UIContext.IMAGE_EDITOR)
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
            render_in_progress_view(layout, UIContext.SCENE_VIEW)
            return

        render_account_details(layout, settings)
        render_prompt_list(scene, layout)

        render_dream_row(layout, settings, scene, UIContext.SCENE_VIEW)
        render_links_row(layout)

TITLES = {
    InitType.ANIMATION.value: "Dream (Animation)",
    InitType.TEXT.value: "Dream (Text)",
    InitType.TEXTURE.value: "Dream (Texture)",
}


def render_dream_row(layout, settings, scene, ui_context: UIContext):
    dream_row = layout.row()
    dream_row.scale_y = 2.0
    valid = render_validation(layout, settings, scene, ui_context)
    if ui_context == UIContext.IMAGE_EDITOR:
        dream_row.operator(
            DS_SceneRenderExistingOutputOperator.bl_idname, text="Dream (Image Editor)"
        )
        dream_row.enabled = valid == ValidationState.VALID
    else:
        viewport_col = dream_row.column()
        viewport_col.operator(
            DS_SceneRenderViewportOperator.bl_idname, text="Dream (Viewport)"
        )
        viewport_col.enabled = valid in (
            ValidationState.VALID,
            ValidationState.RENDER_SETTINGS,
        )
        render_col = dream_row.column()
        init_type = get_init_type()
        render_col.operator(
            DS_SceneRenderExistingOutputOperator.bl_idname, text=TITLES[init_type.value]
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
        return False, "Add at least one prompt to the prompt list."

    if init_type in (InitType.ANIMATION, InitType.TEXTURE):
        render_file_type = scene.render.image_settings.file_format
        if render_file_type not in SUPPORTED_RENDER_FILE_TYPES:
            return ValidationState.RENDER_SETTINGS, (
                f"Unsupported render file type: {render_file_type}. Supported types: {SUPPORTED_RENDER_FILE_TYPES}"
            )

    render_file_path = scene.render.filepath
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
                "Input directory is not valid.",
            )
        if len(init_img_paths) < 1:
            return (
                ValidationState.RENDER_SETTINGS,
                "No images found in input directory.",
            )

    for p in prompts:
        if not p or p.prompt == "":
            return ValidationState.DS_SETTINGS, "Enter a prompt."

        if p and p.prompt and len(p.prompt) > 500:
            return ValidationState.DS_SETTINGS, "Enter a prompt."

    return ValidationState.VALID, ""


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
            layout.label(text="Ready!", icon="CHECKMARK")
    return valid_state


# Individual panel sections are added by setting bl_parent_id

# Blender requires that we register a different panel type for each UI section -
# so we need to register a panel type for each UI for both the 3D view and the image editor.


class RenderOptionsPanelSectionImageEditor(PanelSectionImageEditor, Panel):

    bl_parent_id = DreamStudioImageEditorPanel.bl_idname
    bl_label = "Texture Options"

    def draw(self, context):
        render_render_options_panel(self, context, UIContext.IMAGE_EDITOR)


class RenderOptionsPanelSection3DEditor(PanelSection3D, Panel):

    bl_parent_id = DreamStudio3DPanel.bl_idname
    bl_label = "Render Options"

    def draw(self, context):
        render_render_options_panel(self, context, UIContext.SCENE_VIEW)


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


def render_render_options_panel(self, context, ui_context: UIContext):
    layout = self.layout
    settings = context.scene.ds_settings
    use_custom_res = not settings.use_render_resolution
    init_type = get_init_type()
    if DreamStateOperator.render_state == RenderState.ONBOARDING:
        return

    layout.prop(settings, "init_type")

    if init_type != InitType.TEXT:
        layout.prop(settings, "init_strength")

    if init_type == InitType.TEXTURE:
        layout.template_ID(
            settings, "init_texture_ref", open="image.open", new="image.new"
        )

    if init_type == InitType.ANIMATION:
        init_folder_row = layout.row()
        init_folder_row.prop(settings, "init_animation_folder_path")
        init_folder_row.operator(DS_UseRenderFolderOperator.bl_idname)

    use_resolution_label = "Use Render Resolution"
    if ui_context == UIContext.IMAGE_EDITOR:
        use_resolution_label = "Use Texture Resolution"
    layout.prop(settings, "use_render_resolution", text=use_resolution_label)
    image_size_row = layout.row()
    image_size_row.enabled = use_custom_res
    image_size_row.prop(settings, "init_image_height", text="Height")
    image_size_row.prop(settings, "init_image_width", text="Width")

    render_output_location_row(layout, settings)

    layout.operator(DS_OpenOutputFolderOperator.bl_idname, text="Open Output Folder")
