#!/usr/bin/env python3
"""
Up/Down Training Game - Main Entry Point
Phase 1: Core Infrastructure Testing

Run this file to start the game
"""
import atexit
import signal
import asyncio
import logging
import sys
import random
from datetime import datetime, timedelta
from main_wit import set_angle_printing

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'game_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('main')

# Import game modules
try:
    from config import *
    from hardware import (
        hardware_state, start_hardware_monitoring, stop_hardware_monitoring,
        bulb_1_control, bulb_2_control, all_bulbs_off, all_bulbs_on,
        read_button, send_vibration, plug_control
    )
    from audio import (
        audio_manager, start_white_noise, stop_white_noise,
        play_first_press, play_second_press, play_sensor_issue,
        play_sensor_issue_resolved
    )
    from game import UpDownGame, game_loop
except ImportError as e:
    logger.critical(f"Failed to import modules: {e}")
    logger.critical("Make sure all files are in the same directory:")
    logger.critical("  - config.py")
    logger.critical("  - hardware.py")
    logger.critical("  - audio.py")
    logger.critical("  - game.py")
    logger.critical("  - main_wit.py (sensor system)")
    sys.exit(1)

# Import sensor system
try:
    from main_wit import main as sensor_main, sensor_queue
except ImportError as e:
    logger.critical(f"Failed to import sensor system: {e}")
    logger.critical("Make sure main_wit.py is in the same directory")
    sys.exit(1)


async def safe_audio(audio_func, fallback_message):
    """
    Safely play audio - if it fails, just log and continue
    """
    try:
        from audio import play_audio
        play_audio(audio_func, fallback_message)
    except Exception as e:
        logger.warning(f"Audio failed: {e} - continuing anyway")


async def wait_for_sensors():
    """
    Wait for both sensors to connect
    Give them 30 seconds max
    """
    logger.info("=" * 70)
    logger.info(" WAITING FOR SENSORS TO CONNECT")
    logger.info("=" * 70)

    timeout = 30
    start_time = asyncio.get_event_loop().time()

    primary_connected = False
    backup_connected = False

    logger.info("Testing button reads...")
    for i in range(5):
        b1 = await read_button(BUTTON_1)
        b2 = await read_button(BUTTON_2)
        logger.info(f"  Test {i + 1}: Button1={b1}, Button2={b2}")
        await asyncio.sleep(0.5)
    logger.info("Button test complete. Starting calibration...")

    while asyncio.get_event_loop().time() - start_time < timeout:
        primary_state = sensor_queue.get_sensor_state('w_back.txt')
        backup_state = sensor_queue.get_sensor_state('Orientation.txt')

        # Check primary
        if primary_state.value == 'connected' and not primary_connected:
            primary_connected = True
            logger.info("✓ Primary sensor (w_back.txt) CONNECTED")

        # Check backup
        if backup_state.value == 'connected' and not backup_connected:
            backup_connected = True
            logger.info("✓ Backup sensor (Orientation.txt) CONNECTED")

        # Both connected?
        if primary_connected and backup_connected:
            logger.info("")
            logger.info("=" * 70)
            logger.info(" ✓ BOTH SENSORS CONNECTED")
            logger.info("=" * 70)
            logger.info("")
            return True

        await asyncio.sleep(0.5)

    # Timeout - check what we have
    logger.warning("")
    logger.warning("=" * 70)
    logger.warning(" SENSOR CONNECTION TIMEOUT")
    logger.warning("=" * 70)
    logger.warning(f"Primary (w_back.txt): {'✓ CONNECTED' if primary_connected else '✗ NOT CONNECTED'}")
    logger.warning(f"Backup (Orientation.txt): {'✓ CONNECTED' if backup_connected else '✗ NOT CONNECTED'}")
    logger.warning("=" * 70)
    logger.warning("")

    if primary_connected or backup_connected:
        logger.warning("At least one sensor connected - continuing anyway")
        return True
    else:
        logger.error("NO SENSORS CONNECTED - cannot continue")
        return False


async def sensor_calibration_mode():
    """
    Continuous sensor monitoring with bulb feedback
    - Both bulbs stay ON
    - Bulb_1 blinks when angle < DOWN threshold
    - Bulb_2 blinks when angle > UP threshold
    - Print angles every 2 seconds
    - Wait for TWO button presses (10-second timeout after first press)
    """
    logger.info("=" * 70)
    logger.info(" SENSOR CALIBRATION MODE")
    logger.info("=" * 70)
    logger.info("Monitoring sensors... Bulbs will blink at threshold crossings")
    logger.info("Angles printed every 2 seconds")
    logger.info("Press ANY button to begin")
    logger.info("=" * 70)
    logger.info("")

    # Turn on both bulbs (they stay on throughout calibration)
    await bulb_1_control("on")
    await bulb_2_control("on")

    # Initialize button state - GIVE IT TIME TO READ FIRST
    await asyncio.sleep(0.5)  # ADD THIS
    last_button_1_value = await read_button(BUTTON_1)
    last_button_2_value = await read_button(BUTTON_2)

    # Log initial button values for debugging
    logger.info(f"Initial button states: Button1={last_button_1_value}, Button2={last_button_2_value}")

    # Track threshold crossings to avoid repeated blinks
    last_was_down = False
    last_was_up = False

    # State machine
    waiting_for_first = True
    waiting_for_second = False
    second_press_deadline = 0

    # Print timing
    last_print_time = 0
    print_interval = 2.0  # Print every 2 seconds

    while True:
        try:
            current_time = asyncio.get_event_loop().time()

            # Get sensor data
            angles = sensor_queue.get_all_angles()
            states = {
                'w_back.txt': sensor_queue.get_sensor_state('w_back.txt'),
                'Orientation.txt': sensor_queue.get_sensor_state('Orientation.txt')
            }

            # Print sensor data every 2 seconds
            if current_time - last_print_time >= print_interval:
                primary_angle = angles.get('w_back.txt', None)
                backup_angle = angles.get('Orientation.txt', None)

                print(
                    f"[Primary: w_back.txt] Angle: {primary_angle if primary_angle else 'N/A':>6}° [{states['w_back.txt'].value:>12}]  |  "
                    f"[Backup: Orientation.txt] Angle: {backup_angle if backup_angle else 'N/A':>6}° [{states['Orientation.txt'].value:>12}]")

                last_print_time = current_time

            # Determine which sensor to use for threshold checking
            primary_angle = angles.get('w_back.txt', None)
            backup_angle = angles.get('Orientation.txt', None)
            active_angle = primary_angle if primary_angle is not None else backup_angle

            if active_angle is not None:
                # Check DOWN threshold (blink Bulb_1)
                is_down = active_angle < ANGLE_DOWN_THRESHOLD
                if is_down and not last_was_down:
                    # Just crossed into down
                    logger.info(f"✓ DOWN threshold crossed ({active_angle:.1f}°) - Bulb 1 blink")
                    await bulb_1_control("off")
                    await asyncio.sleep(0.3)
                    await bulb_1_control("on")
                last_was_down = is_down

                # Check UP threshold (blink Bulb_2)
                is_up = active_angle > ANGLE_UP_THRESHOLD
                if is_up and not last_was_up:
                    # Just crossed into up
                    logger.info(f"✓ UP threshold crossed ({active_angle:.1f}°) - Bulb 2 blink")
                    await bulb_2_control("off")
                    await asyncio.sleep(0.3)
                    await bulb_2_control("on")
                last_was_up = is_up

            # Check for button presses
            current_button_1 = await read_button(BUTTON_1)
            current_button_2 = await read_button(BUTTON_2)

            button_pressed = False
            button_name = ""

            # Check Button 1
            if current_button_1 is not None and last_button_1_value is not None:
                if current_button_1 > last_button_1_value:
                    button_pressed = True
                    button_name = "Button 1"
                    logger.debug(f"Button 1: {last_button_1_value} → {current_button_1}")
                    last_button_1_value = current_button_1

            # Check Button 2
            if current_button_2 is not None and last_button_2_value is not None:
                if current_button_2 > last_button_2_value:
                    button_pressed = True
                    button_name = "Button 2"
                    logger.debug(f"Button 2: {last_button_2_value} → {current_button_2}")
                    last_button_2_value = current_button_2

            # Update last values (even if None - keep trying)
            if current_button_1 is not None:
                last_button_1_value = current_button_1
            if current_button_2 is not None:
                last_button_2_value = current_button_2

            # State machine logic
            if button_pressed:
                if waiting_for_first:
                    # First button press
                    logger.info("")
                    logger.info("=" * 70)
                    logger.info(f"{button_name} pressed! (1/2)")
                    logger.info("Press again within 10 seconds to confirm")
                    logger.info("=" * 70)
                    logger.info("")

                    play_first_press()

                    waiting_for_first = False
                    waiting_for_second = True
                    second_press_deadline = asyncio.get_event_loop().time() + 10

                elif waiting_for_second:
                    # Second button press - exit calibration
                    logger.info("")
                    logger.info("=" * 70)
                    logger.info(f"{button_name} pressed! (2/2)")
                    logger.info("Starting game...")
                    logger.info("=" * 70)
                    logger.info("")

                    play_second_press()

                    # Exit calibration mode
                    break

            # Check timeout for second press
            if waiting_for_second:
                if asyncio.get_event_loop().time() > second_press_deadline:
                    logger.info("")
                    logger.info("=" * 70)
                    logger.info("Timeout - press button to restart")
                    logger.info("=" * 70)
                    logger.info("")

                    # Reset to waiting for first press
                    waiting_for_first = True
                    waiting_for_second = False

            await asyncio.sleep(0.1)  # 10Hz update

        except KeyboardInterrupt:
            logger.info("\n\nCalibration interrupted")
            raise
        except Exception as e:
            logger.error(f"Error in calibration mode: {e}", exc_info=True)
            await asyncio.sleep(1)

    # Rest of function continues...

    # Two button presses received - prepare for game start
    logger.info("=" * 70)
    logger.info(" PREPARING GAME START")
    logger.info("=" * 70)

    # Turn on white noise
    try:
        from audio import start_white_noise
        start_white_noise()
        logger.info("White noise ON")
    except Exception as e:
        logger.warning(f"Failed to start white noise: {e}")

    # Turn off all lights
    await all_bulbs_off()
    logger.info("All lights OFF")

    # Wait before first round (shorter in testing mode)
    if TESTING_MODE:
        wait_time = random.randint(PREGAME_WAIT_MIN_TESTING, PREGAME_WAIT_MAX_TESTING)
        logger.info(f"[TESTING MODE] Waiting {wait_time} seconds before first round...")
    else:
        wait_time = random.randint(PREGAME_WAIT_MIN, PREGAME_WAIT_MAX)
        logger.info(f"Waiting {wait_time} seconds before first round...")

    logger.info("")

    # Wait with progress updates
    elapsed = 0
    update_interval = 5 if TESTING_MODE else 30  # More frequent updates in testing

    while elapsed < wait_time:
        await asyncio.sleep(min(update_interval, wait_time - elapsed))
        elapsed += update_interval
        if elapsed < wait_time:
            remaining = wait_time - elapsed
            logger.info(f"  {remaining} seconds until preparation phase...")

    # Stop white noise
    try:
        from audio import stop_white_noise
        stop_white_noise()
    except Exception as e:
        logger.warning(f"Failed to stop white noise: {e}")

    logger.info("")
    logger.info("Preparation phase starting in 15 seconds...")
    logger.info("")


async def emergency_cleanup():
    """
    Emergency cleanup - runs on ANY exit
    This MUST succeed to ensure safety
    """
    try:
        logger.critical("EMERGENCY CLEANUP INITIATED")

        # Stop all hardware monitoring
        try:
            stop_hardware_monitoring()
        except:
            pass

        # Turn on plug (critical safety signal)
        try:
            await plug_control("on")
            logger.critical("✓ Plug activated")
        except Exception as e:
            logger.critical(f"✗ Plug activation failed: {e}")

        # Turn on all lights (visual signal)
        try:
            await all_bulbs_on()
            logger.critical("✓ All bulbs ON")
        except Exception as e:
            logger.critical(f"✗ Bulb activation failed: {e}")

        # Stop white noise if running
        try:
            stop_white_noise()
        except:
            pass

        # Stop audio system
        try:
            audio_manager.cleanup()
        except:
            pass

        logger.critical("EMERGENCY CLEANUP COMPLETE")
    except Exception as e:
        logger.critical(f"EMERGENCY CLEANUP ERROR: {e}")
        # Even if logging fails, try to activate plug
        try:
            await plug_control("on")
        except:
            pass


def sync_emergency_cleanup():
    """Synchronous wrapper for emergency cleanup (for atexit)"""
    try:
        asyncio.run(emergency_cleanup())
    except:
        # If async fails, try direct hardware control
        import requests
        try:
            requests.get(f"http://192.168.1.195/relay/0?turn=on", timeout=2)
        except:
            pass


# Register emergency cleanup on program exit
atexit.register(sync_emergency_cleanup)


# Register signal handlers for Ctrl+C, kill, etc.
def signal_handler(signum, frame):
    logger.critical(f"Signal {signum} received - emergency cleanup")
    sync_emergency_cleanup()
    sys.exit(1)


signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # kill command
async def main():
    """Main entry point with bulletproof cleanup"""
    game = None
    sensor_task = None

    try:
        logger.info("=" * 70)
        logger.info(" UP/DOWN TRAINING GAME - PHASE 1: CORE INFRASTRUCTURE")
        logger.info("=" * 70)
        logger.info("")

        # Show configuration
        logger.info("Configuration:")
        logger.info(f"  Testing mode: {'ENABLED' if TESTING_MODE else 'DISABLED'}")
        logger.info(f"  Game duration: {GAME_DURATION_HOURS} hours")
        logger.info(f"  Training time: {TRAINING_TIME_MIN / 60:.0f}-{TRAINING_TIME_MAX / 60:.0f} minutes")
        logger.info(f"  Round duration: {ROUND_DURATION_MIN}-{ROUND_DURATION_MAX} seconds")
        logger.info(f"  Break duration: {BREAK_DURATION_MIN}-{BREAK_DURATION_MAX} seconds")
        logger.info(f"  Sensor patience: {SENSOR_PATIENCE_TIME / 3600:.1f} hours")
        logger.info("")

        # Test PiShock with vibration
        logger.info("Testing PiShock...")
        result = await send_vibration()
        logger.info(f"  {'✓ SUCCESS' if result else '✗ FAILED (will retry during game)'}")
        logger.info("")

        # Start sensor system in background
        logger.info("Starting sensor system...")
        sensor_task = asyncio.create_task(sensor_main())

        # Wait for sensors to connect with confirmation
        await asyncio.sleep(2)  # Give scan time to start
        sensors_ok = await wait_for_sensors()

        if not sensors_ok:
            logger.critical("Cannot start without sensors - exiting")
            if sensor_task:
                sensor_task.cancel()
            return

        # Enter sensor calibration mode
        # Waits for 2 button presses (with 10-sec timeout), then prepares for game
        await sensor_calibration_mode()
        set_angle_printing(False)
        logger.info("✓ Continuous angle printing disabled - showing events only")
        # Initialize game
        logger.info("Initializing game...")
        game = UpDownGame()
        game.is_running = True

        # Mark game as started and set times
        # Start hardware monitoring FIRST
        start_hardware_monitoring()
        logger.info("✓ Hardware monitoring active")
        logger.info("")

        # Start the game (this handles video + prep internally)
        logger.info("=" * 70)
        logger.info(" STARTING GAME")
        logger.info("=" * 70)
        logger.info("")

        await game.start_game()
        # Start game loop (it will continue from preparation into rounds)
        try:
            await game_loop(game)
        except KeyboardInterrupt:
            logger.info("")
            logger.info("Game interrupted by user")
        except Exception as e:
            logger.critical(f"Fatal error in game loop: {e}", exc_info=True)

    except Exception as e:
        logger.critical(f"Fatal startup error: {e}", exc_info=True)

    finally:
        # CLEANUP - THIS MUST ALWAYS RUN
        logger.critical("=" * 70)
        logger.critical(" STARTING CLEANUP SEQUENCE")
        logger.critical("=" * 70)

        try:
            # Stop game
            if game:
                game.is_running = False
                logger.info("✓ Game stopped")
        except Exception as e:
            logger.error(f"Error stopping game: {e}")

        try:
            # Stop hardware monitoring
            stop_hardware_monitoring()
            logger.info("✓ Hardware monitoring stopped")
        except Exception as e:
            logger.error(f"Error stopping hardware monitoring: {e}")

        try:
            # Stop sensors
            if sensor_task:
                sensor_task.cancel()
                logger.info("✓ Sensor task cancelled")
        except Exception as e:
            logger.error(f"Error cancelling sensor task: {e}")

        try:
            # Stop audio
            audio_manager.cleanup()
            logger.info("✓ Audio cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up audio: {e}")

        try:
            # CRITICAL: Activate safety signals
            await all_bulbs_on()
            logger.critical("✓ All bulbs turned ON")
        except Exception as e:
            logger.critical(f"✗ Failed to turn on bulbs: {e}")

        try:
            await plug_control("on")
            logger.critical("✓ Plug activated")
        except Exception as e:
            logger.critical(f"✗ Failed to activate plug: {e}")

        logger.critical("=" * 70)
        logger.critical(" CLEANUP COMPLETE")
        logger.critical("=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nEXITING - Emergency cleanup...")
        sync_emergency_cleanup()
    except Exception as e:
        logger.critical(f"Top-level error: {e}", exc_info=True)
        sync_emergency_cleanup()
    finally:
        print("\nProgram terminated.")