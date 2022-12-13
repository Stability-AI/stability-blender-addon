import datetime
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
from threading import Thread
import time
import webbrowser

from .data import (
    RENDER_PREFIX,
    TrackingEvent,
    UIContext,
    InitSource,
    OutputLocation,
    PauseReason,
    RenderState,
    copy_image,
    format_rest_args,
    get_init_image_dimensions,
    get_preferences,
    initialize_sentry,
    log_sentry_event,
)
from .dependencies import install_dependencies, check_dependencies_installed
from .requests import log_analytics_event, render_img2img, render_text2img
import multiprocessing as mp
import threading
import glob
import platform
import tempfile
import time


class DS_ContinueRenderOperator(Operator):
    """Continue Baking"""

    bl_idname = "dreamstudio.continue_render"
    bl_label = "Continue"

    def execute(self, context):
        DreamStateOperator.render_state = RenderState.DIFFUSING
        return {"FINISHED"}


class DS_CancelRenderOperator(Operator):
    """Cancel diffusion process"""

    bl_idname = "dreamstudio.cancel_render"
    bl_label = "Cancel"

    def execute(self, context):
        log_sentry_event(TrackingEvent.CANCEL_GENERATION)
        log_analytics_event(TrackingEvent.CANCEL_GENERATION)
        DreamStateOperator.render_state = RenderState.IDLE
        DreamStateOperator.generator_thread.running = False
        DreamStateOperator.reset_render_state()
        return {"FINISHED"}


class DS_SceneRenderFrameOperator(Operator):
    """Render the current frame, then send to Stability SDK for diffusion"""

    bl_idname = "dreamstudio.render_frame"
    bl_label = "Cancel"

    def execute(self, context):
        DreamStateOperator.ui_context = UIContext.SCENE_VIEW_FRAME
        DreamStateOperator.render_state = RenderState.RENDERING
        DreamStateOperator.render_start_time = time.time()
        bpy.ops.dreamstudio.dream_render_operator()
        return {"FINISHED"}


class DS_SceneRenderAnimationOperator(Operator):
    """Render an entire animation as a sequence of frames, then send to Stability SDK for diffusion"""

    bl_idname = "dreamstudio.render_animation"
    bl_label = "Cancel"

    def execute(self, context):
        DreamStateOperator.ui_context = UIContext.SCENE_VIEW_ANIMATION
        DreamStateOperator.render_state = RenderState.RENDERING
        DreamStateOperator.render_start_time = time.time()
        bpy.ops.dreamstudio.dream_render_operator()
        return {"FINISHED"}


class GeneratorWorker(Thread):
    def __init__(self, scene, context, gen_type=UIContext.SCENE_VIEW_ANIMATION):
        self.scene = scene
        self.context = context
        self.ui_context: UIContext = gen_type
        self.running: bool = True
        self.init_source: InitSource = InitSource[scene.ds_settings.init_source]
        Thread.__init__(self)

    def run(self):
        try:
            self.generate()
        except Exception as e:
            if check_dependencies_installed():
                from sentry_sdk import capture_exception

                capture_exception(e)
            DreamStateOperator.render_state = RenderState.IDLE
            DreamStateOperator.reset_render_state()
            raise e

    def generate(self):
        settings = self.scene.ds_settings
        scene = self.scene
        args = format_rest_args(settings, scene.prompt_list)

        DreamStateOperator.render_state = RenderState.DIFFUSING
        output_file_path = os.path.join(DreamStateOperator.results_dir, f"result.png")
        DreamStateOperator.diffusion_output_path = output_file_path
        init_image_width, init_image_height = get_init_image_dimensions(settings, scene)

        # text2img mode
        if self.init_source == InitSource.NONE:
            DreamStateOperator.render_state = RenderState.DIFFUSING
            status, reason = render_text2img(
                DreamStateOperator.diffusion_output_path, args
            )
            DreamStateOperator.render_state = RenderState.FINISHED
            return

        if self.ui_context == UIContext.IMAGE_EDITOR:
            DreamStateOperator.render_state = RenderState.DIFFUSING
            if not os.path.exists(DreamStateOperator.init_img_path):
                DreamStateOperator.reset_render_state()
                raise Exception(
                    "No image found at {}. Does the texture exist?".format(
                        DreamStateOperator.init_img_path
                    )
                )
            status, reason = render_img2img(
                DreamStateOperator.init_img_path, output_file_path, args
            )
            if status != 200:
                raise Exception("Error generating image: {} {}".format(status, reason))
            DreamStateOperator.render_state = RenderState.FINISHED
            return

        render_file_type = scene.render.image_settings.file_format
        if render_file_type == "JPEG":
            render_file_type = "JPG"

        # img2img mode
        if self.ui_context == UIContext.SCENE_VIEW_FRAME:
            DreamStateOperator.diffusion_output_path = output_file_path
            if not os.path.exists(DreamStateOperator.init_img_path):
                raise Exception(
                    "No image found at {}. Was the scene rendered, or is re-render disabled?".format(
                        DreamStateOperator.init_img_path
                    )
                )
            status, reason = render_img2img(
                DreamStateOperator.init_img_path, output_file_path, args
            )
            if status != 200:
                raise Exception("Error generating image: {} {}".format(status, reason))
        elif DreamStateOperator.ui_context == UIContext.SCENE_VIEW_ANIMATION:
            frames_glob = os.path.join(
                DreamStateOperator.output_dir,
                "{}*.{}".format(RENDER_PREFIX, render_file_type.lower()),
            )
            rendered_frame_image_paths = glob.glob(frames_glob)
            rendered_frame_image_paths = list(sorted(rendered_frame_image_paths))
            if len(rendered_frame_image_paths) == 0:
                raise Exception(
                    "No rendered frames found. Please render the scene first."
                )
            end_frame = len(rendered_frame_image_paths)
            DreamStateOperator.total_frame_count = end_frame
            for i, frame_img_file in enumerate(rendered_frame_image_paths[:end_frame]):
                print("about to render frame", i, self.running)
                if (
                    not self.running
                    or DreamStateOperator.render_state == RenderState.CANCELLED
                ):
                    break
                scene.frame_set(i + 1)
                DreamStateOperator.render_start_time = time.time()
                args = format_rest_args(settings, scene.prompt_list)
                output_file_path = os.path.join(
                    DreamStateOperator.results_dir, f"result_{i}.png"
                )
                rendered_image = bpy.data.images.load(frame_img_file)
                rendered_image.scale(init_image_width, init_image_height)
                DreamStateOperator.current_frame_idx = i + 1
                print(
                    "about to render frame - render state:",
                    DreamStateOperator.render_state,
                )
                # We need to actually set Blender to a certain frame to evaluate all the keyframe values for that frame.
                status, reason = render_img2img(frame_img_file, output_file_path, args)
                print("rendered frame", i, status, reason, output_file_path)
                if status != 200:
                    raise Exception(
                        "Error generating image: {} {}".format(status, reason)
                    )
            scene.frame_set(0)

        DreamStateOperator.render_state = RenderState.FINISHED


# Sets up the init image / animation, as well as setting all DreamStateOperator state that is passed to
# the generation thread.
class DreamRenderOperator(Operator):
    bl_idname = "dreamstudio.dream_render_operator"
    bl_label = "Dream!"

    def modal(self, context, event):

        settings = context.scene.ds_settings
        output_location = OutputLocation[settings.output_location]
        ui_context = DreamStateOperator.ui_context

        if DreamStateOperator.render_start_time:
            settings.current_time = time.time() - DreamStateOperator.render_start_time

        if DreamStateOperator.render_state == RenderState.CANCELLED:
            DreamStateOperator.render_state = RenderState.IDLE
            return {"FINISHED"}

        if DreamStateOperator.render_state == RenderState.FINISHED:
            image_tex_area = None
            for area in bpy.context.screen.areas:
                if area.type == "IMAGE_EDITOR":
                    image_tex_area = area
            if (
                output_location
                in (
                    OutputLocation.NEW_TEXTURE,
                    OutputLocation.CURRENT_TEXTURE,
                )
                and ui_context != UIContext.SCENE_VIEW_ANIMATION
            ):
                rendered_image = bpy.data.images.load(
                    DreamStateOperator.diffusion_output_path
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
                output_location == OutputLocation.FILE_SYSTEM
                or ui_context == UIContext.SCENE_VIEW_ANIMATION
            ):
                if os.name == "nt":
                    os.startfile(DreamStateOperator.results_dir)
                else:
                    os.system("open " + DreamStateOperator.results_dir)
            DreamStateOperator.render_state = RenderState.IDLE

        if DreamStateOperator.render_state == RenderState.IDLE:
            return {"FINISHED"}

        def confirm_cancel(self, context):
            layout = self.layout
            layout.operator(DS_ContinueRenderOperator.bl_idname)
            layout.operator(DS_CancelRenderOperator.bl_idname)

        if DreamStateOperator.render_state == RenderState.SHOULD_PAUSE:
            context.window_manager.popup_menu(
                confirm_cancel, title="Cancel generation?", icon="X"
            )
            return {"PASS_THROUGH"}

        if event.type == "ESC":
            DreamStateOperator.render_state = RenderState.PAUSED
            return {"PASS_THROUGH"}

        return {"PASS_THROUGH"}

    def execute(self, context):
        wm = context.window_manager
        settings = context.scene.ds_settings
        re_render, init_source = (
            settings.re_render,
            InitSource[settings.init_source],
        )
        scene = bpy.context.scene
        ui_context = DreamStateOperator.ui_context
        if context.area.type == "IMAGE_EDITOR":
            ui_context = UIContext.IMAGE_EDITOR
        output_dir, results_dir = setup_render_directories(clear=re_render)
        render_anim = ui_context == UIContext.SCENE_VIEW_ANIMATION
        DreamStateOperator.output_dir = output_dir
        DreamStateOperator.results_dir = results_dir
        if render_anim:
            DreamStateOperator.init_img_path = os.path.join(
                DreamStateOperator.output_dir, "render_"
            )
        else:
            DreamStateOperator.init_img_path = os.path.join(
                DreamStateOperator.output_dir, "init.png"
            )
        init_image_width, init_image_height = get_init_image_dimensions(settings, scene)

        # If we are in the image editor, we need to save the image to a temporary file to use for init
        if (
            ui_context == UIContext.IMAGE_EDITOR
            and init_source == InitSource.CURRENT_TEXTURE
        ):
            img = context.space_data.image
            if not img:
                raise Exception("No image selected")
            init_image = copy_image(img)
            init_image.scale(init_image_width, init_image_height)
            init_image.save_render(DreamStateOperator.init_img_path)

        # We only support rendering from the render in the 3D view
        if (
            ui_context == UIContext.SCENE_VIEW_ANIMATION
            or ui_context == UIContext.SCENE_VIEW_FRAME
        ):
            init_source = InitSource.SCENE_RENDER

        # Render 3D view
        if init_source == InitSource.SCENE_RENDER and (
            (
                ui_context
                in (UIContext.SCENE_VIEW_ANIMATION, UIContext.SCENE_VIEW_FRAME)
                and re_render
            )
            or (ui_context == UIContext.IMAGE_EDITOR)
        ):
            user_filepath = scene.render.filepath
            scene.render.filepath = DreamStateOperator.init_img_path

            render_file_type = scene.render.image_settings.file_format

            if render_file_type not in SUPPORTED_RENDER_FILE_TYPES:
                raise Exception(
                    f"Unsupported render file type: {render_file_type}. Supported types: {SUPPORTED_RENDER_FILE_TYPES}"
                )

            tmp_w, tmp_h = scene.render.resolution_x, scene.render.resolution_y
            scene.render.resolution_x = init_image_width
            scene.render.resolution_y = init_image_height
            res = bpy.ops.render.render(write_still=True, animation=render_anim)
            scene.render.resolution_x = tmp_w
            scene.render.resolution_y = tmp_h

            scene.render.filepath = user_filepath
            if res != {"FINISHED"}:
                raise Exception("Failed to render: {}".format(res))

        DreamStateOperator.ui_context = ui_context
        DreamStateOperator.generator_thread = GeneratorWorker(
            scene, context, ui_context
        )
        DreamStateOperator.generator_thread.start()

        wm.modal_handler_add(self)

        return {"RUNNING_MODAL"}


# State that is held during runtime, that is not stored as user modified properties.
# Read within the generation thread, and written to by the main thread.
class DreamStateOperator(Operator):
    bl_idname = "object.dream_operator"
    bl_label = "Dream"
    bl_options = {"REGISTER"}

    ui_context = UIContext.SCENE_VIEW_ANIMATION
    render_state = RenderState.IDLE
    pause_reason = PauseReason.NONE
    current_frame_idx = 0
    total_frame_count = 0
    generator_thread: Thread = None
    diffusion_output_path = None
    init_img_path = None
    output_dir = None
    results_dir = None
    render_start_time: float = None

    sentry_initialized = False

    # Cancel any in-progress render and reset the addon state.
    def reset_render_state():
        self = DreamStateOperator
        self.pause_reason = PauseReason.NONE
        self.cancel_rendering = False
        self.current_frame_idx = 0
        self.render_start_time = None
        if self.generator_thread:
            try:
                self.generator_thread.running = False
                self.generator_thread.join(1)
            except Exception as e:
                print(e)


# Create and clear render directories. This function should get all filesystem info for rendering,
# as well as any platform specific info.
def setup_render_directories(clear=False):
    output_dir = os.path.join(tempfile.gettempdir(), "dreamstudio")
    results_dir = os.path.join(output_dir, "results")
    for dir in [output_dir, results_dir]:
        if not os.path.exists(dir):
            os.mkdir(dir)
        elif clear:
            files = glob.glob(f"{dir}/*")
            for f in files:
                if not os.path.isdir(f):
                    os.remove(f)
    return output_dir, results_dir


SUPPORTED_RENDER_FILE_TYPES = {"PNG", "JPEG"}


class DS_OpenWebViewOperator(Operator):
    bl_idname = "dreamstudio.open_webview"
    bl_label = "Open Web View"

    url = None

    def execute(self, context):
        log_sentry_event(TrackingEvent.OPEN_WEB_URL)
        log_analytics_event(TrackingEvent.OPEN_WEB_URL)
        webbrowser.open(self.url)
        return {"FINISHED"}


class DS_GetAPIKeyOperator(DS_OpenWebViewOperator, Operator):
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


class DS_FinishOnboardingOperator(Operator):
    """Get started with Dream Studio"""

    bl_idname = "dreamstudio.finish_onboarding"
    bl_label = "Install"

    def execute(self, context):
        prefs = get_preferences()
        if prefs.record_analytics:
            if not check_dependencies_installed():
                install_dependencies()
            initialize_sentry()
        DreamStateOperator.sentry_initialized = True
        DreamStateOperator.render_state = RenderState.IDLE
        return {"FINISHED"}
