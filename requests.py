import os
import requests
import json
import random
import time
import bpy
from .prompt_list import MULTIPROMPT_ENABLED
from .data import APIType, TrackingEvent, DSAccount, get_preferences, log_sentry_event


def render_img2img(input_file_location, output_file_location, args, depth=False):
    preferences = get_preferences()
    api_type = APIType[preferences.api_type]
    if depth:
        log_sentry_event(TrackingEvent.DEPTH2IMG)
        if api_type == APIType.REST:
            return render_depth2img_rest(input_file_location, output_file_location, args)
        elif api_type == APIType.GRPC:
            # HACK for now, the grpc server accepts depth as init_image
            return render_img2img_grpc(input_file_location, output_file_location, args, depth=True)
    log_sentry_event(TrackingEvent.IMG2IMG)
    if api_type == APIType.REST:
        return render_img2img_rest(input_file_location, output_file_location, args)
    elif api_type == APIType.GRPC:
        return render_img2img_grpc(input_file_location, output_file_location, args)


def render_img2img_rest(input_file_location, output_file_location, args):
    seed = random.randrange(0, 4294967295) if args["seed"] is None else args["seed"]
    all_options = {
        "cfg_scale": args["cfg_scale"],
        "clip_guidance_preset": args["clip_guidance_preset"],
        "height": 512,
        "sampler": "K_DPM_2_ANCESTRAL",
        "seed": seed,
        "step_schedule_end": 0.01,
        "step_schedule_start": 1.0 - args["init_strength"],
        "steps": args["steps"],
        "text_prompts": args["prompts"],
        "width": 512,
    }

    base_url = args["base_url"]
    url = f"{base_url}/generation/stable-diffusion-v1-5/image-to-image"

    payload = {"options": json.dumps(all_options)}
    files = [
        (
            "init_image",
            ("render_0001.png", open(input_file_location, "rb"), "image/png"),
        )
    ]
    headers = {
        "accept": "image/png",
        "Authorization": args["api_key"],
    }

    response = requests.request("POST", url, headers=headers, data=payload, files=files)

    msg = response.reason

    if response.status_code in (200, 201):
        res_img = response.content
        with open(output_file_location, "wb") as res_img_file:
            res_img_file.write(res_img)
    else:
        try:
            res_body = response.json()
            msg = res_body["message"]
            print(msg)
        except json.JSONDecodeError:
            print(response.text)
    return response.status_code, msg

def render_depth2img_rest(input_file_location, output_file_location, args):
    seed = random.randrange(0, 4294967295) if args["seed"] is None else args["seed"]
    all_options = {
        "cfg_scale": args["cfg_scale"],
        "clip_guidance_preset": args["clip_guidance_preset"],
        "height": 512,
        "sampler": "K_DPM_2_ANCESTRAL",
        "seed": seed,
        "step_schedule_end": 0.01,
        "step_schedule_start": 1.0 - args["init_strength"],
        "steps": args["steps"],
        "text_prompts": args["prompts"],
        "width": 512,
    }

    base_url = args["base_url"]
    url = f"{base_url}/generation/stable-diffusion-depth-v2-0/depth-to-image"

    payload = {"options": json.dumps(all_options)}
    files = [
        (
            "depth_image",
            ("render_0001.png", open(input_file_location, "rb"), "image/png"),
        )
    ]
    headers = {
        "accept": "image/png",
        "Authorization": args["api_key"],
    }

    response = requests.request("POST", url, headers=headers, data=payload, files=files)

    msg = response.reason

    if response.status_code in (200, 201):
        res_img = response.content
        with open(output_file_location, "wb") as res_img_file:
            res_img_file.write(res_img)
    else:
        try:
            res_body = response.json()
            msg = res_body["message"]
            print(msg)
        except json.JSONDecodeError:
            print(response.text)
    return response.status_code, msg


def render_img2img_grpc(input_file_location, output_file_location, args, depth=False):

    import stability_sdk.interfaces.gooseai.generation.generation_pb2 as generation
    from stability_sdk import client, interfaces
    from PIL import Image
    import numpy as np
    import io
    from stability_sdk.utils import (
        SAMPLERS,
        MAX_FILENAME_SZ,
        truncate_fit,
        get_sampler_from_str,
        open_images,
    )

    engine = "stable-diffusion-v1-5" if not depth else "stable-diffusion-depth-v2-0"
    os.environ['STABILITY_HOST'] = args["base_url"]

    host = 'grpc-brian.stability.ai:443'
    key = 'sk-qhSi2fGaHyZKttXUCdC2c2kePLCaVavJXbY4jVRTSq4egPYL'


    # Our Host URL should not be prepended with "https" nor should it have a trailing slash.
    os.environ['STABILITY_HOST'] = host

    # Sign up for an account at the following link to get an API Key. https://beta.dreamstudio.ai/membership
    # Click on the following link once you have created an account to be taken to your API Key. Paste it below when prompted after running the cell. https://beta.dreamstudio.ai/membership?tab=apiKeys
    os.environ['STABILITY_KEY'] = key
    # Set up our connection to the API.
    stability_api = client.StabilityInference(
        key=os.environ['STABILITY_KEY'], # API Key reference.
        verbose=True, # Print debug messages.
        engine="stable-diffusion-depth-v2-0", # Set the engine to use for generation. 
        host=host
    )
    
    sampler = get_sampler_from_str(args["sampler"])
    if depth:
        sampler = generation.SAMPLER_K_DPMPP_2M
    init_img = Image.open(input_file_location)
    res_img = None
    seed = random.randrange(0, 4294967295) if args["seed"] is None else args["seed"]
    prompt_protos = []
    for p in args["prompts"]:
        prompt_proto = generation.Prompt(text=p["text"]) 
        prompt_params = prompt_proto.parameters
        prompt_params.weight = p["weight"]
        prompt_protos.append(prompt_proto)
    answers = stability_api.generate(
        init_image=init_img,
        start_schedule=1 - args["init_strength"],
        prompt=prompt_protos,
        seed=int(seed), # If a seed is provided, the resulting generated image will be deterministic.
                        # What this means is that as long as all generation parameters remain the same, you can always recall the same image simply by generating it again.
                        # Note: This isn't quite the case for Clip Guided generations, which we'll tackle in a future example notebook.
        steps=args["steps"], # Amount of inference steps performed on image generation. Defaults to 30. 
        cfg_scale=args["cfg_scale"], # Influences how strongly your generation is guided to match your prompt.
                        # Setting this value higher increases the strength in which it tries to match your prompt.
                        # Defaults to 7.0 if not specified.
        width=512, # Generation width, defaults to 512 if not included.
        height=512, # Generation height, defaults to 512 if not included.
        samples=1, # Number of images to generate, defaults to 1 if not included.
        sampler=sampler # Choose which sampler we want to denoise our generation with.
                                                    # Defaults to k_dpmpp_2m if not specified. Clip Guidance only supports ancestral samplers.
                                                    # (Available Samplers: ddim, plms, k_euler, k_euler_ancestral, k_heun, k_dpm_2, k_dpm_2_ancestral, k_dpmpp_2s_ancestral, k_lms, k_dpmpp_2m)
    )


    # TODO handle errors in here more gracefully. Look at REST or SDK code
    for resp in answers:
        for artifact in resp.artifacts:
            if (
                artifact.finish_reason
                == generation.FILTER
            ):
                return 401, "Safety filter hit"
            if (
                artifact.type
                == generation.ARTIFACT_IMAGE
            ):
                res_img = Image.open(io.BytesIO(artifact.binary))
                res_img.save(output_file_location)
                return 200, "Success"
    return 500, "No image returned from server"


def render_text2img(output_file_directory, args):

    log_sentry_event(TrackingEvent.TEXT2IMG)
    log_analytics_event(TrackingEvent.TEXT2IMG)

    seed = random.randrange(0, 4294967295) if args["seed"] is None else args["seed"]
    payload = {
        "cfg_scale": args["cfg_scale"],
        "clip_guidance_preset": args["clip_guidance_preset"],
        "height": 512,
        "sampler": "K_DPM_2_ANCESTRAL",
        "seed": seed,
        "step_schedule_end": 0.01,
        "step_schedule_start": 1.0 - args["init_strength"],
        "steps": args["steps"],
        "text_prompts": args["prompts"],
        "width": 512,
    }

    base_url = args["base_url"]
    url = f"{base_url}/generation/stable-diffusion-v1-5/text-to-image"

    headers = {
        "Content-Type": "application/json",
        "Accept": "image/png",
        "Authorization": args["api_key"],
    }

    response = requests.request("POST", url, json=payload, headers=headers)

    msg = response.reason

    if response.status_code in (200, 201):
        res_img = response.content
        with open(output_file_directory + "/result.png", "wb") as res_img_file:
            res_img_file.write(res_img)
    else:
        res_body = response.json()
        msg = res_body["message"]
    return response.status_code, msg


def log_analytics_event(
    tracking_event: TrackingEvent,
    payload: dict = {},
    debug: bool = False,
):
    prefs = get_preferences()
    if prefs and not prefs.record_analytics:
        return
    MEASUREMENT_ID = "G-VSQBN4R3ZS"
    API_SECRET = "YR_AFHGuSS-VtCQXIhb2Fg"
    url = f"https://www.google-analytics.com/mp/collect?measurement_id={MEASUREMENT_ID}&api_secret={API_SECRET}"
    if debug:
        url = f"https://www.google-analytics.com/debug/mp/collect?measurement_id={MEASUREMENT_ID}&api_secret={API_SECRET}"

    platform = "Windows" if os.name == "nt" else "macOS"
    country = "US"
    headers = {
        "authority": "www.google-analytics.com",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,sk;q=0.8,it;q=0.7",
        "content-type": "application/json",
        "dnt": "1",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": platform,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "geoid": country,
    }

    current_unix_timestamp_microseconds = int(time.time() * 1000000) - 52091520

    event_payload = {
        "client_id": "blender",
        "user_id": "brian",
        "timestamp_micros": current_unix_timestamp_microseconds,
        "non_personalized_ads": True,
        "events": [{"name": tracking_event.name, "params": payload}],
        "validationBehavior": "ENFORCE_RECOMMENDATIONS",
    }

    response = requests.request(
        "POST", url, headers=headers, data=json.dumps(event_payload)
    )

    if debug:
        errors = response.json()
        print(errors)

    if response.status_code not in (200, 204):
        print(
            f"Failed to record tracking event: {response.status_code} {response.reason}"
        )

def get_account_details(base_url: str, api_key: str) -> DSAccount:

    
    user = DSAccount()
    
    try:
        response = requests.get(f"{base_url}/user/account", headers={
            "Authorization": api_key
        })

        if response.status_code != 200:
            raise Exception("Error getting user details: " + str(response.text))

        # Do something with the payload...
        user_payload = response.json()

        user.email = user_payload["email"]
        user.id = user_payload["id"]

        response = requests.get(f"{base_url}/user/balance", headers={
            "Authorization": api_key
        })

        if response.status_code != 200:
            raise Exception("Error getting user balance: " + str(response.text))
        
        credits = response.json()["credits"]
        user.credits = round(credits, 2)
        user.logged_in = True
    except Exception as e:
        print(f"Error getting account details: {e}")

    return user