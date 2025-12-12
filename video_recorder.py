"""
Video Recorder for Training Game
Matches standalone script exactly - proven to work
"""

import subprocess
import asyncio
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Thread pool for running blocking subprocess calls
executor = ThreadPoolExecutor(max_workers=2)


class VideoRecorder:
    """Manage video recording on Android device via ADB"""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.recording = False
        self.video_count = 0
        self.adb_prefix = ['adb']

        if self.enabled:
            self._check_adb()

    def _check_adb(self):
        """Check if ADB and device are available"""
        try:
            result = subprocess.run(
                ['adb', 'devices'],
                capture_output=True,
                text=True,
                timeout=5
            )

            lines = result.stdout.strip().split('\n')[1:]
            devices = [line for line in lines if line.strip() and '\tdevice' in line]

            if not devices:
                logger.warning("No Android device - video recording disabled")
                self.enabled = False
            else:
                logger.info("✓ Video recording system ready")
        except Exception as e:
            logger.warning(f"ADB not available - video recording disabled: {e}")
            self.enabled = False

    def _run_adb_sync(self, command):
        """
        Run ADB command synchronously (blocking)
        EXACTLY matches standalone script
        """
        if not self.enabled:
            return None

        try:
            full_command = self.adb_prefix + command
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result
        except Exception as e:
            logger.error(f"ADB command failed: {e}")
            return None

    async def _run_adb(self, command):
        """Run ADB command asynchronously (non-blocking)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, self._run_adb_sync, command)

    async def start_recording(self):
        """
        Start video recording
        EXACTLY matches standalone script sequence
        """
        if not self.enabled or self.recording:
            logger.warning("Cannot start recording (disabled or already recording)")
            return

        self.video_count += 1
        logger.info("=" * 60)
        logger.info(f"📹 STARTING VIDEO RECORDING #{self.video_count}")
        logger.info("=" * 60)

        # Step 1: Wake screen
        logger.info("Waking screen...")
        await self._run_adb(['shell', 'input', 'keyevent', 'KEYCODE_WAKEUP'])
        await asyncio.sleep(0.5)

        # Step 2: Stop camera apps (EXACTLY like standalone)
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
            await self._run_adb(['shell', 'am', 'force-stop', package])

        await asyncio.sleep(1)

        # Step 3: Launch camera in video mode (EXACTLY like standalone)
        logger.info("Launching camera in video mode...")
        await self._run_adb([
            'shell', 'am', 'start',
            '-a', 'android.media.action.VIDEO_CAPTURE'
        ])

        await asyncio.sleep(3)  # Wait for camera to initialize (EXACTLY 3 seconds)

        # Step 4: Start recording (EXACTLY like standalone)
        logger.info("Starting recording (KEYCODE_ENTER)...")
        await self._run_adb(['shell', 'input', 'keyevent', 'KEYCODE_ENTER'])
        await asyncio.sleep(1)

        self.recording = True
        logger.info("✓ Recording started")
        logger.info("=" * 60)

    async def stop_recording(self):
        """
        Stop video recording
        EXACTLY matches standalone script sequence
        """
        if not self.enabled or not self.recording:
            logger.warning("Cannot stop recording (disabled or not recording)")
            return

        logger.info("=" * 60)
        logger.info("📹 STOPPING VIDEO RECORDING")
        logger.info("=" * 60)

        # Step 1: Stop recording (EXACTLY like standalone)
        logger.info("Stopping recording (KEYCODE_ENTER)...")
        await self._run_adb(['shell', 'input', 'keyevent', 'KEYCODE_ENTER'])
        await asyncio.sleep(1)

        logger.info("✓ Recording stopped")

        # Step 2: Wait for video to save (EXACTLY like standalone - 3 seconds)
        logger.info("Waiting for video to save...")
        await asyncio.sleep(3)

        # Step 3: Return to home (EXACTLY like standalone)
        logger.info("Returning to home screen...")
        await self._run_adb(['shell', 'input', 'keyevent', 'KEYCODE_HOME'])
        await asyncio.sleep(0.5)

        self.recording = False
        logger.info("=" * 60)
        logger.info("VIDEO RECORDING COMPLETE")
        logger.info("=" * 60)