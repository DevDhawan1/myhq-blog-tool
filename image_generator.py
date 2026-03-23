import requests
import time

# Models tried in order — first one that works is used
HF_MODELS = [
    "stabilityai/stable-diffusion-xl-base-1.0",
    "black-forest-labs/FLUX.1-dev",
    "runwayml/stable-diffusion-v1-5",
]
HF_BASE = "https://router.huggingface.co/hf-inference/models"
UNSPLASH_BASE = "https://api.unsplash.com/photos/random"


def generate_ai_image(prompt: str, hf_token: str) -> bytes:
    """
    Generate an AI image via Hugging Face Inference API.
    Tries multiple models in order until one succeeds.
    Returns raw image bytes (JPEG/PNG).
    """
    headers = {"Authorization": f"Bearer {hf_token}"}

    enhanced_prompt = (
        f"{prompt}. Professional blog feature image, cinematic lighting, "
        "ultra-detailed, photorealistic, 4K quality"
    )

    last_error = None
    for model in HF_MODELS:
        url = f"{HF_BASE}/{model}"
        try:
            resp = requests.post(
                url,
                headers=headers,
                json={"inputs": enhanced_prompt},
                timeout=120,
            )
            if resp.status_code == 503:
                # Model warming up — wait and retry once
                time.sleep(25)
                resp = requests.post(
                    url, headers=headers,
                    json={"inputs": enhanced_prompt},
                    timeout=120,
                )
            if resp.status_code == 200 and resp.content[:4] in (b'\xff\xd8\xff\xe0', b'\x89PNG', b'GIF8', b'RIFF'):
                return resp.content  # valid image bytes
            last_error = f"{resp.status_code} {resp.text[:200]}"
        except Exception as e:
            last_error = str(e)
            continue

    raise RuntimeError(f"All HF models failed. Last error: {last_error}")


def get_unsplash_image(prompt: str, access_key: str) -> tuple[str, str]:
    """
    Fallback: fetch a relevant stock photo from Unsplash.
    Returns (image_url, credit_string).
    """
    query = prompt[:80].split(".")[0].strip()

    for search_query in [query, "office workspace", "coworking space"]:
        try:
            resp = requests.get(
                UNSPLASH_BASE,
                params={
                    "query": search_query,
                    "orientation": "landscape",
                    "client_id": access_key,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                img_url = data["urls"]["regular"]
                photographer = data["user"]["name"]
                link = data["links"]["html"] + "?utm_source=myHQ_blog_tool&utm_medium=referral"
                return img_url, f"Photo by [{photographer}]({link}) on Unsplash"
        except Exception:
            continue

    return "", ""
