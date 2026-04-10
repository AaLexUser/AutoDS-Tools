"""Utility functions for Jupyter executor.

This module contains helper functions for notebook execution including
async helpers, text processing utilities, and display functions.
"""

import asyncio
import base64
import logging
from typing import Literal

logger = logging.getLogger(__name__)

EXECUTION_TIMEOUT_SECONDS = 24 * 60 * 60  # 24 hours


async def _terminate_with_timeout(executor, timeout: float = 5.0) -> None:
    """Attempt to terminate an executor within a timeout."""
    try:
        await asyncio.wait_for(executor.terminate(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("Timeout while terminating kernel; forcing shutdown.")
    except Exception as exc:
        logger.debug("Error during kernel termination: %s", exc, exc_info=True)


async def _shutdown_all_kernels_async(active_executors: list):
    """Async version of cleanup all active executors."""
    for executor in list(active_executors):
        try:
            try:
                await _terminate_with_timeout(executor)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    await _terminate_with_timeout(executor)
                finally:
                    loop.close()
        except Exception as e:
            logger.debug(f"Error during executor cleanup: {e}", exc_info=True)


def shutdown_all_kernels(active_executors: list):
    """Cleanup all active executors when the Python interpreter exits.

    This is a synchronous wrapper for the async cleanup function.
    It handles the event loop management needed for proper async cleanup.
    """
    try:
        # Try to get existing event loop, handling deprecation warning
        try:
            loop = asyncio.get_running_loop()
            if loop.is_closed():
                # Create new loop if current one is closed
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            # No running event loop exists, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Run the async cleanup
        loop.run_until_complete(_shutdown_all_kernels_async(active_executors))
    except Exception as e:
        logger.debug(f"Error during kernel shutdown: {e}", exc_info=True)
    finally:
        # Clean up the loop if we created it
        try:
            if "loop" in locals() and loop and not loop.is_closed():
                loop.close()
        except Exception:
            pass  # Ignore errors during cleanup


def detect_ipython() -> bool:
    """Check if the code is running in an IPython environment."""
    try:
        from IPython import get_ipython

        ipython = get_ipython()
        return ipython is not None and "IPKernelApp" in ipython.config
    except Exception:
        return False


def display_image(
    image_base64: str, interaction_type: Literal["ipython", None]
) -> None:
    """Display a figure from base64-encoded image data."""
    try:
        image_bytes = base64.b64decode(image_base64)
        if interaction_type == "ipython":
            from IPython.display import Image, display

            display(Image(data=image_bytes))
        else:
            logger.debug("Image detected in output (not displayed in console mode)")
    except Exception as e:
        logger.warning(f"Error displaying image: {str(e)}")
