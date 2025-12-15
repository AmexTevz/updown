#!/usr/bin/env python3
"""
Holding Training - Main Launcher

Simpler training where subject just needs to keep board level
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

# Import sensor system
from main_wit import main as sensor_main

# Import holding game
from holding_game import HoldingGame, game_loop

# Import cleanup
from hardware import emergency_shutdown

# Import config
from config import PREGAME_WAIT_MIN, PREGAME_WAIT_MAX, PREGAME_WAIT_MIN_TESTING, PREGAME_WAIT_MAX_TESTING, TESTING_MODE

# Import audio
from audio import cleanup_audio, play_audio_from_folder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)

logger = logging.getLogger(__name__)

# Global references
game: Optional[HoldingGame] = None
sensor_task: Optional[asyncio.Task] = None
game_task: Optional[asyncio.Task] = None


async def sensor_calibration_mode():
    """
    Sensor calibration and game start
    3-button press sequence with audio feedback:
    1. First press → holding_intro
    2. Second press → first_press
    3. Third press → second_press → game starts
    """
    import random
    from hardware import read_button, all_bulbs_on, strobe_control, send_vibration
    
    logger.info("=" * 60)
    logger.info("HOLDING TRAINING - BUTTON SEQUENCE")
    logger.info("=" * 60)
    logger.info("Waiting for first Button 2 press...")
    
    # Helper function to wait for button press
    async def wait_for_button_press():
        """Wait for button 2 press (rising edge)"""
        last_value = await read_button(227)  # Button 2
        
        while True:
            current_value = await read_button(227)
            
            if current_value is not None and last_value is not None:
                if current_value > last_value:
                    return True
            
            last_value = current_value
            await asyncio.sleep(0.1)
    
    # FIRST PRESS - Introduction
    await wait_for_button_press()
    logger.info("✓ First press - Playing introduction")
    play_audio_from_folder('audio_holding/holding_intro', 'Introduction')
    await send_vibration()
    await asyncio.sleep(2)
    
    # SECOND PRESS - First confirmation
    logger.info("Waiting for second Button 2 press...")
    await wait_for_button_press()
    logger.info("✓ Second press - First confirmation")
    play_audio_from_folder('audio_holding/first_press', 'First confirmation')
    await send_vibration()
    
    # Flash lights briefly
    await all_bulbs_on()
    await asyncio.sleep(1)
    await all_bulbs_on()  # Turn off via toggle
    await asyncio.sleep(2)
    
    # THIRD PRESS - Final confirmation
    logger.info("Waiting for third Button 2 press...")
    await wait_for_button_press()
    logger.info("✓ Third press - Final confirmation")
    play_audio_from_folder('audio_holding/second_press', 'Final confirmation')
    await send_vibration()
    
    # Turn on all bulbs + strobe as final confirmation
    await all_bulbs_on()
    await strobe_control("on")
    await asyncio.sleep(2)
    await strobe_control("off")
    
    # Wait before starting (random)
    if TESTING_MODE:
        wait_time = random.randint(PREGAME_WAIT_MIN_TESTING, PREGAME_WAIT_MAX_TESTING)
        logger.info(f"[TESTING MODE] Waiting {wait_time} seconds before starting...")
    else:
        wait_time = random.randint(PREGAME_WAIT_MIN, PREGAME_WAIT_MAX)
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
        
        # Sensor calibration mode
        await sensor_calibration_mode()
        
        # Create game
        game = HoldingGame()
        game.is_running = True
        
        # Start game loop
        game_task = asyncio.create_task(game_loop(game))
        
        # Wait for game to finish
        await game_task
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Keyboard interrupt received")
    except Exception as e:
        logger.critical(f"Fatal startup error: {e}", exc_info=True)
    finally:
        await cleanup()


async def cleanup():
    """Cleanup on exit"""
    global game, sensor_task, game_task
    
    logger.critical("=" * 70)
    logger.critical(" STARTING CLEANUP SEQUENCE")
    logger.critical("=" * 70)
    
    try:
        # Stop game
        if game:
            game.is_running = False
            logger.info("✓ Game stopped")
        
        # Cancel sensor task (it will handle cancellation gracefully)
        if sensor_task and not sensor_task.done():
            sensor_task.cancel()
            try:
                await sensor_task
            except asyncio.CancelledError:
                pass
            logger.info("✓ Sensor system stopped")
        
        # Cancel game task
        if game_task and not game_task.done():
            game_task.cancel()
            try:
                await game_task
            except asyncio.CancelledError:
                pass
            logger.info("✓ Game task cancelled")
        
        # Cleanup audio
        cleanup_audio()
        logger.info("✓ Audio cleaned up")
        
        # Emergency cleanup (all lights on, plug on)
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
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        logger.critical("Program terminated.")