import bpy
from bpy.props import StringProperty, IntProperty, CollectionProperty, FloatProperty
from bpy.types import PropertyGroup, UIList, Operator, Panel, UILayout
class PromptListItem(PropertyGroup):
    prompt: StringProperty(name="Prompt", default="")
    strength: FloatProperty(name="Strength", default=1, min=0, max=1)

class PromptListUIItem(UILayout):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        prompt_data = item
        layout.prop(prompt_data, "prompt")
        layout.prop(prompt_data, "strength")

class PromptList_NewItem(Operator):
    """Add a new item to the list."""

    bl_idname = "prompt_list.new_item"
    bl_label = "Add a new prompt"

    def execute(self, context):
        context.scene.prompt_list.add()

        return {'FINISHED'}

class PromptList_RemoveItem(Operator):
    """Remove an item from the list."""

    bl_idname = "prompt_list.remove_item"
    bl_label = "Remove a prompt"

    index: IntProperty()

    def execute(self, context):
        print(self.index)
        context.scene.prompt_list.remove(self.index)

        return {'FINISHED'}
