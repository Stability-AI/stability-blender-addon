import os
import requests
import requests
import json
import random
import time
from enum import Enum
import bpy
from .prompt_list import MULTIPROMPT_ENABLED
from .data import APIType


def render_img2img(input_file_location, output_file_location, args):
    preferences = bpy.context.preferences.addons[__package__].preferences
    api_type = APIType[preferences.api_type]
    if api_type == APIType.REST:
        return render_img2img_rest(input_file_location, output_file_location, args)
    if api_type == APIType.GRPC:
        return render_img2img_grpc(input_file_location, output_file_location, args)


def render_img2img_rest(input_file_location, output_file_location, args):
    prompts = [{"text": p[0], "weight": p[1]} for p in args["prompts"]]

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
        "text_prompts": prompts,
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

    sampler_name = args["sampler"].name.lower().strip()
    sampler = get_sampler_from_str(sampler_name)

    init_img = Image.open(input_file_location)
    hit_safety_filter = True
    res_img = None
    seed = random.randrange(0, 4294967295) if args["seed"] is None else args["seed"]
    prompts = [{"text": p[0], "weight": p[1]} for p in args["prompts"]]
    if not MULTIPROMPT_ENABLED:
        prompts = prompts[0]["text"]
    while hit_safety_filter:
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

        for answer in answers:
            for artifact in answer.artifacts:
                print("type", artifact.type, "finish reason", artifact.finish_reason)
                if (
                    artifact.finish_reason
                    == interfaces.gooseai.generation.generation_pb2.FILTER
                ):
                    frame_seed += 1
                    break
                if (
                    artifact.type
                    == interfaces.gooseai.generation.generation_pb2.ARTIFACT_IMAGE
                ):
                    res_img = Image.open(io.BytesIO(artifact.binary))
                    res_img.save(output_file_location)
                    hit_safety_filter = False
    if res_img is None:
        # TODO actual error surfacing
        return 500, "No image returned from server"
    return 200, "Success"


def render_text2img(output_file_location, args):

    prompts = [{"text": p[0], "weight": p[1]} for p in args["prompts"]]

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
        "text_prompts": prompts,
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
        with open(output_file_location, "wb") as res_img_file:
            res_img_file.write(res_img)
    else:
        res_body = response.json()
        msg = res_body["message"]
        print(msg)
    return response.status_code, msg


TRACKED_GENERATION_PARAMS = [
    "cfg_scale",
    "clip_guidance_preset",
    "width",
    "height",
    "sampler",
    "seed",
    "step_schedule_end",
    "step_schedule_start",
    "steps",
    "text_prompts",
]


def filter_keys(keys, d):
    print(keys)
    return {k: d[k] for k in keys if k in d}


class TrackingEvent(Enum):
    TEXT2IMG = 1
    IMG2IMG = 2
    CANCEL_GENERATION = 3


# TODO track crashes, and exceptions as well
TRACKING_EVENTS = {
    TrackingEvent.TEXT2IMG: TRACKED_GENERATION_PARAMS,
    TrackingEvent.IMG2IMG: TRACKED_GENERATION_PARAMS,
    TrackingEvent.CANCEL_GENERATION: [],
}


def record_tracking_event(
    tracking_event: TrackingEvent,
    payload: dict,
    user_id: str = None,
    debug: bool = False,
):
    url = "https://www.google-analytics.com/mp/collect?measurement_id=G-321PW7EDCP&api_secret=CPIiVajARdOuRypeU2mOrg"
    if debug:
        url = "https://www.google-analytics.com/debug/mp/collect?measurement_id=G-321PW7EDCP&api_secret=CPIiVajARdOuRypeU2mOrg"

    if tracking_event not in TRACKING_EVENTS:
        raise ValueError(f"Unknown event name: {tracking_event}")

    if set(payload.keys()) != set(TRACKING_EVENTS[tracking_event]):
        raise ValueError(f"Invalid payload for event {tracking_event}")

    if "text_prompts" in payload and len(payload["text_prompts"]) > 0:
        payload["prompt"] = payload["text_prompts"][0]["text"]
        payload["text_prompts"] = json.dumps(payload["text_prompts"])

    # https://developers.google.com/analytics/devguides/collection/protocol/v1/parameters
    # TODO flesh these out.
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
