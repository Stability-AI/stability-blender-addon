from enum import Enum
from pathlib import Path
import shutil
import bpy
from dataclasses import dataclass
import ensurepip
import os
import subprocess
import sys
import platform


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


RENDER_PREFIX = "render_"


# Take current state of the scene and use it to format arguments for the REST API.
def format_rest_args(settings, prompt_list_items):
    prompt_list = [{"text": p.prompt, "weight": p.strength} for p in prompt_list_items]
    preferences = bpy.context.preferences.addons[__package__].preferences
    use_clip, sampler, steps = (
        settings.use_clip_guidance,
        settings.sampler,
        settings.steps,
    )
    if settings.use_recommended_settings:
        width, height = get_init_image_dimensions(settings, bpy.context.scene)
        recommended = get_optimal_engine_config(width, height)
        clip_preset, sampler, steps = (
            recommended.guidance_preset,
            recommended.sampler_clip if use_clip else recommended.sampler,
            recommended.steps,
        )
    return {
        "api_key": preferences.api_key,
        "base_url": preferences.base_url,
        "prompts": prompt_list,
        "guidance_strength": 0.05,
        "init_strength": settings.init_strength,
        "cfg_scale": settings.cfg_scale,
        "sampler": sampler,
        "clip_guidance_preset": clip_preset,
        "steps": steps,
        "seed": settings.seed,
    }


def get_init_image_dimensions(settings, scene):
    try:
        if settings.use_render_resolution:
            width, height = int(scene.render.resolution_x), int(
                scene.render.resolution_y
            )
        else:
            width, height = int(settings.init_image_width), int(
                settings.init_image_height
            )
    except ValueError:
        width, height = 512, 512
    return width, height


def copy_image(image):
    new_image = bpy.data.images.new(
        "dreamstudio_result",
        width=image.size[0],
        height=image.size[1],
    )
    new_image.pixels = image.pixels[:]
    return new_image


class APIType(Enum):
    REST = 1
    GRPC = 2


# Main state for the addon. Should be thought of as a linear single path - except for pausing / cancelling.
class RenderState(Enum):
    ONBOARDING = 0
    IDLE = 1
    # Rendering or copying the init image
    RENDERING = 2
    # Running the diffusion thread
    DIFFUSING = 3
    # About to pause
    SHOULD_PAUSE = 4
    # Paused due to displaying an option or dialog box
    PAUSED = 5
    CANCELLED = 6
    # generation is finished and we want to display the finished texture this frame
    FINISHED = 7


# Why are we pausing the render?
class PauseReason(Enum):
    NONE = 1
    CONFIRM_CANCEL = 2
    EXCEPTION = 3


# Where to grab the init image from.
class InitSource(Enum):
    NONE = 1
    SCENE_RENDER = 2
    CURRENT_TEXTURE = 3


# What to display to the user when generation is finished - either the file location, or the image in the texture view.
class OutputLocation(Enum):
    CURRENT_TEXTURE = 1
    NEW_TEXTURE = 2
    FILE_SYSTEM = 3


# Used to display the init source property in the UI
INIT_SOURCES = [
    (InitSource.NONE.name, "None", "", InitSource.NONE.value),
    (
        InitSource.CURRENT_TEXTURE.name,
        "Current Texture",
        "",
        InitSource.CURRENT_TEXTURE.value,
    ),
    (InitSource.SCENE_RENDER.name, "Scene Render", "", InitSource.SCENE_RENDER.value),
]

# where to send the resulting texture
OUTPUT_LOCATIONS = [
    (
        OutputLocation.NEW_TEXTURE.name,
        "New Texture",
        "",
        OutputLocation.NEW_TEXTURE.value,
    ),
    (
        OutputLocation.FILE_SYSTEM.name,
        "File System",
        "",
        OutputLocation.FILE_SYSTEM.value,
    ),
]

# Which UI element are we operating from?
class UIContext(Enum):
    SCENE_VIEW_ANIMATION = 1
    SCENE_VIEW_FRAME = 2
    SCENE_VIEW_VIDEO = 3
    IMAGE_EDITOR = 4


class Sampler(Enum):
    K_EULER = 1
    K_DPM_2 = 2
    K_LMS = 3
    K_DPMPP_2S_ANCESTRAL = 4
    K_DPMPP_2M = 5
    DDIM = 6
    K_EULER_ANCESTRAL = 7
    K_HEUN = 8
    K_DPM_2_ANCESTRAL = 9


class ClipGuidancePreset(Enum):
    NONE = 1
    SIMPLE = 2
    FAST_BLUE = 3
    FAST_GREEN = 4
    SLOW = 5
    SLOWER = 6
    SLOWEST = 7


class Engine(Enum):
    GENERATE_1_0 = 0
    GENERATE_1_5 = 1
    GENERATE_512_2_0 = 2
    GENERATE_768_2_0 = 3
    GENERATE_512_2_1 = 4
    GENERATE_768_2_1 = 5


engine_enum_to_name = {
    Engine.GENERATE_1_0: "stable-diffusion-v1",
    Engine.GENERATE_1_5: "stable-diffusion-v1-5",
    Engine.GENERATE_512_2_0: "stable-diffusion-512-v2-0",
    Engine.GENERATE_768_2_0: "stable-diffusion-768-v2-0",
    Engine.GENERATE_512_2_1: "stable-diffusion-512-v2-1",
    Engine.GENERATE_768_2_1: "stable-diffusion-768-v2-1",
}


# set of configurations with a sampler / engine config for each
# then have a method to get optimal sampler / engine config for a given resolution


class EngineConfig:
    engine: Engine
    sampler_clip: Sampler
    sampler_no_clip: Sampler
    guidance_preset: ClipGuidancePreset
    steps: int


class DefaultEngineConfig(EngineConfig):
    engine = Engine.GENERATE_1_5
    sampler_clip = Sampler.K_DPM_2_ANCESTRAL
    sampler_no_clip = Sampler.K_DPMPP_2M
    guidance_preset = ClipGuidancePreset.FAST_GREEN
    steps = 50


class HighResEngineConfig(EngineConfig):
    engine = Engine.GENERATE_768_2_1
    sampler_clip = Sampler.K_DPMPP_2S_ANCESTRAL
    sampler_no_clip = Sampler.K_DPMPP_2M
    guidance_preset = ClipGuidancePreset.FAST_BLUE
    steps = 30


def get_optimal_engine_config(width: int, height: int) -> EngineConfig:
    if width <= 512 and height <= 512:
        return DefaultEngineConfig()
    else:
        return HighResEngineConfig()


def enum_to_blender_enum(enum: Enum):
    return [(e.name, e.name, "", e.value) for e in enum]


def engine_to_blender_enum():
    options = []
    for engine in Engine.__members__.values():
        engine_name = engine_enum_to_name[engine]
        options.append((engine_name, engine_name, "", engine.value))
    return options


def get_image_size_options(self, context):
    opts = []
    for opt in range(384, 2048 + 64, 64):
        opts.append((str(opt), str(opt), "", opt))
    return opts


def install_dependencies():
    ensurepip.bootstrap()
    os.environ.pop("PIP_REQ_TRACKER", None)
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    env["GRPC_PYTHON_BUILD_WITH_CYTHON"] = "1"
    for dep_name in ("stability-sdk==0.3.0", "sentry-sdk", "Pillow"):
        res = subprocess.run(
            [sys.executable, "-m", "pip", "install", dep_name], env=env
        )
        print(res.stdout)


def check_dependencies_installed():
    try:
        import stability_sdk
        import sentry_sdk
        import PIL

        return True
    except ImportError:
        return False


class TrackingEvent(Enum):
    TEXT2IMG = 1
    IMG2IMG = 2
    CANCEL_GENERATION = 3
    OPEN_WEB_URL = 4


TRACKED_GENERATION_PARAMS = [
    "cfg_scale",
    "clip_guidance_preset",
    "width",
    "height",
    "sampler",
    "seed",
    "step_schedule_end",
    "step_schedule_start",
    "steps",
    "text_prompts",
]


# TODO track crashes, and exceptions as well
TRACKING_EVENTS = {
    TrackingEvent.TEXT2IMG: TRACKED_GENERATION_PARAMS,
    TrackingEvent.IMG2IMG: TRACKED_GENERATION_PARAMS,
    TrackingEvent.CANCEL_GENERATION: [],
}


def initialize_sentry():
    import sentry_sdk

    # TODO reduce this to 0.2 or 0.1 when we release
    sentry_sdk.init(
        dsn="https://a5cc2b7983c24638af48ee316d4a00da@o1345497.ingest.sentry.io/4504299695570944",
        traces_sample_rate=1.0,
        environment="testing",
    )
    sentry_sdk.set_context(
        "system",
        {
            "blender_version": bpy.app.version_string,
            "operating_system_version": platform.version(),
            "operating_system_name": platform.system(),
            "addon_version": bl_info["version"].__str__(),
        },
    )


def log_sentry_event(event: TrackingEvent):
    if not check_dependencies_installed():
        return
    from sentry_sdk import capture_message, add_breadcrumb

    capture_message(event.name, level="info")
    add_breadcrumb(message=event.name, level="info")


def check_video_dependencies_installed():
    try:
        from stability_sdk import client
        from stability_sdk.animation import AnimationArgs, Animator

        return True
    except ImportError:
        return False


def install_video_dependencies():
    path = Path("stability-sdk")
    if path.exists():
        shutil.rmtree(path)
        os.system("pip uninstall -y stability-sdk")
    os.system(
        "git clone -b anima.nb.20221207 --recurse-submodules https://github.com/Stability-AI/stability-sdk"
    )
    Path("./stability-sdk/src/stability_sdk/interfaces/__init__.py").touch()
    os.system("pip install ./stability-sdk")
    sys.path.append("stability-sdk/src/stability_sdk/interfaces/src/tensorizer"),
    sys.path.append(
        "stability-sdk/src/stability_sdk/interfaces/src/tensorizer/tensors"
    ),
