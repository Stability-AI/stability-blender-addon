# Using Stability for Blender

For instructions on installing the plugin, go here: [Installation](Installation.md)

Stability for Blender is meant to be used in two different contexts: the 3D View, for taking a 3D scene and running Img2Img on rendered frames, or in the Image Editor, for running Img2Img on existing textures - or generating next textures from scratch.

## Using the 3D View Mode

To start, select the DreamStudio panel in the 3D View. You may need to click this arrow on the right side of the 3D View panel:

![](/content/image_editor_slide_out.jpg)

You should see the following UI:

![](/content/3D_view_default.jpjpg)

To start, press the 'Add' button on top of the Prompts list. This will add an empty prompt to the list - try filling with `A dream of a distant galaxy, concept art, matte painting, HQ, 4k`. You can click on 'DreamStudio Options' and 'Render Options' to toggle the panels for options relevant to diffusion and Blender, respectively.

Your UI should look like this:

![](/content/3D_view_ready.jpg)

Now, to render. Click 'Dream (Viewport)' and Blender will render your current viewport view, then send the frame to the Stability API. When the API finishes processing your image, the result will be displayed in a pop-up window. When you click 'Dream (Last Render)', the addon will look at the current output path in 'Output Properties' in Blender, and send the image rendered there to the API. When the API finishes processing your image, the result will be displayed in a pop-up window.

From here, try changing the prompt, adding multiple prompts, playing with the DreamStudio options, or the Blender render settings, and see what happens! You can set the 'Init Source' property in the 'Render Options' panel to 'Rendered Video Frames' to use a folder of video frames, as well. All parameters can also be automated - try changing the prompt strength over time to get some neat effects.

## Using the Image Editor Mode

In Blender, change the UI type to Image Editor, like so:

![](/content/image_editor_change_panel_type.jpg)

Then, you may need to select this tiny arrow icon to open the Image Editor side panel:

![](/content/image_editor_slide_out.jpg)

Now, you should see the following UI:

![](/content/image_editor_ready.jpg)

Similar to before, set the 'Height' and 'Width' to 512. Then, press the 'Add' button on top of the Prompts list. This will add an empty prompt to the list - try using `A dream of a distant galaxy, concept art, matte painting, HQ, 4k`.

Now, to render. Click 'Dream (Texture)' and Blender will send the texture to the Stability API. When the API finishes processing your image, the result will be displayed in your existing texture window.

From here, try changing the prompt, adding multiple prompts, playing with the DreamStudio options, or different types of textures, and see what happens!
