"""
Holding Training Game - FIXED VERSION
"""

import asyncio
import random
import time
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from config import *
from hardware import (
    bulb_1_control, bulb_2_control, strobe_control,
    heat_control, plug_control,
    all_bulbs_on, all_bulbs_off,
    read_button, check_button_press,
    send_vibration,
    emergency_shutdown
)
from audio import start_white_noise, stop_white_noise

import sys
sys.path.append('.')
from main_wit import SensorDataQueue, SensorState

logger = logging.getLogger(__name__)

ANGLE_THRESHOLD = 10
REMINDER_INTERVAL_MIN = 60
REMINDER_INTERVAL_MAX = 120
REMINDER_DURATION = 3
HOLD_CONFIRMATION_DURATION = 5
SENSOR_PATIENCE_TIME = 1 * 3600

class HoldingState(Enum):
    WAITING = "waiting"
    NOT_HOLDING = "not_holding"
    HOLDING = "holding"
    FINISHED = "finished"
    EMERGENCY = "emergency"

class HoldingGame:
    def __init__(self):
        self.sensor_queue = SensorDataQueue()
        self.state = HoldingState.WAITING
        self.is_running = True
        self.game_started = False

        self.start_time: Optional[datetime] = None
        self.deadline: Optional[datetime] = None
        self.training_goal = random.randint(HOLDING_TRAINING_TIME_MIN, HOLDING_TRAINING_TIME_MAX)
        self.accumulated_hold_time = 0.0
        self.current_hold_start = 0.0

        self.currently_holding = False
        self.next_reminder_time = 0
        self.sensor_loss_start = None
        self.sensor_lost = False
        self.critical_error = False

        self.session_start = None
        self.session_end = None

        self.report_file = None
        self._create_report()
        self.hold_attempts = []  # List of all hold attempts
        self.attempt_number = 0

        logger.info("=" * 60)
        logger.info("HOLDING TRAINING GAME")
        logger.info(f"Training goal: {self.training_goal / 60:.1f} minutes")
        logger.info(f"Angle threshold: ±{ANGLE_THRESHOLD} degrees")
        logger.info("=" * 60)

    def _create_report(self):
        """Create report file with header"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.report_file = f"holding_report_{timestamp}.txt"

            with open(self.report_file, 'w') as f:
                f.write("=" * 100 + "\n")
                f.write("HOLDING TRAINING GAME - SESSION REPORT\n")
                f.write("=" * 100 + "\n")
                f.write(f"Report Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Training Goal: {self.training_goal / 60:.1f} minutes ({self.training_goal:.0f} seconds)\n")
                f.write(f"Angle Threshold: ANY negative OR 0° to +{ANGLE_THRESHOLD}°\n")
                f.write("=" * 100 + "\n\n")

            logger.info(f"✓ Report created: {self.report_file}")
        except Exception as e:
            logger.error(f"✗ Report creation failed: {e}")

    def _log_hold_attempt(self, start_time: datetime, end_time: datetime, duration: float):
        """Log a hold attempt to report file"""
        if not self.report_file:
            return

        try:
            self.attempt_number += 1

            # Calculate stats at this moment
            total_accumulated = self.accumulated_hold_time
            remaining = self.remaining_time
            percent_complete = (total_accumulated / self.training_goal * 100) if self.training_goal > 0 else 0

            # Store attempt data
            attempt_data = {
                'number': self.attempt_number,
                'start_time': start_time,
                'end_time': end_time,
                'duration': duration,
                'total_accumulated': total_accumulated,
                'remaining': remaining,
                'percent_complete': percent_complete
            }
            self.hold_attempts.append(attempt_data)

            # Write to file immediately
            with open(self.report_file, 'a') as f:
                f.write(f"\n{'─' * 100}\n")
                f.write(f"ATTEMPT #{self.attempt_number}\n")
                f.write(f"{'─' * 100}\n")
                f.write(f"Started:           {start_time.strftime('%H:%M:%S')}\n")
                f.write(f"Ended:             {end_time.strftime('%H:%M:%S')}\n")
                f.write(f"Hold Duration:     {duration:.1f} seconds ({duration / 60:.2f} minutes)\n")
                f.write(f"\n")
                f.write(f"Progress After This Attempt:\n")
                f.write(
                    f"  Total Accumulated:  {total_accumulated:.1f} seconds ({total_accumulated / 60:.2f} minutes)\n")
                f.write(f"  Remaining:          {remaining:.1f} seconds ({remaining / 60:.2f} minutes)\n")
                f.write(f"  Completion:         {percent_complete:.1f}%\n")
                f.write(f"{'─' * 100}\n")

        except Exception as e:
            logger.error(f"Failed to log attempt: {e}")

    def generate_final_report(self):
        """Generate comprehensive final report"""
        if not self.report_file:
            return

        try:
            with open(self.report_file, 'a') as f:
                f.write("\n\n")
                f.write("=" * 100 + "\n")
                f.write("FINAL SESSION SUMMARY\n")
                f.write("=" * 100 + "\n")
                f.write(f"Session Start:  {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Session End:    {self.session_end.strftime('%Y-%m-%d %H:%M:%S')}\n")

                duration = (self.session_end - self.session_start).total_seconds()
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                seconds = int(duration % 60)
                f.write(f"Total Duration: {hours}h {minutes}m {seconds}s\n")
                f.write("\n")

                # Goal and achievement
                f.write(
                    f"Training Goal:        {self.training_goal / 60:.1f} minutes ({self.training_goal:.0f} seconds)\n")
                f.write(
                    f"Total Hold Time:      {self.accumulated_hold_time / 60:.2f} minutes ({self.accumulated_hold_time:.1f} seconds)\n")
                f.write(
                    f"Remaining:            {self.remaining_time / 60:.2f} minutes ({self.remaining_time:.1f} seconds)\n")

                completion_percent = (
                            self.accumulated_hold_time / self.training_goal * 100) if self.training_goal > 0 else 0
                f.write(f"Completion:           {completion_percent:.1f}%\n")
                f.write("\n")

                # Result
                if self.remaining_time <= 0:
                    f.write("Result: ✓ GOAL ACHIEVED\n")
                elif self.is_deadline_reached():
                    f.write("Result: ✗ TIME EXPIRED (deadline reached)\n")
                else:
                    f.write("Result: ✗ TERMINATED (early exit)\n")
                f.write("\n")

                # Time distribution
                hold_percent = (self.accumulated_hold_time / duration * 100) if duration > 0 else 0
                not_hold_percent = 100 - hold_percent
                not_hold_time = duration - self.accumulated_hold_time

                f.write("Time Distribution:\n")
                f.write(f"  Time Holding:      {self.accumulated_hold_time / 60:.2f} minutes ({hold_percent:.1f}%)\n")
                f.write(f"  Time Not Holding:  {not_hold_time / 60:.2f} minutes ({not_hold_percent:.1f}%)\n")
                f.write("\n")

                # Attempt statistics
                f.write("=" * 100 + "\n")
                f.write("ATTEMPT STATISTICS\n")
                f.write("=" * 100 + "\n")
                f.write(f"Total Attempts:       {self.attempt_number}\n")

                if self.hold_attempts:
                    durations = [a['duration'] for a in self.hold_attempts]
                    avg_duration = sum(durations) / len(durations)
                    longest = max(durations)
                    shortest = min(durations)

                    f.write(f"Average Hold:         {avg_duration:.1f} seconds ({avg_duration / 60:.2f} minutes)\n")
                    f.write(f"Longest Hold:         {longest:.1f} seconds ({longest / 60:.2f} minutes)\n")
                    f.write(f"Shortest Hold:        {shortest:.1f} seconds ({shortest / 60:.2f} minutes)\n")

                    # Find longest and shortest attempts
                    longest_attempt = max(self.hold_attempts, key=lambda x: x['duration'])
                    shortest_attempt = min(self.hold_attempts, key=lambda x: x['duration'])

                    f.write(f"\n")
                    f.write(
                        f"Longest attempt was #{longest_attempt['number']} at {longest_attempt['start_time'].strftime('%H:%M:%S')}\n")
                    f.write(
                        f"Shortest attempt was #{shortest_attempt['number']} at {shortest_attempt['start_time'].strftime('%H:%M:%S')}\n")
                else:
                    f.write("No hold attempts recorded.\n")

                f.write("\n")
                f.write("=" * 100 + "\n")
                f.write("END OF REPORT\n")
                f.write("=" * 100 + "\n")

            logger.info(f"✓ Final report saved: {self.report_file}")

        except Exception as e:
            logger.error(f"Failed to generate final report: {e}")

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

    def is_board_level(self) -> bool:
        """
        Check if board is level (within threshold)
        - ANY negative angle = LEVEL
        - Positive angles: 0° to +10° = LEVEL
        """
        angle = self.get_board_angle()

        if angle is None:
            return False

        # ANY negative angle counts as level
        if angle < 0:
            return True

        # Positive angles: check threshold
        # 0 to +10 degrees = LEVEL
        is_level = angle <= ANGLE_THRESHOLD

        return is_level
    @property
    def remaining_time(self) -> float:
        return self.training_goal - self.accumulated_hold_time

    def is_deadline_reached(self) -> bool:
        if self.deadline is None:
            return False
        return datetime.now() >= self.deadline

    async def start_game(self):
        """Start the actual game"""
        self.game_started = True
        self.start_time = datetime.now()
        self.deadline = self.start_time + timedelta(hours=GAME_DURATION_HOURS)
        self.session_start = self.start_time

        logger.info("=" * 60)
        logger.info(f"GAME STARTED: {self.start_time.strftime('%H:%M:%S')}")
        logger.info(f"Deadline: {self.deadline.strftime('%H:%M:%S')}")
        logger.info("=" * 60)

        # Start in NOT HOLDING state
        await self.enter_not_holding_state()

    async def enter_not_holding_state(self):
        """Enter NOT HOLDING state"""
        self.state = HoldingState.NOT_HOLDING
        self.currently_holding = False

        # Stop current hold timer if active
        if self.current_hold_start > 0:
            hold_start_time = datetime.fromtimestamp(self.current_hold_start)
            hold_end_time = datetime.now()
            hold_duration = time.time() - self.current_hold_start

            self.accumulated_hold_time += hold_duration

            # Log to report
            self._log_hold_attempt(hold_start_time, hold_end_time, hold_duration)

            # Console logging
            current_angle = self.get_board_angle()
            logger.info(f"Hold ended - Duration: {hold_duration:.1f}s (angle now: {current_angle:.1f}°)")
            logger.info(f"Total: {self.accumulated_hold_time / 60:.1f} min")
            logger.info(f"Remaining: {self.remaining_time / 60:.1f} min")
            self.current_hold_start = 0

        await heat_control("off")
        await bulb_1_control("off")
        await bulb_2_control("off")
        start_white_noise()

        self.next_reminder_time = time.time() + random.randint(
            REMINDER_INTERVAL_MIN, REMINDER_INTERVAL_MAX
        )
        logger.info("→ NOT HOLDING (white noise ON)")

    async def enter_holding_state(self):
        """Enter HOLDING state"""
        self.state = HoldingState.HOLDING
        self.currently_holding = True
        self.current_hold_start = time.time()

        # Log with current angle
        current_angle = self.get_board_angle()
        logger.info(f"✓ HOLDING state! (angle: {current_angle:.1f}°)")

        stop_white_noise()
        await heat_control("on")
        await bulb_1_control("on")
        await bulb_2_control("on")
        await asyncio.sleep(HOLD_CONFIRMATION_DURATION)
        await bulb_1_control("off")
        await bulb_2_control("off")

        logger.info("→ HOLDING (white noise OFF, heat ON)")

    async def show_reminder(self):
        logger.info("Reminder: Board not level")
        await bulb_1_control("on")
        await bulb_2_control("on")
        await asyncio.sleep(REMINDER_DURATION)
        await bulb_1_control("off")
        await bulb_2_control("off")
        self.next_reminder_time = time.time() + random.randint(
            REMINDER_INTERVAL_MIN, REMINDER_INTERVAL_MAX
        )

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
        logger.info(f"Hold time: {self.accumulated_hold_time / 60:.1f} min")
        logger.info(f"Goal: {self.training_goal / 60:.1f} min")

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

        # Start end sequence
        await self.game_end_sequence()

    async def game_end_sequence(self):
        from audio import play_audio_from_folder

        logger.info("GAME END SEQUENCE")
        play_audio_from_folder('audio_holding/holding_over', 'Complete')
        await all_bulbs_on()

        wait_time = random.randint(3 * 60, 5 * 60)
        logger.info(f"Waiting {wait_time / 60:.1f} min before plug...")

        elapsed = 0
        while elapsed < wait_time:
            await asyncio.sleep(10)
            elapsed += 10

        await plug_control("on")
        await strobe_control("on")
        logger.info("✓ Plug activated, strobe ON")

        while True:
            await all_bulbs_on()
            await strobe_control("on")
            await plug_control("on")
            await asyncio.sleep(30)

    async def update(self, delta_time: float):
        try:
            if self.critical_error:
                await emergency_shutdown()
                return

            if self.is_deadline_reached():
                await self.end_game()
                return

            if self.remaining_time <= 0:
                await self.end_game()
                return

            # Main state logic
            if self.state == HoldingState.NOT_HOLDING:
                if self.is_board_level():
                    await self.enter_holding_state()
                elif time.time() >= self.next_reminder_time:
                    await self.show_reminder()

            elif self.state == HoldingState.HOLDING:
                # Check if still level
                current_angle = self.get_board_angle()
                is_level = self.is_board_level()

                if not is_level:
                    logger.info(f"⚠️ Lost level position (angle: {current_angle:.1f}°)")
                    await self.enter_not_holding_state()
                elif self.current_hold_start > 0:
                    current_hold = time.time() - self.current_hold_start
                    total = self.accumulated_hold_time + current_hold

                    # Log progress every 30 seconds
                    if int(current_hold) % 30 == 0 and current_hold > 0:
                        logger.info(
                            f"Holding: {current_hold:.0f}s | Total: {total / 60:.1f} min | Angle: {current_angle:.1f}°")

        except Exception as e:
            logger.critical(f"Error: {e}", exc_info=True)
            self.critical_error = True

async def game_loop(game: HoldingGame):
    last_time = time.time()
    while game.is_running:
        try:
            current_time = time.time()
            delta_time = current_time - last_time
            last_time = current_time
            await game.update(delta_time)
            await asyncio.sleep(1 / 60)
        except Exception as e:
            logger.critical(f"Game loop error: {e}", exc_info=True)
            await emergency_shutdown()
            break