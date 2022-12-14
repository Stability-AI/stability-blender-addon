from datetime import datetime
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

from .data import (
    DSAccount,
    TrackingEvent,
    UIContext,
    InitType,
    OutputDisplayLocation,
    RenderState,
    copy_image,
    format_rest_args,
    get_anim_images,
    get_init_image_dimensions,
    get_init_type,
    get_preferences,
    get_settings,
    initialize_sentry,
    log_sentry_event,
    prompt_to_filename,
    get_presets_file_location,
)
from .dependencies import install_dependencies, check_dependencies_installed
from .requests import (
    get_account_details,
    log_analytics_event,
    render_img2img,
    render_text2img,
)
import multiprocessing as mp
import threading
from glob import glob
import platform
import tempfile
import time


def open_folder(dir: str):
    if platform.system() == "Windows":
        os.startfile(dir)
    elif platform.system() == "Darwin":
        subprocess.call(["open", dir])
    else:
        subprocess.call(["xdg-open", dir])


# Create and clear render directories. This function should get all filesystem info for rendering,
# as well as any platform specific info.
def setup_render_directories(clear_anim=True):
    addon_data_dir = os.path.join(tempfile.gettempdir(), "stability")
    rendered_dir = os.path.join(addon_data_dir, "rendered")
    generated_images_dir = os.path.join(addon_data_dir, "generated_images")
    generated_animation_dir = os.path.join(addon_data_dir, "generated_animation")
    for dir in [
        addon_data_dir,
        generated_images_dir,
        rendered_dir,
        generated_animation_dir,
    ]:
        if not os.path.exists(dir):
            os.mkdir(dir)
        if not os.access(dir, os.W_OK):
            raise Exception(
                f"Directory {dir} is not writable. Please check your Blender application permissions."
            )
        if dir == generated_animation_dir and clear_anim:
            for file in glob(os.path.join(dir, "*")):
                os.remove(file)
    return rendered_dir, generated_images_dir, generated_animation_dir


class ContinueRenderOperator(Operator):
    """Continue Baking"""

    bl_idname = "dreamstudio.continue_render"
    bl_label = "Continue"

    def execute(self, context):
        StateOperator.render_state = RenderState.DIFFUSING
        return {"FINISHED"}


class CancelRenderOperator(Operator):
    """Cancel diffusion process"""

    bl_idname = "dreamstudio.cancel_render"
    bl_label = "Cancel"

    def execute(self, context):
        log_sentry_event(TrackingEvent.CANCEL_GENERATION)
        log_analytics_event(TrackingEvent.CANCEL_GENERATION)
        StateOperator.reset_render_state()
        StateOperator.kill_render_thread()
        StateOperator.render_state = RenderState.IDLE
        return {"FINISHED"}


class SceneRenderViewportOperator(Operator):
    """Render the perspective from the current viewport, and send to Stability SDK for diffusion"""

    bl_idname = "dreamstudio.render_viewport"
    bl_label = "Cancel"

    def execute(self, context):
        StateOperator.ui_context = UIContext.SCENE_VIEW
        StateOperator.render_state = RenderState.RENDERING
        StateOperator.rendering_from_viewport = True
        StateOperator.render_start_time = time.time()
        bpy.ops.dreamstudio.dream_render_operator()
        return {"FINISHED"}


class SceneRenderExistingOutputOperator(Operator):
    """Send an existing set of rendered frames to Stability SDK for diffusion"""

    bl_idname = "dreamstudio.render_existing_output"
    bl_label = "Cancel"

    def execute(self, context):
        StateOperator.ui_context = UIContext.SCENE_VIEW
        StateOperator.render_state = RenderState.RENDERING
        StateOperator.render_start_time = time.time()
        bpy.ops.dreamstudio.dream_render_operator()
        return {"FINISHED"}


class GeneratorWorker(Thread):
    def __init__(
        self,
        scene,
        context,
        ui_context: UIContext,
        input_img_paths: List[str],
        output_img_directory: str,
        init_type: InitType,
    ):
        self.scene = scene
        self.context = context
        self.ui_context: UIContext = ui_context
        self.input_img_paths: List[str] = input_img_paths
        self.output_img_directory = output_img_directory
        self.running: bool = True
        self.init_type: InitType = init_type
        Thread.__init__(self)

    def run(self):
        try:
            self.generate()
        except Exception as e:
            StateOperator.render_state = RenderState.IDLE
            StateOperator.reset_render_state()
            StateOperator.kill_render_thread()
            if check_dependencies_installed():
                from sentry_sdk import capture_exception

                capture_exception(e)
            raise e

    # This sets up directories for render, and then renders individual frames
    def generate(self):
        settings = self.scene.ds_settings
        scene = self.scene
        args = format_rest_args(settings, scene.prompt_list)

        frame_start, frame_end = scene.frame_start, scene.frame_end
        scene_frame_length: int = frame_end - frame_start + 1

        StateOperator.render_state = RenderState.DIFFUSING
        output_file_path = os.path.join(self.output_img_directory, "result.png")
        init_image_width, init_image_height = get_init_image_dimensions(settings, scene)
        StateOperator.last_rendered_image_path = output_file_path

        # text2img mode
        if self.init_type == InitType.TEXT:
            StateOperator.render_state = RenderState.DIFFUSING
            status, reason = render_text2img(self.output_img_directory, args)
            StateOperator.render_state = RenderState.FINISHED
            if status != 200:
                raise Exception("Error generating image: {} {}".format(status, reason))
            return

        init_img_path = self.input_img_paths[0]
        # img2img mode - image editor, which can only generate from textures and text
        if self.init_type == InitType.TEXTURE:
            StateOperator.render_state = RenderState.DIFFUSING
            if not os.path.exists(init_img_path):
                raise Exception(
                    "No image found at {}. Does the texture exist?".format(
                        init_img_path
                    )
                )
            status, reason = render_img2img(init_img_path, output_file_path, args)
            if status != 200:
                raise Exception("Error generating image: {} {}".format(status, reason))
            StateOperator.render_state = RenderState.FINISHED
            return

        # img2img mode - 3D view
        if self.init_type == InitType.VIEWPORT:
            input_img_path = self.input_img_paths[0]
            if not os.path.exists(input_img_path):
                raise Exception(
                    "No image found at {}. Was the scene rendered, or is re-render disabled?".format(
                        init_img_path
                    )
                )
            status, reason = render_img2img(input_img_path, output_file_path, args)
            if status != 200:
                raise Exception("Error generating image: {} {}".format(status, reason))
        elif self.init_type == InitType.ANIMATION:
            rendered_frame_image_paths = list(sorted(self.input_img_paths))
            if len(rendered_frame_image_paths) == 0:
                raise Exception(
                    "No rendered frames found. Please render the scene first."
                )
            start_frame = max(0, frame_start - 1)
            end_frame = min(len(rendered_frame_image_paths), scene_frame_length)
            StateOperator.total_frame_count = end_frame
            for i, frame_img_file in enumerate(
                rendered_frame_image_paths[start_frame:end_frame]
            ):
                if (
                    not self.running
                    or StateOperator.render_state == RenderState.CANCELLED
                ):
                    return
                scene.frame_set(i + 1)
                StateOperator.render_start_time = time.time()
                args = format_rest_args(settings, scene.prompt_list)
                output_file_path = os.path.join(
                    self.output_img_directory, f"result_{i}.png"
                )
                rendered_image = bpy.data.images.load(frame_img_file)
                rendered_image.scale(init_image_width, init_image_height)
                StateOperator.current_frame_idx = i + 1
                # We need to actually set Blender to a certain frame to evaluate all the keyframe values for that frame.
                status, reason = render_img2img(frame_img_file, output_file_path, args)
                if status != 200:
                    raise Exception(
                        "Error generating image: {} {}".format(status, reason)
                    )
            scene.frame_set(0)

        StateOperator.rendering_from_viewport = False
        if self.running:
            StateOperator.render_state = RenderState.FINISHED


# Sets up the init image / animation, as well as setting all DreamStateOperator state that is passed to
# the generation thread.
class RenderOperator(Operator):
    bl_idname = "dreamstudio.dream_render_operator"
    bl_label = "Dream!"

    def modal(self, context, event):
        settings = context.scene.ds_settings
        output_location = OutputDisplayLocation[settings.output_location]
        ui_context = StateOperator.ui_context
        init_type = get_init_type()
        prefs = get_preferences()

        if StateOperator.render_start_time:
            settings.current_time = time.time() - StateOperator.render_start_time

        if StateOperator.render_state == RenderState.CANCELLED:
            StateOperator.render_state = RenderState.IDLE
            return {"FINISHED"}

        if StateOperator.render_state == RenderState.FINISHED:
            StateOperator.account = get_account_details(prefs.base_url, prefs.api_key)
            StateOperator.render_state = RenderState.IDLE
            image_tex_area = None
            for area in bpy.context.screen.areas:
                if area.type == "IMAGE_EDITOR":
                    image_tex_area = area
            if (
                output_location == OutputDisplayLocation.TEXTURE_VIEW
                and init_type != InitType.ANIMATION
            ):
                rendered_image = bpy.data.images.load(
                    StateOperator.last_rendered_image_path
                )
                if image_tex_area:
                    image_tex_area.spaces.active.image = copy_image(rendered_image)
                else:
                    # Create a new image editor area
                    bpy.ops.screen.userpref_show("INVOKE_DEFAULT")
                    image_tex_area = bpy.context.window_manager.windows[
                        -1
                    ].screen.areas[0]
                    image_tex_area.type = "IMAGE_EDITOR"
                    image_tex_area.spaces.active.image = copy_image(rendered_image)
            elif (
                output_location == OutputDisplayLocation.FILE_SYSTEM
                or ui_context == UIContext.SCENE_VIEW
            ):
                open_folder(StateOperator.generated_output_dir)

        if StateOperator.render_state == RenderState.IDLE:
            return {"FINISHED"}

        def confirm_cancel(self, context):
            layout = self.layout
            layout.operator(ContinueRenderOperator.bl_idname)
            layout.operator(CancelRenderOperator.bl_idname)

        if StateOperator.render_state == RenderState.SHOULD_PAUSE:
            context.window_manager.popup_menu(
                confirm_cancel, title="Cancel generation?", icon="X"
            )
            return {"PASS_THROUGH"}

        if event.type == "ESC":
            StateOperator.render_state = RenderState.PAUSED
            return {"PASS_THROUGH"}

        return {"PASS_THROUGH"}

    def execute(self, context):
        wm = context.window_manager
        settings = context.scene.ds_settings
        scene = bpy.context.scene
        ui_context = StateOperator.ui_context
        init_type = get_init_type()
        # Ensure there isn't an existing thread with a lock on the render directory.
        StateOperator.kill_render_thread()
        (
            rendered_dir,
            generated_images_dir,
            generated_animation_dir,
        ) = setup_render_directories()
        out_dir = (
            generated_animation_dir
            if init_type == InitType.ANIMATION
            else generated_images_dir
        )
        StateOperator.generated_output_dir = out_dir
        if context.area.type == "IMAGE_EDITOR":
            ui_context = UIContext.IMAGE_EDITOR

        init_img_path = os.path.join(rendered_dir, "init.png")

        init_image_width, init_image_height = get_init_image_dimensions(settings, scene)
        render_file_path = scene.render.filepath
        init_img_paths = []

        if StateOperator.rendering_from_viewport:
            init_type = InitType.VIEWPORT
        # If we are in the image editor, we need to save the image to a temporary file to use for init
        if init_type == InitType.TEXTURE:
            img = settings.init_texture_ref
            if not img:
                raise Exception("No init texture set")
            # workaround for render result not having pixels
            # https://blender.stackexchange.com/questions/2170/how-to-access-render-result-pixels-from-python-script
            if img.name == "Render Result":
                img = bpy.data.images["Render Result"]
                rr_path = os.path.join(rendered_dir, "render_result.png")
                img.save_render(rr_path, scene=None)
                init_image = bpy.data.images.load(rr_path)
                init_image.scale(init_image_width, init_image_height)
                init_image.save_render(init_img_path)
            else:
                init_image = copy_image(img)
                init_image.scale(init_image_width, init_image_height)
                init_image.save_render(init_img_path)
            init_img_paths = [init_img_path]

        # Render 3D view
        if init_type == InitType.VIEWPORT:

            scene.render.filepath = init_img_path
            workspace = bpy.context.workspace.name
            # tmp_show_overlay = bpy.data.screens[workspace].overlay.show_overlays
            # bpy.data.screens[workspace].overlay.show_overlays = False

            tmp_w, tmp_h = scene.render.resolution_x, scene.render.resolution_y
            scene.render.resolution_x = init_image_width
            scene.render.resolution_y = init_image_height
            res = bpy.ops.render.opengl(
                write_still=True, animation=False, view_context=True
            )
            scene.render.resolution_x = tmp_w
            scene.render.resolution_y = tmp_h
            # bpy.data.screens[workspace].overlay.show_overlays = tmp_show_overlay

            init_img_paths = [init_img_path]

            if res != {"FINISHED"}:
                raise Exception("Failed to render: {}".format(res))
        elif init_type == InitType.ANIMATION:
            init_img_paths, frame_path = get_anim_images()
        StateOperator.generator_thread = GeneratorWorker(
            scene,
            context,
            ui_context,
            input_img_paths=init_img_paths,
            output_img_directory=out_dir,
            init_type=init_type,
        )
        StateOperator.generator_thread.start()

        wm.modal_handler_add(self)

        return {"RUNNING_MODAL"}


# State that is held during runtime, that is not stored as user modified properties.
# Read within the generation thread, and written to by the main thread.
class StateOperator(Operator):
    bl_idname = "object.dream_operator"
    bl_label = "Dream"
    bl_options = {"REGISTER"}

    ui_context = UIContext.SCENE_VIEW
    render_state = RenderState.IDLE
    current_frame_idx = 0
    total_frame_count = 0
    generator_thread: Thread = None
    rendering_from_viewport = False
    # Where we put images that are generated after the diffusion step.
    # Either generated_images_dir or generation_animation_dir will be set.
    generated_output_dir = None
    # Where we put images that are rendered by the addon.
    rendered_images_dir = None
    # Where we put images that are generated by the addon.
    last_rendered_image_path = None
    render_start_time: float = None

    sentry_initialized = False

    account: DSAccount = None

    # Cancel any in-progress render and reset the addon state.
    def reset_render_state():
        self = StateOperator
        self.cancel_rendering = False
        self.current_frame_idx = 0
        self.render_start_time = None

    def kill_render_thread():
        self = StateOperator
        if self.generator_thread:
            try:
                self.generator_thread.running = False
                self.generator_thread.join(1)
            except Exception as e:
                print(e)


class DS_OpenWebViewOperator(Operator):
    bl_idname = "dreamstudio.open_webview"
    bl_label = "Open Web View"

    url = None

    def execute(self, context):
        webbrowser.open(self.url)
        return {"FINISHED"}


class DS_OpenPresetsFileOperator(Operator):
    bl_idname = "dreamstudio.open_presets_file"
    bl_label = "Edit Presets"

    def execute(self, context):
        csv_location = get_presets_file_location()
        open_folder(csv_location)
        return {"FINISHED"}


class OpenOutputFolderOperator(Operator):
    bl_idname = "dreamstudio.open_output_folder"
    bl_label = "Open Output Folder"

    def execute(self, context):
        (
            dreamstudio_dir,
            generated_images_dir,
            generated_animation_dir,
        ) = setup_render_directories(clear_anim=False)
        init_type = get_init_type()
        if init_type == InitType.ANIMATION:
            open_folder(generated_animation_dir)
        else:
            open_folder(generated_images_dir)
        return {"FINISHED"}


class UseRenderFolderOperator(Operator):
    """Use the current Output Path setting in Output Properties as the input folder"""

    bl_idname = "dreamstudio.set_render_folder"
    bl_label = "Use Render Folder"

    def execute(self, context):
        settings = get_settings()
        scene = context.scene
        abs_filepath = bpy.path.abspath(scene.render.filepath)
        if not os.path.isdir(abs_filepath):
            abs_filepath = os.path.dirname(abs_filepath)
        settings.init_animation_folder_path = abs_filepath
        return {"FINISHED"}


class GetAPIKeyOperator(DS_OpenWebViewOperator, Operator):
    """Open a link to the API key page in your web browser"""

    bl_idname = "dreamstudio.get_api_key"
    url = "https://beta.dreamstudio.ai/membership?tab=apiKeys"


class DS_OpenDocumentationOperator(DS_OpenWebViewOperator, Operator):
    """Open a link to the documentation page in your web browser"""

    bl_idname = "dreamstudio.open_documentation"
    url = "https://platform.stability.ai/"


# TODO find a better support link
class DS_LogIssueOperator(DS_OpenWebViewOperator, Operator):
    """Open a link to the support page in your web browser"""

    bl_idname = "dreamstudio.log_issue"
    url = "https://github.com/Stability-AI/stability-blender-addon/issues/new"


class FinishOnboardingOperator(Operator):
    """Get started with Dream Studio!"""

    bl_idname = "dreamstudio.finish_onboarding"
    bl_label = "Install"

    def execute(self, context):
        prefs = get_preferences()
        if prefs.record_analytics:
            if not check_dependencies_installed():
                install_dependencies()
            initialize_sentry()
        StateOperator.sentry_initialized = True
        StateOperator.render_state = RenderState.IDLE
        return {"FINISHED"}


class SelectFileOperator(bpy.types.Operator):
    bl_idname = "dreamstudio.select_file"
    bl_label = "Select a file"
    filepath = bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        print(self.filepath)
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


def get_render_texture():
    for tex in bpy.data.textures:
        if tex.type == "IMAGE" and tex.name == "Render Result":
            return tex
