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

from .data import (
    RENDER_PREFIX,
    UIContext,
    InitSource,
    OutputLocation,
    PauseReason,
    RenderState,
    format_args_dict,
)
from .send_to_stability import render_img2img, render_text2img
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
    """Cancel Baking"""

    bl_idname = "dreamstudio.cancel_render"
    bl_label = "Cancel"

    def execute(self, context):
        DreamStateOperator.render_state = RenderState.IDLE
        DreamStateOperator.reset_render_state()
        DreamStateOperator.generator_thread.running = False
        return {"FINISHED"}


class DS_SceneRenderFrameOperator(Operator):
    """Render a single frame."""

    bl_idname = "dreamstudio.render_frame"
    bl_label = "Cancel"

    def execute(self, context):
        DreamStateOperator.ui_context = UIContext.SCENE_VIEW_FRAME
        DreamStateOperator.render_state = RenderState.RENDERING
        bpy.ops.dreamstudio.dream_render_operator()
        return {"FINISHED"}


class DS_SceneRenderAnimationOperator(Operator):
    """Render an entire animation."""

    bl_idname = "dreamstudio.render_animation"
    bl_label = "Cancel"

    def execute(self, context):
        DreamStateOperator.ui_context = UIContext.SCENE_VIEW_ANIMATION
        DreamStateOperator.render_state = RenderState.RENDERING
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
            if (
                self.ui_context == UIContext.SCENE_VIEW_ANIMATION
                or self.ui_context == UIContext.SCENE_VIEW_FRAME
            ):
                self.generate_from_3d_scene()
            elif self.ui_context == UIContext.IMAGE_EDITOR:
                self.generate_from_image_editor()
        except Exception as e:
            print(e)
            DreamStateOperator.render_state = RenderState.CANCELLED
            DreamStateOperator.reset_render_state()

    # TODO we can refactor these to be single-image and animation methods. Single image init code should be the same.
    def generate_from_image_editor(self):
        # Get current image context, save to disk, then use as init img
        settings = self.scene.ds_settings
        context = self.context
        args = format_args_dict(settings, context.scene.prompt_list)
        # if using active image, we want to just use the already saved img.
        DreamStateOperator.render_state = RenderState.DIFFUSING
        res_img_file_location = os.path.join(
            DreamStateOperator.results_dir, "result_0.png"
        )
        DreamStateOperator.diffusion_output_path = res_img_file_location
        DreamStateOperator.render_start_time = time.time()
        if self.init_source == InitSource.NONE:
            status, reason = render_text2img(res_img_file_location, args)
        else:
            status, reason = render_img2img(
                DreamStateOperator.init_img_path, res_img_file_location, args
            )
        if status != 200:
            raise Exception("Error generating image: {} {}".format(status, reason))
        DreamStateOperator.render_state = RenderState.FINISHED

    def generate_from_3d_scene(self):
        settings = self.scene.ds_settings
        context = self.context
        # scene = self.scene
        frame_limit: int = settings.frame_limit

        if self.init_source == InitSource.NONE:
            DreamStateOperator.render_state = RenderState.DIFFUSING
            status, reason = render_text2img(res_img_file_location, args)
            DreamStateOperator.render_state = RenderState.FINISHED
            return

        DreamStateOperator.render_state = RenderState.DIFFUSING
        DreamStateOperator.render_start_time = time.time()

        render_file_type = self.scene.render.image_settings.file_format
        if render_file_type == "JPEG":
            render_file_type = "JPG"
        frames_glob = os.path.join(
            DreamStateOperator.output_dir,
            "{}*.{}".format(RENDER_PREFIX, render_file_type.lower()),
        )
        rendered_frame_image_paths = glob.glob(frames_glob)
        rendered_frame_image_paths = list(sorted(rendered_frame_image_paths))

        if len(rendered_frame_image_paths) == 0:
            raise Exception("No rendered frames found. Please render the scene first.")

        res_img_file_location = os.path.join(
            DreamStateOperator.results_dir, "result.png"
        )
        DreamStateOperator.diffusion_output_path = res_img_file_location
        i = 0
        if self.ui_context == UIContext.SCENE_VIEW_FRAME:
            frame_img_file = rendered_frame_image_paths[0]
            args = format_args_dict(settings, context.scene.prompt_list)
            status, reason = render_img2img(frame_img_file, res_img_file_location, args)
            if status != 200:
                raise Exception("Error generating image: {} {}".format(status, reason))
        elif DreamStateOperator.ui_context == UIContext.SCENE_VIEW_ANIMATION:
            end_frame = min(
                frame_limit,
                len(rendered_frame_image_paths),
                len(rendered_frame_image_paths),
            )
            for i, frame_img_file in enumerate(rendered_frame_image_paths[:end_frame]):
                if not self.running:
                    return
                args = format_args_dict(settings, context.scene.prompt_list)
                res_img_file_location = os.path.join(
                    DreamStateOperator.results_dir, f"result_{i}.png"
                )
                DreamStateOperator.current_frame_idx = i + 1
                if DreamStateOperator.render_state == RenderState.CANCELLED:
                    break
                # We need to actually set Blender to a certain frame to evaluate all the keyframe values for that frame.
                bpy.context.scene.frame_set(i + 1)
                status, reason = render_img2img(
                    frame_img_file, res_img_file_location, args
                )
                print("rendered frame", i, status, reason, res_img_file_location)
                if status != 200:
                    raise Exception(
                        "Error generating image: {} {}".format(status, reason)
                    )
            bpy.context.scene.frame_set(0)

        DreamStateOperator.render_state = RenderState.FINISHED


# Sets up the init image / animation, as well as setting all DreamStateOperator state that is passed to
# the generation thread.
class DreamRenderOperator(Operator):
    bl_idname = "dreamstudio.dream_render_operator"
    bl_label = "Dream!"

    # Used to display the cancel modal
    _timer = None

    def modal(self, context, event):

        # print("modal", DreamStateOperator.render_state.name)

        settings = context.scene.ds_settings
        output_location = OutputLocation[settings.output_location]
        ui_context = DreamStateOperator.ui_context

        if DreamStateOperator.render_start_time is not None:
            settings.render_time = time.time() - DreamStateOperator.render_start_time

        if DreamStateOperator.render_state == RenderState.CANCELLED:
            DreamStateOperator.render_state = RenderState.IDLE
            return {"FINISHED"}

        if DreamStateOperator.render_state == RenderState.FINISHED:
            image_tex_area = None
            for area in bpy.context.screen.areas:
                if area.type == "IMAGE_EDITOR":
                    image_tex_area = area
            rendered_image = bpy.data.images.load(
                DreamStateOperator.diffusion_output_path
            )
            if output_location in (
                OutputLocation.NEW_TEXTURE,
                OutputLocation.CURRENT_TEXTURE,
            ):
                new_image = bpy.data.images.new(
                    "dreamstudio_result",
                    width=rendered_image.size[0],
                    height=rendered_image.size[1],
                )
                new_image.pixels = rendered_image.pixels[:]
                image_tex_area.spaces.active.image = new_image
                # TODO don't show if gen was cancelled or failed
                # TODO check this for edge cases
            elif (
                output_location == OutputLocation.FILE_SYSTEM
                and ui_context != UIContext.SCENE_VIEW_ANIMATION
            ):
                if os.name == "nt":
                    os.startfile(DreamStateOperator.results_dir)
                else:
                    os.system("open " + DreamStateOperator.results_dir)
            DreamStateOperator.render_state = RenderState.IDLE
            return {"FINISHED"}

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
        re_render, frame_limit, init_source = (
            settings.re_render,
            settings.frame_limit,
            InitSource[settings.init_source]
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

        # If we are in the image editor, we need to render the scene to a temporary file
        if ui_context == UIContext.IMAGE_EDITOR and init_source == InitSource.CURRENT_TEXTURE:
            img = context.space_data.image
            if not img:
                raise Exception("No image selected")
            img.save_render(DreamStateOperator.init_img_path)

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
            # TODO reset these params to the user's original values after render.
            tmp_frame_end = None
            scene.render.filepath = DreamStateOperator.init_img_path
            scene.render.resolution_x = 512
            scene.render.resolution_y = 512
            if frame_limit < scene.frame_end:
                tmp_frame_end = scene.frame_end
                scene.frame_end = frame_limit

            render_file_type = scene.render.image_settings.file_format

            if render_file_type not in SUPPORTED_RENDER_FILE_TYPES:
                raise Exception(
                    f"Unsupported render file type: {render_file_type}. Supported types: {SUPPORTED_RENDER_FILE_TYPES}"
                )

            res = bpy.ops.render.render(write_still=True, animation=render_anim)
            if tmp_frame_end:
                scene.frame_end = tmp_frame_end
            if res != {"FINISHED"}:
                raise Exception("Failed to render: {}".format(res))

        DreamStateOperator.ui_context = ui_context
        DreamStateOperator.generator_thread = GeneratorWorker(
            scene, context, ui_context
        )
        DreamStateOperator.generator_thread.start()

        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)

        return {"RUNNING_MODAL"}


# State that is held per render, that is not stored as user modified properties.
# Read within the generation thread, and written to by the main thread.
class DreamStateOperator(Operator):
    bl_idname = "object.dream_operator"
    bl_label = "Dream"
    bl_options = {"REGISTER"}

    ui_context = UIContext.SCENE_VIEW_ANIMATION
    render_state = RenderState.IDLE
    pause_reason = PauseReason.NONE
    current_frame_idx = 0
    generator_thread: Thread = None
    diffusion_output_path = None
    init_img_path = None
    output_dir = None
    results_dir = None
    render_start_time: float = None

    # Cancel any in-progress render and reset the addon state.
    def reset_render_state():
        self = DreamStateOperator
        self.pause_reason = PauseReason.NONE
        self.cancel_rendering = False
        self.current_frame_idx = 0
        self.render_start_time = None
        if self.generator_thread:
            self.generator_thread.running = False
            self.generator_thread.join(100)


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
