"""
Monkey patches for Pyrogram library to handle known issues.
"""

from logging import getLogger

logger = getLogger("telegram.pyrogram_patches")


def patch_pyrogram():
    """Apply all necessary Pyrogram patches."""
    _patch_webapp_data_parse()
    logger.info("Applied Pyrogram patches")


def _patch_webapp_data_parse():
    """
    Patch WebAppData._parse to handle MessageActionWebViewDataSent without 'data' attribute.
    MessageActionWebViewDataSent only has 'text' field, not 'data'.
    """
    try:
        from pyrogram.types.messages_and_media.web_app_data import WebAppData

        original_parse = WebAppData._parse

        @staticmethod
        def patched_parse(action):
            # MessageActionWebViewDataSent only has 'text', not 'data'
            # Return a WebAppData with the text as both data and button_text
            if hasattr(action, "data"):
                return original_parse(action)
            else:
                # For MessageActionWebViewDataSent, use the text field
                text = getattr(action, "text", "")
                logger.debug(f"Handling MessageActionWebViewDataSent with text: {text}")
                return WebAppData(
                    data=text,  # Use text as data since that's what's available
                    button_text=text,
                )

        WebAppData._parse = patched_parse
        logger.debug("Patched WebAppData._parse method")

    except ImportError as e:
        logger.error(f"Failed to import Pyrogram types for patching: {e}")
    except Exception as e:
        logger.error(f"Failed to patch WebAppData._parse: {e}")
