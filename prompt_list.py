import bpy
from bpy.props import StringProperty, IntProperty, CollectionProperty, FloatProperty
from bpy.types import PropertyGroup, UIList, Operator, Panel, UILayout

MULTIPROMPT_ENABLED = True


class PromptListItem(PropertyGroup):
    prompt: StringProperty(name="Prompt", default="")
    strength: FloatProperty(name="Strength", default=1, min=0, max=1)


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
    bl_label = "Add a new prompt"

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


def render_prompt_list(scene, layout):

    title_row = layout.row()
    if MULTIPROMPT_ENABLED:
        title_row.label(text="Prompts")
        title_row.operator("prompt_list.new_item", text="Add", icon="ADD")

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
