from bpy.types import Panel
import os
import bpy
import bpy.utils.previews

preview_collections = {}

class PresetsPanel(Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "Previews Example Panel"
    bl_idname = "Presets"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    def draw(self, context):
        layout = self.layout
        pcoll = preview_collections["main"]

        row = layout.row()
        my_icon = pcoll["my_icon"]
        row.operator("render.render", icon_value=my_icon.icon_id)

        # my_icon.icon_id can be used in any UI function that accepts
        # icon_value # try also setting text=""
        # to get an icon only operator button
