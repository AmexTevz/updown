"""
Holding Training Game

Objective: Keep horizontal board level (angle ≤ 10 degrees) for accumulated training time
Simpler than Up/Down training - just hold vs not hold
"""

import asyncio
import random
import time
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

# Import configuration
from config import *

# Import hardware control
from hardware import (
    bulb_1_control, bulb_2_control, strobe_control,
    heat_control, plug_control,
    all_bulbs_on, all_bulbs_off,
    read_button, check_button_press,
    send_vibration,
    emergency_shutdown
)

# Import audio
from audio import (
    play_audio, start_white_noise, stop_white_noise,
    set_audio_volume
)

# Import sensor system
import sys
sys.path.append('.')
from main_wit import SensorDataQueue, SensorState

# Video recording (optional)
from video_recorder import VideoRecorder

logger = logging.getLogger(__name__)

# ============================================================================
# HOLDING GAME CONFIGURATION
# ============================================================================

# Angle threshold for "holding correctly"
ANGLE_THRESHOLD = 10  # degrees (board is level if abs(angle) <= 10)

# Bulb reminder when not holding
REMINDER_INTERVAL_MIN = 60   # 1 minute
REMINDER_INTERVAL_MAX = 120  # 2 minutes
REMINDER_DURATION = 3  # seconds

# Initial hold confirmation
HOLD_CONFIRMATION_DURATION = 5  # seconds - both bulbs ON when first achieving hold

# Sensor patience (same as updown training)
SENSOR_PATIENCE_TIME = 1 * 3600  # 1 hour

# ============================================================================
# GAME STATES
# ============================================================================

class HoldingState(Enum):
    """Simple state machine"""
    WAITING = "waiting"
    NOT_HOLDING = "not_holding"
    HOLDING = "holding"
    FINISHED = "finished"
    EMERGENCY = "emergency"


# ============================================================================
# HOLDING GAME CLASS
# ============================================================================

class HoldingGame:
    """Simpler training - just hold the board level"""

    def __init__(self):
        # Sensor system
        self.sensor_queue = SensorDataQueue()

        # Game state
        self.state = HoldingState.WAITING
        self.is_running = False
        self.game_started = False

        # Time tracking
        self.start_time: Optional[datetime] = None
        self.deadline: Optional[datetime] = None
        self.training_goal = random.randint(TRAINING_TIME_MIN, TRAINING_TIME_MAX)
        self.accumulated_hold_time = 0.0  # Time spent holding correctly
        self.current_hold_start = 0.0  # When current hold started

        # State tracking
        self.currently_holding = False
        self.last_reminder_time = 0
        self.next_reminder_time = 0

        # Button state
        self.last_button_2_value = None

        # Sensor failure tracking
        self.sensor_loss_start = None
        self.sensor_lost = False

        # Emergency flag
        self.critical_error = False

        # Video recording
        self.video_recorder = VideoRecorder(enabled=VIDEO_RECORDING_ENABLED)

        # Report file
        self.report_file = None
        self._create_report()

        # Session tracking
        self.session_start = None
        self.session_end = None
        self.total_not_holding_time = 0.0

        logger.info("=" * 60)
        logger.info("HOLDING TRAINING GAME")
        logger.info("=" * 60)
        logger.info(f"Training goal: {self.training_goal / 60:.1f} minutes")
        logger.info(f"Angle threshold: ±{ANGLE_THRESHOLD} degrees")
        logger.info(f"Game duration: {GAME_DURATION_HOURS} hours")

    def _create_report(self):
        """Create report file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.report_file = f"holding_report_{timestamp}.txt"

            with open(self.report_file, 'w') as f:
                f.write("=" * 80 + "\n")
                f.write("HOLDING TRAINING GAME - SESSION REPORT\n")
                f.write("=" * 80 + "\n")
                f.write(f"Report Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Status: PENDING START\n")
                f.write(f"Training Goal: {self.training_goal / 60:.1f} minutes\n")
                f.write("=" * 80 + "\n\n")

            logger.info(f"✓ Report file created: {self.report_file}")
        except Exception as e:
            logger.error(f"✗ Failed to create report file: {e}")
            self.report_file = None

    def initialize_report(self):
        """Update report with game start info"""
        if not self.report_file:
            return

        try:
            with open(self.report_file, 'w') as f:
                f.write("=" * 80 + "\n")
                f.write("HOLDING TRAINING GAME - SESSION REPORT\n")
                f.write("=" * 80 + "\n")
                f.write(f"Session Start: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Deadline: {self.deadline.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Game Duration: {GAME_DURATION_HOURS} hours\n")
                f.write(f"Training Goal: {self.training_goal / 60:.1f} minutes\n")
                f.write(f"Angle Threshold: ±{ANGLE_THRESHOLD} degrees\n")
                f.write("=" * 80 + "\n\n")

        except Exception as e:
            logger.error(f"✗ Failed to update report: {e}")

    def get_board_angle(self) -> Optional[float]:
        """Get current board angle from sensors"""
        angles = self.sensor_queue.get_all_angles()

        # Try primary sensor first
        if 'w_back.txt' in angles and angles['w_back.txt'] is not None:
            return angles['w_back.txt']

        # Try backup sensor
        if 'Orientation.txt' in angles and angles['Orientation.txt'] is not None:
            return angles['Orientation.txt']

        return None

    def check_sensor_lost(self) -> bool:
        """Check if sensors are lost"""
        angle = self.get_board_angle()

        if angle is None and not self.sensor_lost:
            # Just lost sensor
            self.sensor_lost = True
            self.sensor_loss_start = time.time()
            logger.error("⚠️ SENSOR LOST - Starting patience timer")
            return True
        elif angle is not None and self.sensor_lost:
            # Sensor reconnected
            elapsed = time.time() - self.sensor_loss_start if self.sensor_loss_start else 0
            self.sensor_lost = False
            self.sensor_loss_start = None
            logger.info(f"✓ Sensor reconnected after {elapsed / 60:.1f} minutes")
            return False

        return self.sensor_lost

    def is_board_level(self) -> bool:
        """Check if board is level (within threshold)"""
        angle = self.get_board_angle()
        if angle is None:
            return False

        return abs(angle) <= ANGLE_THRESHOLD

    @property
    def remaining_time(self) -> float:
        """Training time still needed"""
        return self.training_goal - self.accumulated_hold_time

    @property
    def time_until_deadline(self) -> float:
        """Seconds until game deadline"""
        if self.deadline is None:
            return float('inf')
        return (self.deadline - datetime.now()).total_seconds()

    def is_deadline_reached(self) -> bool:
        """Check if game deadline has passed"""
        return self.time_until_deadline <= 0

    async def enter_not_holding_state(self):
        """Enter NOT HOLDING state"""
        self.state = HoldingState.NOT_HOLDING
        self.currently_holding = False

        # Stop current hold timer if active
        if self.current_hold_start > 0:
            hold_duration = time.time() - self.current_hold_start
            self.accumulated_hold_time += hold_duration
            logger.info(f"Hold ended - Duration: {hold_duration:.1f}s")
            logger.info(f"Total accumulated: {self.accumulated_hold_time / 60:.1f} min")
            logger.info(f"Remaining: {self.remaining_time / 60:.1f} min")
            self.current_hold_start = 0

        # Turn off heat
        await heat_control("off")

        # Turn off both bulbs
        await bulb_1_control("off")
        await bulb_2_control("off")

        # Start white noise
        start_white_noise()

        # Schedule next reminder
        self.next_reminder_time = time.time() + random.randint(
            REMINDER_INTERVAL_MIN, REMINDER_INTERVAL_MAX
        )

        logger.info("→ NOT HOLDING state (white noise ON, lights OFF)")

    async def enter_holding_state(self):
        """Enter HOLDING state"""
        self.state = HoldingState.HOLDING
        self.currently_holding = True
        self.current_hold_start = time.time()

        logger.info("✓ HOLDING state achieved!")

        # Stop white noise
        stop_white_noise()

        # Turn on heat
        await heat_control("on")

        # Turn on both bulbs for confirmation
        await bulb_1_control("on")
        await bulb_2_control("on")

        # Keep them on for 5 seconds
        await asyncio.sleep(HOLD_CONFIRMATION_DURATION)

        # Turn bulbs back off
        await bulb_1_control("off")
        await bulb_2_control("off")

        logger.info("→ HOLDING state (white noise OFF, heat ON, lights OFF)")

    async def show_reminder(self):
        """Flash bulbs briefly as reminder when not holding"""
        logger.info("Reminder: Board not level")

        # Turn on both bulbs
        await bulb_1_control("on")
        await bulb_2_control("on")

        # Keep on for 3 seconds
        await asyncio.sleep(REMINDER_DURATION)

        # Turn back off
        await bulb_1_control("off")
        await bulb_2_control("off")

        # Schedule next reminder
        self.next_reminder_time = time.time() + random.randint(
            REMINDER_INTERVAL_MIN, REMINDER_INTERVAL_MAX
        )

    async def start_game(self):
        """Initialize and start the game"""
        self.game_started = True
        self.start_time = datetime.now()
        self.deadline = self.start_time + timedelta(hours=GAME_DURATION_HOURS)
        self.session_start = self.start_time

        logger.info("=" * 60)
        logger.info(f"GAME STARTED: {self.start_time.strftime('%H:%M:%S')}")
        logger.info(f"Deadline: {self.deadline.strftime('%H:%M:%S')}")
        logger.info("=" * 60)

        # Initialize report
        self.initialize_report()

        # Turn off everything
        await all_bulbs_off()
        await strobe_control("off")
        await heat_control("off")

        logger.info("All devices turned OFF")

        # Start video recording
        logger.info(f"Starting video recording in {VIDEO_START_BEFORE_PREP} seconds...")
        await asyncio.sleep(VIDEO_START_BEFORE_PREP)
        await self.video_recorder.start_recording()
        await asyncio.sleep(3)

        # Start in NOT HOLDING state
        await self.enter_not_holding_state()

    async def end_game(self):
        """End the game"""
        self.state = HoldingState.FINISHED
        self.is_running = False
        self.session_end = datetime.now()

        # Stop any active hold timer
        if self.current_hold_start > 0:
            hold_duration = time.time() - self.current_hold_start
            self.accumulated_hold_time += hold_duration

        logger.info("=" * 60)
        logger.info("GAME ENDED")
        logger.info(f"Accumulated hold time: {self.accumulated_hold_time / 60:.1f} minutes")
        logger.info(f"Training goal: {self.training_goal / 60:.1f} minutes")

        if self.remaining_time <= 0:
            logger.info("STATUS: GOAL ACHIEVED")
        elif self.is_deadline_reached():
            logger.info("STATUS: TIME EXPIRED")
        else:
            logger.info("STATUS: TERMINATED")
        logger.info("=" * 60)

        # Generate final report
        self.generate_final_report()

        # Stop white noise if playing
        stop_white_noise()

        # Stop video
        await self.video_recorder.stop_recording()

        # Start end sequence
        asyncio.create_task(self.game_end_sequence())

    def generate_final_report(self):
        """Generate final session report"""
        if not self.report_file:
            return

        try:
            with open(self.report_file, 'a') as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write("FINAL SESSION SUMMARY\n")
                f.write("=" * 80 + "\n")
                f.write(f"Session End: {self.session_end.strftime('%Y-%m-%d %H:%M:%S')}\n")

                duration = (self.session_end - self.session_start).total_seconds()
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                seconds = int(duration % 60)
                f.write(f"Total Duration: {hours}h {minutes}m {seconds}s\n\n")

                f.write(f"Training Goal: {self.training_goal / 60:.1f} minutes\n")
                f.write(f"Accumulated Hold Time: {self.accumulated_hold_time / 60:.1f} minutes\n")
                f.write(f"Remaining: {self.remaining_time / 60:.1f} minutes\n\n")

                if self.remaining_time <= 0:
                    f.write("Result: GOAL ACHIEVED ✓\n")
                elif self.is_deadline_reached():
                    f.write("Result: TIME EXPIRED\n")
                else:
                    f.write("Result: TERMINATED\n")

                # Calculate percentages
                hold_percent = (self.accumulated_hold_time / duration * 100) if duration > 0 else 0
                not_hold_percent = 100 - hold_percent

                f.write(f"\nTime Distribution:\n")
                f.write(f"  Holding: {self.accumulated_hold_time / 60:.1f} min ({hold_percent:.1f}%)\n")
                f.write(f"  Not Holding: {(duration - self.accumulated_hold_time) / 60:.1f} min ({not_hold_percent:.1f}%)\n")

                f.write("=" * 80 + "\n")

            logger.info(f"✓ Final report saved: {self.report_file}")
        except Exception as e:
            logger.error(f"✗ Failed to generate final report: {e}")

    async def game_end_sequence(self):
        """End game sequence with delay before plug activation"""
        from audio import play_audio_from_folder

        logger.info("=" * 60)
        logger.info("GAME END SEQUENCE")
        logger.info("=" * 60)

        # Play end audio from holding_over folder
        play_audio_from_folder('audio_holding/holding_over', 'Training complete')

        # Turn on all bulbs immediately
        await all_bulbs_on()
        await strobe_control("on")
        logger.info("✓ All lights turned ON")

        # Wait 3-5 minutes before plug
        wait_time = random.randint(3 * 60, 5 * 60)
        logger.info(f"Waiting {wait_time / 60:.1f} minutes before plug activation...")

        elapsed = 0
        while elapsed < wait_time:
            await asyncio.sleep(10)
            elapsed += 10

            if elapsed % 60 == 0:
                remaining = (wait_time - elapsed) / 60
                logger.info(f"  {remaining:.1f} minutes until plug activation...")

        # Activate plug
        logger.info("Activating plug...")
        await plug_control("on")
        logger.info("✓ Plug activated")

        logger.info("=" * 60)

        # Maintain forever
        while True:
            await all_bulbs_on()
            await strobe_control("on")
            await plug_control("on")
            await asyncio.sleep(30)

    async def update(self, delta_time: float):
        """Main game update loop"""
        try:
            # Check for critical error
            if self.critical_error:
                await emergency_shutdown()
                return

            # Waiting for game start
            if not self.game_started:
                # Check button 2 press to start
                pressed, self.last_button_2_value = await check_button_press(
                    BUTTON_2, self.last_button_2_value
                )
                if pressed:
                    logger.info("Button 2 pressed - starting game")
                    await self.start_game()
                return

            # Check deadline
            if self.is_deadline_reached():
                logger.warning("Deadline reached!")
                await self.end_game()
                return

            # Check if goal achieved
            if self.remaining_time <= 0:
                logger.info("Training goal achieved!")
                await self.end_game()
                return

            # Check sensor status
            if self.check_sensor_lost():
                # Sensor just lost
                logger.warning("Sensor lost - entering patience mode")
                start_white_noise()
                await all_bulbs_off()

                # Wait for reconnection with patience
                patience_start = time.time()
                while self.sensor_lost:
                    elapsed = time.time() - patience_start

                    if elapsed >= SENSOR_PATIENCE_TIME:
                        logger.error("Sensor patience timeout - ending game")
                        await self.end_game()
                        return

                    self.check_sensor_lost()
                    await asyncio.sleep(1)

                # Sensor reconnected
                stop_white_noise()
                logger.info("Sensor reconnected - resuming")

            # Main state logic
            if self.state == HoldingState.NOT_HOLDING:
                # Check if board is now level
                if self.is_board_level():
                    await self.enter_holding_state()
                else:
                    # Show reminder periodically
                    if time.time() >= self.next_reminder_time:
                        await self.show_reminder()

            elif self.state == HoldingState.HOLDING:
                # Check if board is still level
                if not self.is_board_level():
                    await self.enter_not_holding_state()
                else:
                    # Update accumulated time
                    if self.current_hold_start > 0:
                        current_hold = time.time() - self.current_hold_start
                        total = self.accumulated_hold_time + current_hold

                        # Log progress every 30 seconds
                        if int(current_hold) % 30 == 0 and current_hold > 0:
                            logger.info(f"Holding: {current_hold:.0f}s | Total: {total / 60:.1f} min | Remaining: {(self.training_goal - total) / 60:.1f} min")

        except Exception as e:
            logger.critical(f"Critical error in update: {e}", exc_info=True)
            self.critical_error = True


# ============================================================================
# GAME LOOP
# ============================================================================

async def game_loop(game: HoldingGame):
    """Main game loop"""
    last_time = time.time()

    while game.is_running:
        try:
            current_time = time.time()
            delta_time = current_time - last_time
            last_time = current_time

            await game.update(delta_time)
            await asyncio.sleep(1 / 60)  # 60 FPS

        except Exception as e:
            logger.critical(f"Critical error in game loop: {e}", exc_info=True)
            await emergency_shutdown()
            break