from enum import Enum
import bpy



RENDER_PREFIX = "render_"

# Return a dict to pass to the REST API.
def format_args_dict(settings, prompt_list_items):
    prompt_list = [(p.prompt, p.strength) for p in prompt_list_items]
    preferences = bpy.context.preferences.addons[__package__].preferences
    return {
        'api_key': preferences.api_key,
        'base_url': preferences.base_url,
        'prompts': prompt_list,
        'guidance_strength': settings.guidance_strength,
        'init_strength': settings.init_strength,
        'cfg_scale': settings.cfg_scale,
        'sampler': settings.sampler,
        'clip_guidance_preset': settings.clip_guidance_preset,
        'steps': settings.steps,
        'seed': settings.seed,
    }

# Main state for the addon. Should be thought of as a linear single path - except for pausing / cancelling.
class RenderState(Enum):
    IDLE = 0
    # Rendering or copying the init image
    RENDERING = 1
    # Running the diffusion thread
    DIFFUSING = 2
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
    (InitSource.CURRENT_TEXTURE.name, "Current Texture", "", InitSource.CURRENT_TEXTURE.value),
    (InitSource.SCENE_RENDER.name, "Scene Render", "", InitSource.SCENE_RENDER.value),
]

# where to send the resulting texture
OUTPUT_LOCATIONS = [
    (OutputLocation.CURRENT_TEXTURE.name, "Current Texture", "", OutputLocation.CURRENT_TEXTURE.value),
    (OutputLocation.NEW_TEXTURE.name, "New Texture", "", OutputLocation.NEW_TEXTURE.value),
    (OutputLocation.FILE_SYSTEM.name, "File System", "", OutputLocation.FILE_SYSTEM.value),
]

# Which UI element are we operating from?
class UIContext(Enum):
    SCENE_VIEW_ANIMATION = 1
    SCENE_VIEW_FRAME = 2
    IMAGE_EDITOR = 3

# TODO we want to grab these from the REST API.

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

def enum_to_blender_enum(enum: Enum):
    return [(e.name, e.name, "", e.value) for e in enum]