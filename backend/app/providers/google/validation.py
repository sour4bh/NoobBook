"""Google AI API key validators."""
import logging
from typing import Tuple
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


def validate_gemini_2_5_key(api_key: str) -> Tuple[bool, str]:
    """
    Validate Gemini 2.5 API key by making a test text generation request.

    Educational Note: This tests if the API key is valid and enabled for
    Gemini 2.5 (text generation) model.

    Args:
        api_key: The Google API key to validate

    Returns:
        Tuple of (is_valid, message)
    """
    if not api_key or api_key == '':
        return False, "API key is empty"

    try:
        # Create client with the provided key
        client = genai.Client(api_key=api_key)

        # Make a minimal test request with Gemini 2.5 Flash
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Test"
        )

        # If we get here with a response, the key is valid
        if response.text:
            return True, "Valid Gemini 2.5 API key"
        else:
            return False, "API returned empty response"

    except Exception as e:
        error_message = str(e).lower()

        # Check for common error types
        if 'api key not valid' in error_message or 'invalid' in error_message:
            return False, "Invalid API key"
        elif 'permission' in error_message or 'enabled' in error_message:
            return False, "API not enabled for this key. Enable Gemini API in Google Cloud Console"
        elif 'quota' in error_message:
            return True, "Valid API key (quota exceeded)"
        elif 'rate' in error_message:
            return True, "Valid API key (rate limited)"
        else:
            logger.error("Gemini 2.5 validation error: %s: %s", type(e).__name__, e)
            return False, f"Validation failed: {str(e)[:100]}"


def validate_nano_banana_key(api_key: str) -> Tuple[bool, str]:
    """
    Validate Nano Banana (Image Generation) API key.

    Educational Note: This tests if the API key is valid and enabled for
    Gemini 3 Pro Image Preview model. We use minimal settings for fastest test.
    """
    if not api_key or api_key == '':
        return False, "API key is empty"

    try:
        client = genai.Client(api_key=api_key)

        model = "gemini-3-pro-image-preview"
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text="Test image")],
            ),
        ]

        generate_content_config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                image_size="1K",
            ),
        )

        response = None
        for chunk in client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=generate_content_config,
        ):
            if (chunk.candidates and
                chunk.candidates[0].content and
                chunk.candidates[0].content.parts):
                response = chunk
                break

        if response:
            return True, "Valid Nano Banana (Image Gen) API key"
        else:
            return False, "API returned no image data"

    except Exception as e:
        error_message = str(e).lower()

        if 'api key not valid' in error_message or 'invalid' in error_message:
            return False, "Invalid API key"
        elif 'permission' in error_message or 'enabled' in error_message:
            return False, "Image generation API not enabled. Enable Gemini API in Google Cloud Console"
        elif 'quota' in error_message:
            return True, "Valid API key (quota exceeded)"
        elif 'rate' in error_message:
            return True, "Valid API key (rate limited)"
        else:
            logger.error("Nano Banana validation error: %s: %s", type(e).__name__, e)
            return False, f"Validation failed: {str(e)[:100]}"


def validate_veo_key(api_key: str) -> Tuple[bool, str]:
    """
    Validate VEO (Video Generation) API key.

    Educational Note: This tests if the API key is valid and enabled for
    VEO 2.0 video generation model. We use minimal settings for fastest test.
    """
    if not api_key or api_key == '':
        return False, "API key is empty"

    try:
        client = genai.Client(
            http_options={"api_version": "v1beta"},
            api_key=api_key
        )

        model = "veo-2.0-generate-001"

        video_config = types.GenerateVideosConfig(
            aspect_ratio="16:9",
            number_of_videos=1,
            duration_seconds=5,
            person_generation="ALLOW_ALL",
        )

        operation = client.models.generate_videos(
            model=model,
            prompt="Test video",
            config=video_config,
        )

        if operation:
            return True, "Valid VEO (Video Gen) API key"
        else:
            return False, "API did not accept video generation request"

    except Exception as e:
        error_message = str(e).lower()

        if 'api key not valid' in error_message or 'invalid' in error_message:
            return False, "Invalid API key"
        elif 'permission' in error_message or 'enabled' in error_message:
            return False, "Video generation API not enabled. Enable VEO API in Google Cloud Console"
        elif 'quota' in error_message:
            return True, "Valid API key (quota exceeded)"
        elif 'rate' in error_message:
            return True, "Valid API key (rate limited)"
        else:
            logger.error("VEO validation error: %s: %s", type(e).__name__, e)
            return False, f"Validation failed: {str(e)[:100]}"
