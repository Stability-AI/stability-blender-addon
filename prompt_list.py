import bpy
from bpy.props import StringProperty, IntProperty, CollectionProperty, FloatProperty, EnumProperty
from bpy.types import PropertyGroup, UIList, Operator, Panel, UILayout
import bpy.utils.previews
import os
from bpy.types import WindowManager

MULTIPROMPT_ENABLED = True


class PromptListItem(PropertyGroup):
    prompt: StringProperty(name="Prompt", default="")
    strength: FloatProperty(name="Strength", default=1, min=-1, max=1)


class PromptListUIItem(UILayout):
    def draw_item(
        self, context, layout, data, item, icon, active_data, active_propname
    ):
        prompt_data = item
        layout.prop(prompt_data, "prompt")
        layout.prop(prompt_data, "strength")


class PromptList_NewItem(Operator):
    """Add a new item to the list."""

    bl_idname = "prompt_list.new_item"
    bl_label = "Add"

    def execute(self, context):
        context.scene.prompt_list.add()

        return {"FINISHED"}


class PromptList_RemoveItem(Operator):
    """Remove an item from the list."""

    bl_idname = "prompt_list.remove_item"
    bl_label = "Remove a prompt"

    index: IntProperty()

    def execute(self, context):
        context.scene.prompt_list.remove(self.index)

        return {"FINISHED"}


class PromptList_AddPreset(Operator):
    """Add a new item to the list."""

    bl_idname = "prompt_list.add_preset"
    bl_label = "Preset"

    def execute(self, context):
        new_prompt = context.scene.prompt_list.add()
        new_prompt.prompt = "Close up, 8k, high detail, photorealistic, proper shading, stock photo"

        return {"FINISHED"}


def render_prompt_list(layout, context):
    scene = context.scene

    title_row = layout.row()
    wm = context.window_manager
    if MULTIPROMPT_ENABLED:
        title_row.label(text="Prompts")
        title_row.operator(PromptList_NewItem.bl_idname, icon="ADD")
        title_row.prop(wm, "style_presets")


    for i in range(len(scene.prompt_list)):
        item = scene.prompt_list[i]

        prompt_row = layout.row(align=True)

        prompt_row.alignment = "EXPAND"
        prompt_row.use_property_split = False
        prompt_text_row = prompt_row.row(align=True)
        prompt_text_row.prop(item, "prompt")
        prompt_text_row.scale_x = 1.5

        if MULTIPROMPT_ENABLED:
            strength_row = prompt_row.row(align=True)
            strength_row.scale_x = 0.5
            strength_row.prop(item, "strength", text="")

            delete_row = prompt_row.row(align=True)
            delete_row.scale_x = 1
            delete_op = delete_row.operator(
                "prompt_list.remove_item", text="", icon="REMOVE"
            )
            delete_op.index = i


preview_collections = {}

PRESETS = [
    ("Fantasy", "fantasy.png", "Fantasy art, epic lighting from above, inside a rpg game, bottom angle, epic fantasy card game art, epic character portrait, glowing and epic, full art illustration, landscape illustration, celtic fantasy art, neon fog"),
    ("Comic", "comic.png", "comic book cover, reddit, antipodeans, leading lines, preparing to fight, trending on imagestation, son, full device, some orange and blue, rear facing, netting, marvel, serious business, centered composition, wide shot")
]

presets_dict = { name: (filename, description) for (name, filename, description) in PRESETS}

class PromptList_PresetPanel(bpy.types.Panel):
    """Select a style preset"""
    bl_label = "Select a style preset"
    bl_idname = "OBJECT_PT_previews"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        row = layout.row()
        row.template_icon_view(wm, "style_presets")

        row = layout.row()
        row.prop(wm, "style_presets")


def get_preset_icons(self, context):
    enum_items = []

    if context is None:
        return enum_items

    wm = context.window_manager
    pcoll = preview_collections["style_presets"]
    icons_dir = os.path.join(os.path.dirname(__file__), "preview_thumbnails")

    for (name, (filename, description)) in presets_dict.items():
        filepath = os.path.join(icons_dir, name)
        if filepath in pcoll:
            thumb = pcoll[filepath]
        else:
            thumb = pcoll.load(filepath, filepath, 'IMAGE')

        enum_items.append((name, name, description, thumb.icon_id, 0))

    pcoll.previews = enum_items
    return pcoll.previews

def update_preset(self, context):
    print('update')
    pass

def register_presets():
    
    WindowManager.style_presets = EnumProperty(
        items=get_preset_icons,
        update=update_preset
        )


    pcoll = bpy.utils.previews.new()

    preview_collections["style_presets"] = pcoll
