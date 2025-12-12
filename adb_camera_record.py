#!/usr/bin/env python3
"""
Android Camera Video Recording via ADB
Auto-records 5 minutes of video using method 3 (KEYCODE_ENTER)
No prompts - runs immediately
"""

import subprocess
import time
import sys
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
RECORDING_DURATION = 5  # 5 minutes in seconds


class ADBCameraController:
    """Control Android camera via ADB"""

    def __init__(self, device_id=None):
        self.device_id = device_id
        self.adb_prefix = ['adb']
        if device_id:
            self.adb_prefix = ['adb', '-s', device_id]

    def run_adb(self, command, capture_output=True):
        """Run ADB command"""
        if isinstance(command, str):
            command = command.split()

        full_command = self.adb_prefix + command

        try:
            result = subprocess.run(
                full_command,
                capture_output=capture_output,
                text=True,
                timeout=30
            )
            return result
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {' '.join(full_command)}")
            return None
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return None

    def check_adb_available(self):
        """Check if ADB is installed and available"""
        try:
            result = subprocess.run(
                ['adb', 'version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False

    def check_device_connected(self):
        """Check if Android device is connected"""
        result = self.run_adb(['devices'])

        if not result or result.returncode != 0:
            return False

        lines = result.stdout.strip().split('\n')[1:]
        devices = [line.split('\t') for line in lines if line.strip()]

        if not devices:
            logger.error("✗ No devices connected")
            return False

        logger.info(f"✓ Found {len(devices)} device(s) connected")
        return True

    def wake_screen(self):
        """Wake up device screen"""
        logger.info("Waking screen...")
        self.run_adb(['shell', 'input', 'keyevent', 'KEYCODE_WAKEUP'])
        time.sleep(0.5)

    def stop_camera_app(self):
        """Force stop camera app to ensure clean state"""
        logger.info("Stopping any running camera app...")

        camera_packages = [
            'com.android.camera',
            'com.android.camera2',
            'com.google.android.GoogleCamera',
            'com.samsung.android.camera',
            'com.motorola.camera2',
            'com.huawei.camera',
        ]

        for package in camera_packages:
            self.run_adb(['shell', 'am', 'force-stop', package])

        time.sleep(1)

    def launch_camera_video_mode(self):
        """Launch camera app in video mode"""
        logger.info("Launching camera in video mode...")

        result = self.run_adb([
            'shell', 'am', 'start',
            '-a', 'android.media.action.VIDEO_CAPTURE'
        ])

        time.sleep(3)  # Wait for camera to initialize
        return True

    def start_recording(self):
        """Start recording using KEYCODE_ENTER"""
        logger.info("Starting recording (KEYCODE_ENTER)...")
        self.run_adb(['shell', 'input', 'keyevent', 'KEYCODE_ENTER'])
        time.sleep(1)

    def stop_recording(self):
        """Stop recording using KEYCODE_ENTER"""
        logger.info("Stopping recording (KEYCODE_ENTER)...")
        self.run_adb(['shell', 'input', 'keyevent', 'KEYCODE_ENTER'])
        time.sleep(1)

    def go_home(self):
        """Return to home screen"""
        logger.info("Returning to home screen...")
        self.run_adb(['shell', 'input', 'keyevent', 'KEYCODE_HOME'])
        time.sleep(0.5)

    def record_video(self, duration):
        """Record video for specified duration"""
        logger.info("=" * 60)
        logger.info(f"STARTING {duration} SECOND VIDEO RECORDING")
        logger.info("=" * 60)

        # Prepare device
        self.wake_screen()
        self.stop_camera_app()

        # Launch camera
        self.launch_camera_video_mode()

        # Start recording
        self.start_recording()

        logger.info(f"Recording for {duration} seconds ({duration // 60} min {duration % 60} sec)...")

        # Wait with periodic updates
        start_time = time.time()
        last_log = 0

        while time.time() - start_time < duration:
            elapsed = int(time.time() - start_time)
            remaining = duration - elapsed

            # Log every 30 seconds
            if elapsed - last_log >= 30:
                logger.info(
                    f"  Recording... {remaining} seconds remaining ({remaining // 60} min {remaining % 60} sec)")
                last_log = elapsed

            time.sleep(1)

        # Stop recording
        self.stop_recording()

        logger.info("✓ Recording stopped")

        # Wait for video to save
        logger.info("Waiting for video to save...")
        time.sleep(3)

        # Return to home
        self.go_home()

        logger.info("=" * 60)
        logger.info("VIDEO RECORDING COMPLETE")
        logger.info("=" * 60)

        return True


def main():
    """Main execution - no prompts, runs immediately"""
    print("=" * 60)
    print("Android 5-Minute Video Recording")
    print("=" * 60)
    print()

    controller = ADBCameraController()

    # Quick checks
    if not controller.check_adb_available():
        print("❌ ADB not available")
        return 1

    if not controller.check_device_connected():
        print("❌ No device connected")
        return 1

    print("✓ ADB ready, device connected")
    print(f"✓ Recording: {RECORDING_DURATION} seconds ({RECORDING_DURATION // 60} minutes)")
    print()

    # Start recording immediately
    success = controller.record_video(duration=RECORDING_DURATION)

    if success:
        print("\n✓ Video recording completed!")
        print("Check your device's camera roll")
        return 0
    else:
        print("\n✗ Recording failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())