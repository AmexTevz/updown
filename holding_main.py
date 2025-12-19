#!/usr/bin/env python3
"""
Holding Training - Main Launcher
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

from main_wit import main as sensor_main
from holding_game import HoldingGame, game_loop
from hardware import emergency_shutdown, read_button, strobe_control, all_bulbs_on, heat_control, \
    send_vibration  # ← ADD read_button HERE
from config import PREGAME_WAIT_MIN, PREGAME_WAIT_MAX, PREGAME_WAIT_MIN_TESTING, PREGAME_WAIT_MAX_TESTING, TESTING_MODE
from audio import cleanup_audio, play_audio_from_folder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)

# Quiet sensor logs during game
logging.getLogger('main_wit').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

game: Optional[HoldingGame] = None
sensor_task: Optional[asyncio.Task] = None
game_task: Optional[asyncio.Task] = None


async def pregame_sensor_test():
    """
    Pregame sensor test - board level controls strobe
    Runs BEFORE button calibration sequence
    """
    from main_wit import SensorDataQueue

    logger.info("=" * 60)
    logger.info("PREGAME SENSOR TEST")
    logger.info("=" * 60)
    logger.info("All devices ON - Strobe responds to board level")
    logger.info("Press Button 2 when ready to start calibration")
    logger.info("=" * 60)

    # Turn on all devices
    await all_bulbs_on()
    await heat_control("on")
    await strobe_control("on")

    sensor_queue = SensorDataQueue()
    strobe_state = "on"
    last_button_value = await read_button(227)

    logger.info("✓ Pregame test active - move board to test sensor")

    while True:
        # Get board angle
        angles = sensor_queue.get_all_angles()
        angle = None

        if 'w_back.txt' in angles and angles['w_back.txt'] is not None:
            angle = angles['w_back.txt']
        elif 'Orientation.txt' in angles and angles['Orientation.txt'] is not None:
            angle = angles['Orientation.txt']

        # Check if level - SAME LOGIC AS GAME
        # ANY negative = level
        # Positive: 0 to +10 = level
        if angle is not None:
            if angle < 0:
                is_level = True  # Any negative = level
            else:
                is_level = angle <= 10  # Positive: 0-10 = level
        else:
            is_level = False

        # Control strobe (only when state changes)
        if is_level and strobe_state != "off":
            await strobe_control("off")
            strobe_state = "off"
            logger.info(f"✓ Board level (angle: {angle:.1f}°) - strobe OFF")
        elif not is_level and strobe_state != "on":
            await strobe_control("on")
            strobe_state = "on"
            if angle is not None:
                logger.info(f"⚠️ Board not level (angle: {angle:.1f}°) - strobe ON")
            else:
                logger.info("⚠️ No sensor data - strobe ON")

        # Check for button press
        current_button = await read_button(227)
        if current_button is not None and last_button_value is not None:
            if current_button > last_button_value:
                logger.info("Button pressed - exiting pregame test")
                await strobe_control("off")
                return
        last_button_value = current_button

        await asyncio.sleep(0.1)


async def sensor_calibration_mode():
    """
    3-button press sequence with audio feedback
    """
    import random
    import pygame

    logger.info("=" * 60)
    logger.info("HOLDING TRAINING - BUTTON SEQUENCE")
    logger.info("=" * 60)
    logger.info("Waiting for first Button 2 press...")

    async def wait_for_button_press():
        """Wait for button 2 press (rising edge)"""
        last_value = await read_button(227)

        while True:
            current_value = await read_button(227)

            if current_value is not None and last_value is not None:
                if current_value > last_value:
                    return True

            last_value = current_value
            await asyncio.sleep(0.1)

    # FIRST PRESS - Introduction (SKIPPABLE)
    await wait_for_button_press()
    logger.info("✓ First press - Playing introduction (press again to skip)")
    await send_vibration()

    # Play intro with skip capability
    duration = play_audio_from_folder('audio_holding/holding_intro', 'Introduction')

    if duration > 0:
        intro_start = asyncio.get_event_loop().time()
        last_value = await read_button(227)

        while asyncio.get_event_loop().time() - intro_start < duration + 0.3:
            # Check for button press to skip
            current_value = await read_button(227)
            if current_value is not None and last_value is not None:
                if current_value > last_value:
                    logger.info("✓ Intro skipped by button press")
                    pygame.mixer.stop()
                    pygame.mixer.music.stop()
                    break
            last_value = current_value
            await asyncio.sleep(0.1)

    await asyncio.sleep(0.5)

    # SECOND PRESS - First confirmation
    logger.info("Waiting for second Button 2 press...")
    await wait_for_button_press()
    logger.info("✓ Second press - First confirmation")
    play_audio_from_folder('audio_holding/first_press', 'First confirmation')
    await send_vibration()

    await all_bulbs_on()
    await asyncio.sleep(1)
    await all_bulbs_on()  # Toggle off
    await asyncio.sleep(2)

    # THIRD PRESS - Final confirmation
    logger.info("Waiting for third Button 2 press...")
    await wait_for_button_press()
    logger.info("✓ Third press - Final confirmation")
    play_audio_from_folder('audio_holding/second_press', 'Final confirmation')
    await send_vibration()

    await all_bulbs_on()
    await strobe_control("on")
    await asyncio.sleep(2)
    await strobe_control("off")

    # Wait before starting
    if TESTING_MODE:
        wait_time = random.randint(PREGAME_WAIT_MIN_TESTING, PREGAME_WAIT_MAX_TESTING)
        logger.info(f"[TESTING MODE] Waiting {wait_time} seconds...")
    else:
        wait_time = random.randint(10, 30)
        logger.info(f"Waiting {wait_time} seconds before starting...")

    await asyncio.sleep(wait_time)
    logger.info("Starting holding training game...")


async def main():
    """Main entry point"""
    global game, sensor_task, game_task

    try:
        logger.info("=" * 70)
        logger.info("HOLDING TRAINING GAME")
        logger.info("=" * 70)
        logger.info("Objective: Keep board level (±10°) for training duration")
        logger.info("=" * 70)

        # Start sensor system
        logger.info("Starting sensor system...")
        sensor_task = asyncio.create_task(sensor_main())
        await asyncio.sleep(2)

        # PREGAME SENSOR TEST
        await pregame_sensor_test()

        # Sensor calibration mode
        await sensor_calibration_mode()

        # Create and start game
        game = HoldingGame()
        game.is_running = True
        await game.start_game()

        # Start game loop
        game_task = asyncio.create_task(game_loop(game))
        await game_task

    except KeyboardInterrupt:
        logger.info("\n⚠️  Keyboard interrupt received")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        await cleanup()


async def cleanup():
    """Cleanup on exit"""
    global game, sensor_task, game_task

    logger.critical("=" * 70)
    logger.critical(" STARTING CLEANUP SEQUENCE")
    logger.critical("=" * 70)

    try:
        if game:
            game.is_running = False
            logger.info("✓ Game stopped")

        if sensor_task and not sensor_task.done():
            sensor_task.cancel()
            try:
                await sensor_task
            except asyncio.CancelledError:
                pass
            logger.info("✓ Sensor system stopped")

        if game_task and not game_task.done():
            game_task.cancel()
            try:
                await game_task
            except asyncio.CancelledError:
                pass
            logger.info("✓ Game task cancelled")

        cleanup_audio()
        logger.info("✓ Audio cleaned up")

        await emergency_shutdown()

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

    logger.critical("=" * 70)
    logger.critical(" CLEANUP COMPLETE")
    logger.critical("=" * 70)


def signal_handler(signum, frame):
    """Handle termination signals"""
    logger.warning(f"\nReceived signal {signum}")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        logger.critical("Program terminated.")