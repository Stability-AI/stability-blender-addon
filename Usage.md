# Using Stability for Blender

For instructions on installing the plugin, go here: [Installation](Installation.md)

Stability for Blender is meant to be used in two different contexts: the 3D View, for taking a 3D scene and running Img2Img on rendered frames, or in the Image Editor, for running Img2Img on existing textures - or generating next textures from scratch.

## How to use the 3D View Mode

To start, select the DreamStudio panel in the 3D View. You will see the following UI:

![](/content/3D_view_default.png)

To make things easy, uncheck the 'Use Render Resolution' toggle under '3D View Options', and set the 'Height' and 'Width' to 512. Then, press the 'Add' button on top of the Prompts list. This will add an empty prompt to the list - try using `A dream of a distant galaxy, concept art, matte painting, HQ, 4k`.

Your UI should look like this:

![](/content/3D_view_ready.png)

Now, to render. Click 'Dream (Frame)' and Blender will render a single frame, then send the frame to the Stability API. When the API finishes processing your image, the result will be displayed in a pop-up window.

From here, try changing the prompt, adding multiple prompts, playing with the DreamStudio options, or the Blender render settings, and see what happens! You can also render your whole animation range with the 'Dream (Animation)' button. All parameters can also be automated - try changing the prompt strength over time to get some neat effects.

## How to use the Image Editor Mode

In Blender, change the UI type to Image Editor, like so:

![](/content/image_editor_change_panel_type.png)

Then, you may need to select this tiny arrow icon to open the Image Editor side panel:

![](/content/image_editor_slide_out.png)

Now, you should see the following UI:

![](/content/image_editor_ready.png)

Similar to before, set the 'Height' and 'Width' to 512. Then, press the 'Add' button on top of the Prompts list. This will add an empty prompt to the list - try using `A dream of a distant galaxy, concept art, matte painting, HQ, 4k`.

Now, to render. Click 'Dream (Texture)' and Blender will send the texture to the Stability API. When the API finishes processing your image, the result will be displayed in your existing texture window.

From here, try changing the prompt, adding multiple prompts, playing with the DreamStudio options, or different types of textures, and see what happens!
