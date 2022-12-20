# Stability Addon for Blender

This is a plugin for Blender that lets you use the Stability.ai REST API to generate images and videos from your renders, right inside Blender - as well as generate textures to use in any use case you want.

## Installation

Get the latest release [here](https://github.com/Stability-AI/stability-blender-addon/releases) - download stability-blender-addon.zip.

Never installed a Blender plugin before? We have detailed, step-by-step 
[installation instructions](/Installing.md)!

Need help getting started? See our [usage instructions](/Usage.md) here.

## Features

* Send rendered animations and still frames to Stable Diffusion as init images, leading to some wild effects

![](/content/city_init.png)
![](/content/city_result.png)

* Take a texture and send it through Stable Diffusion, allowing you to iterate quickly on refining textures

![](/content/img2img.gif)
* Generate new images from scratch using Stable Diffusion, for any use case you can imagine!

![](/content/text2img.gif)


Cool features include:

* Multi prompt support: add multiple prompts, and automate how much of each prompt is used per frame

![](/content/city_pan.gif)
* Keyframe all properties for generation: control the prompts, the amount of noise, via Blender's keyframe curve editor


![](/content/param_keyframing.gif)
* No external dependencies, one-click install and updating.

## Repo notes

This repo is formatted with Black. If you want to contribute, please install Black and run it on your code before submitting a PR.

Find a bug! Please report it as an Issue!