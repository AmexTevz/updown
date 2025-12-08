#!/usr/bin/env python3
"""
Hardware Testing Script
Test each hardware component individually
"""

import asyncio
import logging
import sys
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Import hardware controls

from config import *
from hardware import *


# Import sensor system

from main_wit import sensor_queue, scan, connect_to_devices


# ============================================================================
# INDIVIDUAL TESTS
# ============================================================================

async def test_bulb_1():
    """Test Bulb 1 (DOWN position)"""
    print("\n" + "=" * 60)
    print("TESTING BULB 1 (DOWN POSITION)")
    print(f"IP: {BASE_IP}{BULB_1}")
    print("=" * 60)

    print("Turning ON...")
    result = await bulb_1_control("on")
    print(f"Result: {'✓ SUCCESS' if result else '✗ FAILED'}")

    await asyncio.sleep(2)

    print("Turning OFF...")
    result = await bulb_1_control("off")
    print(f"Result: {'✓ SUCCESS' if result else '✗ FAILED'}")


async def test_bulb_2():
    """Test Bulb 2 (UP position)"""
    print("\n" + "=" * 60)
    print("TESTING BULB 2 (UP POSITION)")
    print(f"IP: {BASE_IP}{BULB_2}")
    print("=" * 60)

    print("Turning ON...")
    result = await bulb_2_control("on")
    print(f"Result: {'✓ SUCCESS' if result else '✗ FAILED'}")

    await asyncio.sleep(2)

    print("Turning OFF...")
    result = await bulb_2_control("off")
    print(f"Result: {'✓ SUCCESS' if result else '✗ FAILED'}")


async def test_bulb_3():
    """Test Bulb 3 (Verification)"""
    print("\n" + "=" * 60)
    print("TESTING BULB 3 (VERIFICATION)")
    print(f"IP: {BASE_IP}{BULB_3}")
    print("=" * 60)

    print("Testing blink (1 second ON, then OFF)...")
    await bulb_3_blink()
    print("✓ Blink complete")

    await asyncio.sleep(1)

    print("Testing 3 blinks...")
    for i in range(3):
        print(f"  Blink {i + 1}...")
        await bulb_3_blink()
        await asyncio.sleep(0.5)
    print("✓ Complete")


async def test_all_bulbs():
    """Test all bulbs together"""
    print("\n" + "=" * 60)
    print("TESTING ALL BULBS")
    print("=" * 60)

    print("Turning all bulbs ON...")
    await all_bulbs_on()
    await asyncio.sleep(2)

    print("Turning all bulbs OFF...")
    await all_bulbs_off()
    print("✓ Complete")


async def test_strobe():
    """Test strobe light"""
    print("\n" + "=" * 60)
    print("TESTING STROBE LIGHT")
    print(f"IP: {BASE_IP}{STROBE}")
    print("=" * 60)

    print("Turning ON for 3 seconds...")
    result = await strobe_control("on")
    print(f"Result: {'✓ SUCCESS' if result else '✗ FAILED'}")

    await asyncio.sleep(3)

    print("Turning OFF...")
    result = await strobe_control("off")
    print(f"Result: {'✓ SUCCESS' if result else '✗ FAILED'}")


async def test_fan():
    """Test fan control"""
    print("\n" + "=" * 60)
    print("TESTING FAN")
    print(f"IP: {BASE_IP}{FAN}")
    print("=" * 60)

    print("Turning ON for 3 seconds...")
    result = await fan_control("on")
    print(f"Result: {'✓ SUCCESS' if result else '✗ FAILED'}")

    await asyncio.sleep(3)

    print("Turning OFF...")
    result = await fan_control("off")
    print(f"Result: {'✓ SUCCESS' if result else '✗ FAILED'}")


async def test_plug():
    """Test plug control"""
    print("\n" + "=" * 60)
    print("TESTING PLUG CONTROL")
    print(f"IP: {BASE_IP}{PLUG}")
    print("=" * 60)

    print("Turning ON for 2 seconds...")
    result = await plug_control("on")
    print(f"Result: {'✓ SUCCESS' if result else '✗ FAILED'}")

    await asyncio.sleep(2)

    print("Turning OFF...")
    result = await plug_control("off")
    print(f"Result: {'✓ SUCCESS' if result else '✗ FAILED'}")


async def test_button_1():
    """Test Button 1"""
    print("\n" + "=" * 60)
    print("TESTING BUTTON 1")
    print(f"IP: {BASE_IP}{BUTTON_1}")
    print("=" * 60)

    print("Reading current value...")
    value = await read_button(BUTTON_1)

    if value is None:
        print("✗ FAILED - Cannot read button")
        return

    print(f"Current count: {value}")
    print("\nPress Button 1 now...")
    print("Monitoring for 10 seconds...")

    last_value = value
    start_time = asyncio.get_event_loop().time()

    while asyncio.get_event_loop().time() - start_time < 10:
        current_value = await read_button(BUTTON_1)

        if current_value is not None and current_value > last_value:
            print(f"✓ BUTTON PRESSED! Count: {last_value} → {current_value}")
            last_value = current_value

        await asyncio.sleep(0.2)

    print("Monitoring complete")


async def test_button_2():
    """Test Button 2"""
    print("\n" + "=" * 60)
    print("TESTING BUTTON 2")
    print(f"IP: {BASE_IP}{BUTTON_2}")
    print("=" * 60)

    print("Reading current value...")
    value = await read_button(BUTTON_2)

    if value is None:
        print("✗ FAILED - Cannot read button")
        return

    print(f"Current count: {value}")
    print("\nPress Button 2 now...")
    print("Monitoring for 10 seconds...")

    last_value = value
    start_time = asyncio.get_event_loop().time()

    while asyncio.get_event_loop().time() - start_time < 10:
        current_value = await read_button(BUTTON_2)

        if current_value is not None and current_value > last_value:
            print(f"✓ BUTTON PRESSED! Count: {last_value} → {current_value}")
            last_value = current_value

        await asyncio.sleep(0.2)

    print("Monitoring complete")


async def test_pishock():
    """Test PiShock"""
    print("\n" + "=" * 60)
    print("TESTING PISHOCK")
    print("=" * 60)

    print("Available tests:")
    print("1. Vibration (safe)")
    print("2. Shock (intensity 60)")
    print("3. Shock (intensity 80)")
    print("4. Shock (intensity 100)")
    print("0. Cancel")

    choice = input("\nSelect test (0-4): ").strip()

    if choice == "0":
        print("Cancelled")
        return

    if choice == "1":
        print("\nSending VIBRATION...")
        result = await send_pishock(mode=PISHOCK_MODE_VIBRATE, intensity=70, duration=1)
    elif choice == "2":
        print("\nSending SHOCK (intensity 60)...")
        result = await send_pishock(mode=PISHOCK_MODE_SHOCK, intensity=60, duration=1)
    elif choice == "3":
        print("\nSending SHOCK (intensity 80)...")
        result = await send_pishock(mode=PISHOCK_MODE_SHOCK, intensity=80, duration=1)
    elif choice == "4":
        print("\nSending SHOCK (intensity 100)...")
        result = await send_pishock(mode=PISHOCK_MODE_SHOCK, intensity=100, duration=1)
    else:
        print("Invalid choice")
        return

    print(f"Result: {'✓ SUCCESS' if result else '✗ FAILED'}")


async def test_sensors():
    """Test sensors"""
    print("\n" + "=" * 60)
    print("TESTING SENSORS")
    print("=" * 60)

    if sensor_queue is None:
        print("✗ Sensor system not available")
        print("Make sure main_wit.py is in the directory")
        return

    print("Scanning for sensors...")
    devices = await scan()

    if not devices:
        print("✗ No sensors found")
        return

    print(f"\n✓ Found {len(devices)} sensor(s):")
    for device in devices:
        print(f"  - {device.name} ({device.address})")

    print("\nStarting sensor connection...")
    print("This will run for 10 seconds to collect data")

    # Start sensor connection in background
    sensor_task = asyncio.create_task(connect_to_devices(devices))

    # Give sensors time to connect
    await asyncio.sleep(3)

    # Monitor for 10 seconds
    print("\nMonitoring sensor data...")
    start_time = asyncio.get_event_loop().time()

    while asyncio.get_event_loop().time() - start_time < 10:
        angles = sensor_queue.get_all_angles()
        states = {
            'w_back.txt': sensor_queue.get_sensor_state('w_back.txt'),
            'Orientation.txt': sensor_queue.get_sensor_state('Orientation.txt')
        }

        print("\rSensors: ", end="")
        print(f"Primary={angles.get('w_back.txt', 'N/A')}° [{states['w_back.txt'].value}]  ", end="")
        print(f"Backup={angles.get('Orientation.txt', 'N/A')}° [{states['Orientation.txt'].value}]  ", end="")

        await asyncio.sleep(0.5)

    print("\n\nStopping sensors...")
    sensor_task.cancel()
    print("✓ Complete")


# ============================================================================
# SEQUENCE TESTS
# ============================================================================

async def test_preparation_sequence():
    """Test preparation phase sequence"""
    print("\n" + "=" * 60)
    print("TESTING PREPARATION SEQUENCE")
    print("=" * 60)
    print("\nThis simulates the 15-second preparation phase:")
    print("- All bulbs OFF")
    print("- Strobe ON")
    print("- Vibration sent")
    print("- Wait 15 seconds")
    print("- Strobe OFF")
    print("\nStarting in 3 seconds...")
    await asyncio.sleep(3)

    print("\n[PREPARATION START]")

    # Turn off all bulbs
    print("  - Bulbs OFF")
    await all_bulbs_off()

    # Turn on strobe
    print("  - Strobe ON")
    await strobe_control("on")

    # Send vibration
    print("  - Vibration sent")
    await send_vibration()

    # Wait 15 seconds
    print("  - Waiting 15 seconds...")
    for i in range(15, 0, -1):
        print(f"    {i}...", end="\r")
        await asyncio.sleep(1)

    # Turn off strobe
    print("\n  - Strobe OFF")
    await strobe_control("off")

    print("\n[PREPARATION COMPLETE]")


async def test_round_sequence():
    """Test basic round sequence"""
    print("\n" + "=" * 60)
    print("TESTING ROUND SEQUENCE")
    print("=" * 60)
    print("\nThis simulates a short round:")
    print("- Command DOWN (Bulb 1 ON, audio)")
    print("- Wait 5 seconds")
    print("- Command UP (Bulb 2 ON, audio)")
    print("- Wait 5 seconds")
    print("- Command DOWN")
    print("- Wait 5 seconds")
    print("- Round end (vibration)")
    print("\nStarting in 3 seconds...")
    await asyncio.sleep(3)

    print("\n[ROUND START]")

    # DOWN
    print("  - Command: DOWN")
    await bulb_1_control("on")
    await bulb_2_control("off")
    print("    (Bulb 1 ON)")
    await asyncio.sleep(5)

    # UP
    print("  - Command: UP")
    await bulb_1_control("off")
    await bulb_2_control("on")
    print("    (Bulb 2 ON)")
    await asyncio.sleep(5)

    # DOWN
    print("  - Command: DOWN")
    await bulb_1_control("on")
    await bulb_2_control("off")
    print("    (Bulb 1 ON)")
    await asyncio.sleep(5)

    # End
    print("  - Round ending...")
    await all_bulbs_off()
    await send_vibration()
    print("    (Vibration sent)")

    print("\n[ROUND COMPLETE]")


async def test_game_end_sequence():
    """Test game end sequence"""
    print("\n" + "=" * 60)
    print("TESTING GAME END SEQUENCE")
    print("=" * 60)
    print("\nThis simulates game end:")
    print("- Plug ON")
    print("- All bulbs ON")
    print("- Stay on for 10 seconds")
    print("\nStarting in 3 seconds...")
    await asyncio.sleep(3)

    print("\n[GAME END]")

    print("  - Activating plug...")
    await plug_control("on")

    print("  - All bulbs ON...")
    await all_bulbs_on()

    print("  - Holding for 10 seconds...")
    await asyncio.sleep(10)

    print("  - Turning OFF...")
    await plug_control("off")
    await all_bulbs_off()

    print("\n[TEST COMPLETE]")


# ============================================================================
# MAIN MENU
# ============================================================================

async def main_menu():
    """Main test menu"""

    while True:
        print("\n" + "=" * 70)
        print(" HARDWARE TEST MENU")
        print("=" * 70)
        print("\nIndividual Component Tests:")
        print("  1. Test Bulb 1 (DOWN position)")
        print("  2. Test Bulb 2 (UP position)")
        print("  3. Test Bulb 3 (Verification - blink)")
        print("  4. Test All Bulbs")
        print("  5. Test Strobe Light")
        print("  6. Test Fan")
        print("  7. Test Plug Control")
        print("  8. Test Button 1")
        print("  9. Test Button 2")
        print(" 10. Test PiShock")
        print(" 11. Test Sensors")
        print("\nSequence Tests:")
        print(" 20. Test Preparation Sequence")
        print(" 21. Test Round Sequence")
        print(" 22. Test Game End Sequence")
        print("\nOther:")
        print(" 99. Test ALL Hardware (full test)")
        print("  0. Exit")

        choice = input("\nSelect test: ").strip()

        if choice == "0":
            print("\nExiting...")
            break

        try:
            if choice == "1":
                await test_bulb_1()
            elif choice == "2":
                await test_bulb_2()
            elif choice == "3":
                await test_bulb_3()
            elif choice == "4":
                await test_all_bulbs()
            elif choice == "5":
                await test_strobe()
            elif choice == "6":
                await test_fan()
            elif choice == "7":
                await test_plug()
            elif choice == "8":
                await test_button_1()
            elif choice == "9":
                await test_button_2()
            elif choice == "10":
                await test_pishock()
            elif choice == "11":
                await test_sensors()
            elif choice == "20":
                await test_preparation_sequence()
            elif choice == "21":
                await test_round_sequence()
            elif choice == "22":
                await test_game_end_sequence()
            elif choice == "99":
                await test_all_hardware()
            else:
                print("\n✗ Invalid choice")

        except Exception as e:
            logger.error(f"Test error: {e}", exc_info=True)

        input("\nPress Enter to continue...")


# ============================================================================
# ENTRY POINT
# ============================================================================

async def main():
    """Entry point"""
    print("=" * 70)
    print(" HARDWARE TESTING UTILITY")
    print("=" * 70)
    print()
    print("This utility allows you to test each hardware component individually")
    print()

    await main_menu()

    print("\nCleaning up...")
    # Make sure everything is off
    await all_bulbs_off()
    await strobe_control("off")
    await fan_control("off")
    await plug_control("off")
    print("✓ Cleanup complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)