import os
import requests
import json
import random
import time
import bpy
from .prompt_list import MULTIPROMPT_ENABLED
from .data import APIType, TrackingEvent, DSAccount, get_preferences, log_sentry_event


def render_img2img(input_file_location, output_file_location, args):
    preferences = get_preferences()
    api_type = APIType[preferences.api_type]
    log_sentry_event(TrackingEvent.IMG2IMG)
    if api_type == APIType.REST:
        return render_img2img_rest(input_file_location, output_file_location, args)
    if api_type == APIType.GRPC:
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


def render_img2img_grpc(input_file_location, output_file_location, args):

    from stability_sdk import client, interfaces
    from PIL import Image
    import io
    from stability_sdk.utils import (
        SAMPLERS,
        MAX_FILENAME_SZ,
        truncate_fit,
        get_sampler_from_str,
        open_images,
    )

    stability_inference = client.StabilityInference(
        key=args["api_key"], host=args["base_url"]
    )

    sampler = get_sampler_from_str(args["sampler"])
    init_img = Image.open(input_file_location)
    res_img = None
    seed = random.randrange(0, 4294967295) if args["seed"] is None else args["seed"]
    if MULTIPROMPT_ENABLED:
        prompts = args["prompts"]
    else:
        prompts = args["prompts"][0]["text"]
    frame_seed = seed
    answers = stability_inference.generate(
        prompt=prompts,
        init_image=init_img,
        width=init_img.width if init_img is not None else args["width"],
        height=init_img.height if init_img is not None else args["height"],
        start_schedule=1.0 - args["init_strength"],
        cfg_scale=args["cfg_scale"],
        steps=args["steps"],
        guidance_strength=args["guidance_strength"],
        sampler=sampler,
        seed=frame_seed,
    )

    # TODO handle errors in here more gracefully. Look at REST or SDK code
    for answer in answers:
        for artifact in answer.artifacts:
            print("type", artifact.type, "finish reason", artifact.finish_reason)
            if (
                artifact.finish_reason
                == interfaces.gooseai.generation.generation_pb2.FILTER
            ):
                return 401, "Safety filter hit"
            if (
                artifact.type
                == interfaces.gooseai.generation.generation_pb2.ARTIFACT_IMAGE
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

    return user