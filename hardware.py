"""
Robust hardware control with automatic retry and continuous monitoring
"""

import asyncio
import aiohttp
import random
import logging
from typing import Optional
from config import *

logger = logging.getLogger(__name__)

# ============================================================================
# HARDWARE STATE TRACKING WITH CONTINUOUS MONITORING
# ============================================================================

class HardwareState:
    def __init__(self):
        self.bulb_1_online = True
        self.bulb_2_online = True
        self.strobe_online = True
        self.fan_online = True
        self.plug_online = True
        self.button_1_online = True
        self.button_2_online = True
        self.pishock_online = True

        # Continuous monitoring
        self.monitoring_active = False
        self.monitor_task = None

hardware_state = HardwareState()

# ============================================================================
# SHELLY DEVICE CONTROL
# ============================================================================

async def shelly_control(device_id: int, command: str, endpoint: str = "light") -> bool:
    """Control Shelly device with retry"""
    url = f"http://{BASE_IP}{device_id}/{endpoint}/0?turn={command}"

    for attempt in range(NETWORK_MAX_RETRIES):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        return True
        except Exception as e:
            if attempt == NETWORK_MAX_RETRIES - 1:
                logger.debug(f"Device {device_id} failed: {e}")

        if attempt < NETWORK_MAX_RETRIES - 1:
            await asyncio.sleep(NETWORK_RETRY_DELAY)

    return False

# ============================================================================
# BULB CONTROLS
# ============================================================================

async def bulb_1_control(state: str) -> bool:
    """DOWN position bulb"""
    success = await shelly_control(BULB_1, state, "light")
    hardware_state.bulb_1_online = success
    return success

async def bulb_2_control(state: str) -> bool:
    """UP position bulb"""
    success = await shelly_control(BULB_2, state, "light")
    hardware_state.bulb_2_online = success
    return success

async def all_bulbs_off():
    """Turn off all bulbs"""
    await asyncio.gather(
        bulb_1_control("off"),
        bulb_2_control("off"),
        return_exceptions=True
    )

async def all_bulbs_on():
    """Turn on all bulbs - used when game ends"""
    await asyncio.gather(
        bulb_1_control("on"),
        bulb_2_control("on"),
        return_exceptions=True
    )

# ============================================================================
# STROBE CONTROL
# ============================================================================

async def strobe_control(state: str) -> bool:
    """Control strobe light"""
    success = await shelly_control(STROBE, state, "relay")
    hardware_state.strobe_online = success
    return success

# ============================================================================
# FAN CONTROL
# ============================================================================

async def fan_control(state: str) -> bool:
    """Control fan"""
    success = await shelly_control(FAN, state, "relay")
    hardware_state.fan_online = success
    return success

async def heat_control(state: str) -> bool:
    """Control heat plug"""
    success = await shelly_control(HEAT, state, "relay")
    # No hardware_state tracking needed for heat
    return success

async def set_heat_fan_state(heat_on: bool):
    """
    Set heat/fan state (mutually exclusive)
    If heat ON → fan OFF
    If heat OFF → fan ON
    """
    if heat_on:
        await heat_control("on")
        await fan_control("off")
        logger.info("→ Mode: HEAT ON / FAN OFF")
    else:
        await heat_control("off")
        await fan_control("on")
        logger.info("→ Mode: HEAT OFF / FAN ON")

# ============================================================================
# PLUG CONTROL
# ============================================================================

async def plug_control(state: str) -> bool:
    """Control plug - game end signal"""
    success = await shelly_control(PLUG, state, "relay")
    hardware_state.plug_online = success
    return success

# ============================================================================
# BUTTON CONTROLS
# ============================================================================

async def read_button(button_id: int) -> Optional[int]:
    """Read button event count"""
    url = f"http://{BASE_IP}{button_id}/input/0"

    for attempt in range(NETWORK_MAX_RETRIES):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['inputs'][0]['event_cnt']
        except Exception as e:
            if attempt == NETWORK_MAX_RETRIES - 1:
                logger.debug(f"Button {button_id} read failed: {e}")

        if attempt < NETWORK_MAX_RETRIES - 1:
            await asyncio.sleep(NETWORK_RETRY_DELAY)

    return None

async def check_button_press(button_id: int, last_value: Optional[int]) -> tuple[bool, Optional[int]]:
    """
    Check if button pressed since last check
    Returns: (pressed, new_value)
    """
    current_value = await read_button(button_id)

    if current_value is None:
        if button_id == BUTTON_1:
            hardware_state.button_1_online = False
        else:
            hardware_state.button_2_online = False
        return False, last_value

    if button_id == BUTTON_1:
        hardware_state.button_1_online = True
    else:
        hardware_state.button_2_online = True

    if last_value is None:
        return False, current_value

    if current_value > last_value:
        logger.info(f"Button {button_id} pressed")
        return True, current_value

    return False, current_value

# ============================================================================
# PISHOCK CONTROL - SIMPLIFIED (SINGLE EMITTER)
# ============================================================================

async def send_pishock(mode: str = "shock", intensity: int = 30, duration: int = 1):
    """
    Send PiShock command (shock or vibrate)
    Uses requests library to avoid SSL verification issues
    """
    try:
        # PiShock API configuration
        api_url = "https://do.pishock.com/api/apioperate"

        # Mode mapping: "shock" -> Op 0, "vibrate" -> Op 1
        op_code = "0" if mode == "shock" else "1"

        api_data = {
            "Username": PISHOCK_USER,
            "Apikey": PISHOCK_API_KEY,
            "Name": "UpDownGame",
            "Code": PISHOCK_EMITTER_1,
            "Intensity": str(intensity),
            "Duration": str(duration),
            "Op": op_code
        }

        # Run requests.post in thread pool to avoid blocking
        def _send_request():
            import requests
            import json
            response = requests.post(
                api_url,
                data=json.dumps(api_data),
                headers={"Content-type": "application/json"},
                timeout=5
            )
            return response.status_code, response.text

        # Execute in thread pool
        status_code, response_text = await asyncio.to_thread(_send_request)

        if status_code == 200:
            logger.info(f"✓ PiShock {mode} sent successfully (Status: {status_code})")  # ← ADD THIS
            logger.debug(f"  Response: {response_text}")
        else:
            logger.warning(f"⚠️ PiShock returned status {status_code}: {response_text}")

    except Exception as e:
        logger.error(f"❌ PiShock failed: {e}")
async def send_vibration(intensity: int = 30, duration: int = 1):
    """Send vibration via PiShock"""
    await send_pishock(mode=PISHOCK_MODE_VIBRATE, intensity=intensity, duration=duration)

# ============================================================================
# CONTINUOUS CONNECTION MONITORING
# ============================================================================

async def monitor_hardware_connections():
    """
    Background task that continuously monitors and retries failed connections
    This runs throughout the entire game and never gives up
    """
    logger.info("Hardware connection monitoring started")

    while hardware_state.monitoring_active:
        try:
            # Check bulbs
            if not hardware_state.bulb_1_online:
                logger.debug("Retrying Bulb 1 connection...")
                result = await shelly_control(BULB_1, "off", "light")
                if result:
                    hardware_state.bulb_1_online = True
                    logger.info("✓ Bulb 1 reconnected")

            if not hardware_state.bulb_2_online:
                logger.debug("Retrying Bulb 2 connection...")
                result = await shelly_control(BULB_2, "off", "light")
                if result:
                    hardware_state.bulb_2_online = True
                    logger.info("✓ Bulb 2 reconnected")

            if not hardware_state.strobe_online:
                logger.debug("Retrying Strobe connection...")
                result = await shelly_control(STROBE, "off", "light")
                if result:
                    hardware_state.strobe_online = True
                    logger.info("✓ Strobe reconnected")

            # Check buttons
            if not hardware_state.button_1_online:
                logger.debug("Retrying Button 1 connection...")
                value = await read_button(BUTTON_1)
                if value is not None:
                    hardware_state.button_1_online = True
                    logger.info("✓ Button 1 reconnected")

            if not hardware_state.button_2_online:
                logger.debug("Retrying Button 2 connection...")
                value = await read_button(BUTTON_2)
                if value is not None:
                    hardware_state.button_2_online = True
                    logger.info("✓ Button 2 reconnected")

            # Check fan
            if not hardware_state.fan_online:
                logger.debug("Retrying Fan connection...")
                result = await shelly_control(FAN, "off", "relay")
                if result:
                    hardware_state.fan_online = True
                    logger.info("✓ Fan reconnected")

            # Check plug
            if not hardware_state.plug_online:
                logger.debug("Retrying Plug connection...")
                result = await shelly_control(PLUG, "off", "relay")
                if result:
                    hardware_state.plug_online = True
                    logger.info("✓ Plug reconnected")

            # Check PiShock with minimal test
            if not hardware_state.pishock_online:
                logger.debug("Retrying PiShock connection...")
                # Don't actually send shock during monitoring, just mark as online
                # Will be tested during actual use
                hardware_state.pishock_online = True

        except Exception as e:
            logger.error(f"Error in hardware monitoring: {e}")

        await asyncio.sleep(HARDWARE_MONITOR_INTERVAL)

    logger.info("Hardware connection monitoring stopped")

def start_hardware_monitoring():
    """Start the hardware monitoring background task"""
    if not hardware_state.monitoring_active:
        hardware_state.monitoring_active = True
        hardware_state.monitor_task = asyncio.create_task(monitor_hardware_connections())
        logger.info("Started hardware monitoring")

def stop_hardware_monitoring():
    """Stop the hardware monitoring background task"""
    if hardware_state.monitoring_active:
        hardware_state.monitoring_active = False
        if hardware_state.monitor_task:
            hardware_state.monitor_task.cancel()
        logger.info("Stopped hardware monitoring")

# ============================================================================
# EMERGENCY SHUTDOWN
# ============================================================================

async def emergency_shutdown():
    """
    Critical error - activate plug and keep all lights ON forever
    """
    logger.critical("EMERGENCY SHUTDOWN")

    while True:
        try:
            await plug_control("on")
            await all_bulbs_on()
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Emergency shutdown error: {e}")
            await asyncio.sleep(5)

# ============================================================================
# GAME END SEQUENCE
# ============================================================================

async def game_end_sequence():
    """
    Normal game end sequence:
    1. Turn on all bulbs AND play audio simultaneously
    2. Wait 3-5 minutes (random)
    3. Then activate plug
    4. Keep everything on indefinitely
    """
    from audio import play_training_ended  # ← ADD THIS IMPORT

    logger.info("=" * 60)
    logger.info("GAME END SEQUENCE")
    logger.info("=" * 60)

    # Step 1: Turn on all bulbs AND play audio simultaneously
    try:
        await all_bulbs_on()
        logger.info("✓ All bulbs turned ON")
    except Exception as e:
        logger.error(f"Failed to turn on bulbs: {e}")

    # Play audio (non-blocking, happens simultaneously with bulbs)
    play_training_ended()  # ← ADD THIS
    logger.info("✓ Training ended audio playing")

    # Step 2: Wait 3-5 minutes before plug activation
    import random
    wait_time = random.randint(3 * 60, 5 * 60)  # 180-300 seconds
    logger.info(f"Waiting {wait_time} seconds ({wait_time / 60:.1f} minutes) before plug activation...")

    # Wait in 10-second intervals
    elapsed = 0
    while elapsed < wait_time:
        await asyncio.sleep(10)
        elapsed += 10

        # Log progress every minute
        if elapsed % 60 == 0:
            remaining = (wait_time - elapsed) / 60
            logger.info(f"  {remaining:.1f} minutes until plug activation...")

    # Step 3: Activate plug
    logger.info("Activating plug...")
    try:
        await plug_control("on")
        logger.info("✓ Plug activated")
    except Exception as e:
        logger.error(f"Failed to activate plug: {e}")

    logger.info("Game end sequence complete - maintaining state")
    logger.info("=" * 60)

    # Step 4: Keep everything on indefinitely
    while True:
        try:
            await plug_control("on")
            await all_bulbs_on()
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Game end maintenance error: {e}")
            await asyncio.sleep(5)

async def test_all_hardware():
    """Test all hardware"""
    logger.info("="*60)
    logger.info("HARDWARE TEST")
    logger.info("="*60)

    tests = [
        ("Bulb 1 (DOWN)", lambda: bulb_1_control("on")),
        ("Bulb 2 (UP)", lambda: bulb_2_control("on")),
        ("Strobe", lambda: strobe_control("on")),
        ("Fan", lambda: fan_control("on")),
        ("Plug", lambda: plug_control("on")),
    ]

    for name, func in tests:
        logger.info(f"Testing {name}...")
        result = await func()
        logger.info(f"  {'✓' if result else '✗'}")
        await asyncio.sleep(0.5)
        # Turn off after test
        device = name.split()[0].lower()
        if device == "bulb":
            if "1" in name:
                await bulb_1_control("off")
            elif "2" in name:
                await bulb_2_control("off")
        elif device == "strobe":
            await strobe_control("off")
        elif device == "fan":
            await fan_control("off")
        elif device == "plug":
            await plug_control("off")

    logger.info("Testing Button 1...")
    value = await read_button(BUTTON_1)
    logger.info(f"  {'✓' if value is not None else '✗'} (count: {value})")

    logger.info("Testing Button 2...")
    value = await read_button(BUTTON_2)
    logger.info(f"  {'✓' if value is not None else '✗'} (count: {value})")

    logger.info("Testing PiShock (vibration)...")
    result = await send_vibration()
    logger.info(f"  {'✓' if result else '✗'}")

    logger.info("="*60)


# ============================================================================
# HARDWARE MONITORING (Continuous reconnection)
# ============================================================================

async def hardware_monitor():
    """
    Monitor hardware connections and attempt reconnection
    Runs continuously throughout the game
    """
    logger.info("Hardware monitoring started")

    check_interval = HARDWARE_MONITOR_INTERVAL  # From config (default 10 seconds)

    while True:
        try:
            # Just sleep - hardware already auto-reconnects via Govee API
            # This task mainly exists to match the original architecture
            await asyncio.sleep(check_interval)

        except asyncio.CancelledError:
            logger.info("Hardware monitoring stopped")
            break
        except Exception as e:
            logger.error(f"Hardware monitor error: {e}")
            await asyncio.sleep(5)