# Stability Addon for Blender

[Installation instructions](/Installing.md)

[Usage instructions](/Usage.md)


This is a plugin for Blender that lets you use the Stability.ai REST API for a variety of tasks, including:

* Send rendered animations and still frames to Stable Diffusion as init images, leading to some wild effects

![](/content/render2img.gif)
* Take a texture and send it through Stable Diffusion, allowing you to iterate quickly on refining textures

![](/content/img2img.gif)
* Generate new images from scratch using Stable Diffusion, for any use case you can imagine!

![](/content/text2img.gif)


Cool features include:

* Multi prompt support: add multiple prompts, and automate how much of each prompt is used per frame

![](/content/multi_prompt.gif)
* Keyframe all properties for generation: control the prompts, the amount of noise, via Blender's keyframe curve editor


![](/content/param_keyframing.gif)
* No external dependencies, one-click install and updating.

![](/content/city_pan.gif)
## Installation notes

Simply download a release from `Releases` and install it in Blender as you would any other plugin. You will need to have Blender 2.8 or later installed.

## Repo notes

This repo is formatted With Black. If you want to contribute, please install Black and run it on your code before submitting a PR.

## Making a GIF

`cd /tmp/dreams/results`

`ffmpeg -framerate 12 -pattern_type glob -i '*.png' -vcodec mpeg4 video.avi`

`convert -delay 5 -loop 0 'result_%d.png[0-999]' castle.gif`
