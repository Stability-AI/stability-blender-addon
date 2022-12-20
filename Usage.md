# Using Stability for Blender

For instructions on installing the plugin, go here: [Installation](Installation.md)

Stability for Blender is meant to be used in two different contexts: the 3D View, for taking a 3D scene and running Img2Img on rendered frames, or in the Image Editor, for running Img2Img on existing textures - or generating next textures from scratch.

## Using the 3D View Mode

Load up a Blender project - if you don't have one handy, you can open the demo project, which you can download [here](https://github.com/Stability-AI/stability-blender-addon/raw/main/example_scenes/the%20orb.blend).

Open your project and select the DreamStudio panel in the 3D View. You may need to click this arrow on the right side of the 3D View panel:

![](/content/image_editor_slide_out.jpg)

Enter your DreamStudio API key, and you should see the following UI:

![](/content/3D_view_default.jpg)

To start, press the 'Add' button on top of the Prompts list. This will add an empty prompt to the list - try filling the text field with `A mystical floating orb, concept art, matte painting, HQ, 4k`. You can click on 'DreamStudio Options' and 'Render Options' to toggle the panels for options relevant to diffusion and Blender, respectively.

Your UI should look like this:

![](/content/3D_view_ready.jpg)

### Generating from the Viewport

Sometimes it can be useful to get a quick render from a vantage point to see how Stable Diffusion will process a view. Click the 'Render (Viewport) button to render the contents of the current viewport. Note that your current viewport shading mode will apply - make sure you are in 'Material Preview' or 'Render' view, or you will get a bunch of grey objects!

### Generating from a Render

To generate from an image rendered in Blender, open the Render Options panel by clicking the arrow next to the title. Then, change the Init Source to 'Texture'. You can choose any texture in your project as the init image, but for this you'll want to select 'Render Result'. Press F12 or Render -> Render Image in the top bar, to render your scene, then press `Dream (Texture)` in the DreamStudio UI. You should see your scene processed by Stable Diffusion!

### Generating from an Animation

One of the coolest features of the addon is the ability to render out animations. Hover over any parameter in the UI and press I to insert a keyframe for it, at your current frame in Blender - then, open the Render Options panel by clicking the arrow next to the title. Change the Init Source to 'Animation'. Then, render out your video as a series of stills in a directory; finally, select that directory as the `Frame Directory` in the addon window, under Render Options, and press `Dream (Animate)`. You should see the addon generate a new frame in the output folder, with each parameter at its interpolated value for each frame. Press 'Show Folder' to open the folder with your generated frames.

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
