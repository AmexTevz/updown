"""
Up/Down Training Game - Phase 1: Core Infrastructure

Main game logic with complete position management and bulb control
Includes continuous hardware monitoring and sensor reconnection
"""

import asyncio
import random
import time
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

# Import our modules
from config import *
from hardware import *
from audio import *

# Import sensor system
import sys
from hardware import fan_control
sys.path.append('.')
from main_wit import SensorDataQueue, SensorState


logger = logging.getLogger(__name__)



def log_with_time(message: str, level="INFO"):
    """Log message with precise timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.mmm
    if level == "INFO":
        logger.info(f"[{timestamp}] {message}")
    elif level == "WARNING":
        logger.warning(f"[{timestamp}] {message}")
    elif level == "ERROR":
        logger.error(f"[{timestamp}] {message}")
# ============================================================================
# GAME STATES
# ============================================================================

class GameState(Enum):
    """Game state machine"""
    WAITING = "waiting"
    PREPARATION = "preparation"
    ROUND = "round"
    BREAK = "break"
    EXTENDED_BREAK = "extended_break"
    PAUSED = "paused"
    FINISHED = "finished"
    EMERGENCY = "emergency"


# ============================================================================
# MAIN GAME CLASS
# ============================================================================

class UpDownGame:
    """Main game controller - Phase 1"""

    def __init__(self):
        # Sensor system
        self._last_continuous_shock = None
        self._continuous_shock_count = None
        self._continuous_shock_start = None
        self.sensor_queue = SensorDataQueue()
        self.active_board_sensor = 'w_back.txt'

        # Game state
        self.state = GameState.WAITING
        self.is_running = False
        self.game_started = False

        # Time tracking
        self.start_time: Optional[datetime] = None
        self.deadline: Optional[datetime] = None
        self.game_time = 0.0

        # Training time accounting
        self.training_goal = random.randint(TRAINING_TIME_MIN, TRAINING_TIME_MAX)
        self.completed_training_time = 0
        self.penalty_time_added = 0

        # Round tracking
        self.current_round_duration = 0
        self.round_start_time = 0
        self.current_level = 'easy'  # Current difficulty level
        self.round_violations = 0
        self._last_round_passed = None# Violations this round
        self.current_position = 'down'
        self.position_hold_time = 0
        self.position_start_time = 0
        self.position_command_start = 0
        self.position_achieved = False
        self.position_bulb_task = None
        self.position_transition_deadline = 0  # Grace period deadline
        self.last_countdown_second = 0

        # Break tracking
        self.break_start_time = 0
        self.break_duration = 0
        self.total_extension_time = 0
        self.current_extension_start = 0
        self.fan_active = False

        # Button state
        self.last_button_1_value = None
        self.last_button_2_value = None

        # Sensor failure tracking
        self.sensor_loss_start = None
        self.both_sensors_lost = False
        self.primary_sensor_lost_time = None
        self.backup_sensor_lost_time = None

        # Emergency flag
        self.critical_error = False

        self.current_pose_violations = 0  # Violations in current pose
        self.violation_announced_this_pose = False  # Has violation audio played?
        self.consecutive_violations = 0  # Total consecutive violations

        self.total_extension_time_used = 0  # Seconds of extension used
        self.total_extension_requests = 0  # Total requests made (for rapid eligibility)
        self.last_extension_request_time = 0  # When last request was made
        self.extension_active = False  # Is extension currently active
        self.extension_start_time = 0  # When current extension started
        self.extension_qualified = False  # Is subject qualified for extension?
        self.void_occurred = False
        self.extension_fan_triggered = False  # Has fan been activated this extension
        self.extension_fan_trigger_time = 0  # When fan should activate
        self._last_button_1_value = 0  # For button edge detection
        self._last_button_2_value = 0  # For button edge detection
        self.break_start_time = 0
        self.current_break_duration = 0  # ADD THIS LINE
        self.break_duration = 0
        self.total_extension_time = 0
        self.current_extension_start = 0
        self.violation_time_accumulated = 0
        self.fan_active = False
        self.both_sensors_were_lost = False


        logger.info("=" * 60)
        logger.info("UP/DOWN TRAINING GAME - PHASE 1")
        logger.info("=" * 60)
        logger.info(f"Training goal: {self.training_goal / 60:.1f} minutes")
        logger.info(f"Sensor patience: {SENSOR_PATIENCE_TIME / 3600:.1f} hours")
        logger.info(f"Testing mode: {'YES' if TESTING_MODE else 'NO'}")

    # ========================================================================
    # SENSOR MANAGEMENT WITH CONTINUOUS RECONNECTION
    # ========================================================================

    def get_board_angle(self) -> Optional[float]:
        """
        Get current board angle with fallback
        Always prefers primary sensor, automatically switches back when available
        """
        angles = self.sensor_queue.get_all_angles()
        current_time = time.time()

        # Get sensor states
        primary_state = self.sensor_queue.get_sensor_state('w_back.txt')
        backup_state = self.sensor_queue.get_sensor_state('Orientation.txt')

        # Get last update times
        primary_last_update = self.sensor_queue.last_update_time.get('w_back.txt', 0)
        backup_last_update = self.sensor_queue.last_update_time.get('Orientation.txt', 0)

        # Check if data is recent (within 5 seconds)
        primary_recent = primary_last_update > current_time - 5
        backup_recent = backup_last_update > current_time - 5

        # Check if we have actual angle data
        primary_has_data = 'w_back.txt' in angles and angles['w_back.txt'] is not None
        backup_has_data = 'Orientation.txt' in angles and angles['Orientation.txt'] is not None

        # Determine availability
        primary_available = (
                primary_state == SensorState.CONNECTED and
                primary_recent and
                primary_has_data
        )

        backup_available = (
                backup_state == SensorState.CONNECTED and
                backup_recent and
                backup_has_data
        )

        # ALWAYS TRY PRIMARY FIRST
        if primary_available:
            # Check if we need to switch back from backup
            if self.active_board_sensor != 'w_back.txt':
                logger.info("=" * 60)
                logger.info("✓ PRIMARY SENSOR RECONNECTED - SWITCHING BACK")
                logger.info("=" * 60)
                self.active_board_sensor = 'w_back.txt'

                # Only play audio if we were in "both lost" state
                if self.both_sensors_were_lost:
                    play_sensor_issue_resolved()
                    self.both_sensors_were_lost = False

            self.primary_sensor_lost_time = None
            return angles.get('w_back.txt')

        # Try backup if primary unavailable
        if backup_available:
            if self.active_board_sensor != 'Orientation.txt':
                logger.info("Switched to backup board sensor")
                self.active_board_sensor = 'Orientation.txt'
                # DON'T play audio - just switching, not recovering from both lost

            self.backup_sensor_lost_time = None
            return angles.get('Orientation.txt')

        # Both sensors unavailable - this is the problem state
        if not self.both_sensors_were_lost:
            # First time both lost
            self.both_sensors_were_lost = True
            # sensor_issue audio is played in check_both_sensors_lost()

        return None

    def check_both_sensors_lost(self) -> bool:
        """
        Check if both back sensors are disconnected
        Returns True if both sensors are unavailable
        """
        primary_state = self.sensor_queue.get_sensor_state('w_back.txt')
        backup_state = self.sensor_queue.get_sensor_state('Orientation.txt')

        current_time = time.time()
        primary_fresh = self.sensor_queue.last_update_time.get('w_back.txt', 0) > current_time - 5
        backup_fresh = self.sensor_queue.last_update_time.get('Orientation.txt', 0) > current_time - 5

        both_lost = (
                (primary_state == SensorState.DISCONNECTED or not primary_fresh) and
                (backup_state == SensorState.DISCONNECTED or not backup_fresh)
        )

        if both_lost and not self.both_sensors_lost:
            # Just lost both sensors
            self.both_sensors_lost = True
            self.sensor_loss_start = time.time()
            logger.error("⚠ BOTH SENSORS LOST - Starting 2-hour patience timer")
            play_sensor_issue()  # CHANGED: Use new function
            return True

        elif not both_lost and self.both_sensors_lost:
            # Sensors reconnected
            elapsed = time.time() - self.sensor_loss_start if self.sensor_loss_start else 0
            self.both_sensors_lost = False
            self.sensor_loss_start = None
            logger.info(f"✓ Sensors reconnected after {elapsed / 60:.1f} minutes")
            play_sensor_issue_resolved()  # CHANGED: Use new function
            return False

        return both_lost
    def check_position_correct(self, target_position: str) -> bool:
        """Check if current angle matches target position"""
        angle = self.get_board_angle()
        if angle is None:
            return False

        if target_position == 'down':
            return angle < ANGLE_DOWN_THRESHOLD
        else:  # 'up'
            return angle > ANGLE_UP_THRESHOLD

    async def handle_sensor_loss_during_round(self):
        """
        Handle both sensors being lost DURING a round
        - Cancel current round (no time credit)
        - Give audio feedback
        - Enter waiting state (white noise, lights off)
        - Keep checking for reconnection for 2 HOURS
        - Once reconnected OR timeout, take appropriate action
        """
        logger.warning("⚠ Both sensors lost during round - CANCELING ROUND")

        # Turn off all lights
        await all_bulbs_off()

        # Audio feedback
        play_sensor_issue()  # CHANGED: Use new function

        # Start white noise (like break)
        start_white_noise()

        # Change state to paused
        self.state = GameState.PAUSED

        # Keep checking for reconnection (2 HOURS patience)
        logger.info(f"Waiting up to {SENSOR_PATIENCE_TIME / 3600:.1f} hours for sensor reconnection...")

        patience_start = time.time()

        while self.both_sensors_lost:
            # Check elapsed time
            elapsed = time.time() - patience_start

            # Check if patience time exceeded (2 hours)
            if elapsed >= SENSOR_PATIENCE_TIME:
                logger.error(f"⚠ Sensor patience timeout ({SENSOR_PATIENCE_TIME / 3600:.1f} hours) - ENDING GAME")
                stop_white_noise()
                play_audio('game_end_timeout', 'Sensor timeout. Game ending.')
                await self.end_game()
                return

            # Check every 5 seconds
            await asyncio.sleep(5)

            # Update sensor status
            self.check_both_sensors_lost()

            # Check if deadline reached while waiting
            if self.is_deadline_reached():
                logger.info("Deadline reached during sensor wait")
                stop_white_noise()
                await self.end_game()
                return

            # Log progress every 5 minutes
            if elapsed > 0 and int(elapsed) % 300 == 0:
                remaining = (SENSOR_PATIENCE_TIME - elapsed) / 60
                logger.info(f"Still waiting for sensors... {remaining:.0f} minutes remaining")

        logger.info("✓ Sensors reconnected - resuming game")
        stop_white_noise()
        play_sensor_issue_resolved()  # ADD THIS

        # Go to preparation phase (fresh start)
        await self.enter_preparation()

    # ========================================================================
    # POSITION COMMANDS
    # ========================================================================

    async def command_position(self, position: str, is_rapid: bool = False):
        """Command subject to take position"""
        logger.info("=" * 60)
        logger.info(f"COMMAND: {position.upper()} {'(RAPID)' if is_rapid else ''}")
        logger.info("=" * 60)

        self.current_position = position
        self.position_achieved = False
        self.position_command_start = time.time()

        # Determine which bulb to use
        if position == 'down':
            bulb_control = bulb_1_control
            audio_func = play_position_down
            logger.info("→ Using Bulb 1 (DOWN)")
        else:  # 'up'
            bulb_control = bulb_2_control
            audio_func = play_position_up
            logger.info("→ Using Bulb 2 (UP)")

        # Normal round: Turn bulb ON
        if not is_rapid:
            logger.info("→ Turning bulb ON")
            await bulb_control("on")
        else:
            logger.info("→ Rapid mode - bulb stays OFF")

        # Play audio command
        logger.info(f"→ Playing audio: {position}")
        audio_func()

        # Start monitoring position achievement
        logger.info("→ Starting position monitoring")
        config = self.get_level_config()
        if not is_rapid:
            transition_time = random.uniform(*config['transition_time'])
        else:
            transition_time = TRANSITION_TIME_RAPID
        # Store grace period deadline
        self.position_transition_deadline = time.time() + transition_time
        logger.info(
            f"→ Transition time: {transition_time:.1f}s (grace period until {self.position_transition_deadline:.3f})")

        # Start monitoring for achievement
        monitor_task = asyncio.create_task(
            self.monitor_position_achievement(position, bulb_control, is_rapid, transition_time)
        )
        logger.info(f"✓ Position command complete: {position.upper()}")
        logger.info("")

    async def void_round(self):
        """
        Handle round void due to 10 consecutive violations
        - No time credit
        - Forced 3-minute break with white noise
        - Reset violation counters
        """
        self.void_occurred = True
        self.round_violations = 999
        self.state = GameState.BREAK

        logger.warning("=" * 60)
        logger.warning("ROUND VOIDED - 10 CONSECUTIVE VIOLATIONS")
        logger.warning("=" * 60)
        logger.warning(f"Entering forced break: {VOID_BREAK_DURATION / 60:.1f} minutes")

        # Turn off all lights
        await all_bulbs_off()

        # Start white noise during void break
        start_white_noise()

        # Forced break (3 minutes)
        void_break_start = time.time()
        while time.time() - void_break_start < VOID_BREAK_DURATION:
            # Check for sensor loss during void break
            if self.check_both_sensors_lost():
                await self.handle_sensor_loss_during_round()
                return

            # Log progress every 30 seconds
            elapsed = time.time() - void_break_start
            if int(elapsed) % 30 == 0 and elapsed > 0:
                remaining = (VOID_BREAK_DURATION - elapsed) / 60
                logger.info(f"Void break: {remaining:.1f} minutes remaining")

            await asyncio.sleep(1)

        # Stop white noise
        stop_white_noise()

        logger.info("Void break complete - resuming training")

        self.consecutive_violations = 0
        self.current_pose_violations = 0
        self.round_violations = 0  # Also reset round violations

        # Reset continuous shock tracking
        self._continuous_shock_start = None
        self._continuous_shock_count = None
        self._last_continuous_shock = None

        # Resume to preparation
        await self.enter_preparation()
    async def monitor_position_achievement(self, position: str, bulb_control, is_rapid: bool, transition_time: float = 7.0):

        """
        Monitor for position achievement and handle bulb behavior
        NOW ALSO: Track violations and play audio appropriately
        """
        start_time = time.time()
        violation_triggered = False

        # Reset violation tracking for new pose (NEW)
        self.violation_announced_this_pose = False
        self.current_pose_violations = 0

        while True:
            elapsed = time.time() - start_time

            # Check if position achieved
            if not self.position_achieved and self.check_position_correct(position):
                self.position_achieved = True
                logger.info(f"Position {position.upper()} achieved at {elapsed:.1f}s")

                # Reset consecutive violation counter (position achieved)
                self.consecutive_violations = 0  # NEW

                if is_rapid:
                    # Rapid: Just blink
                    await bulb_control("on")
                    await asyncio.sleep(POSITION_CONFIRMATION_DURATION)
                    await bulb_control("off")
                else:
                    # Normal: Keep on for 1 second (confirmation), then OFF
                    await asyncio.sleep(POSITION_CONFIRMATION_DURATION)
                    await bulb_control("off")

                # Start hold timer
                self.position_start_time = time.time()
                break

            # 7-second violation check (only for normal rounds)
            if not is_rapid and elapsed >= transition_time and not violation_triggered:
                violation_triggered = True
                logger.warning(f"Position {position.upper()} not achieved in 7 seconds - VIOLATION")

                # Track violation
                self.current_pose_violations += 1
                self.consecutive_violations += 1
                self.round_violations += 1

                # FIXED ORDER: Shock BEFORE audio
                asyncio.create_task(send_pishock(mode=PISHOCK_MODE_SHOCK))

                # Play violation audio ONLY FIRST TIME in this pose
                if not self.violation_announced_this_pose:
                    play_violation()
                    self.violation_announced_this_pose = True
                # Send PiShock


                # Check for 10-in-a-row void condition (NEW)
                if self.consecutive_violations >= MAX_PISHOCK_CYCLES:
                    logger.error("10 consecutive violations - VOIDING ROUND")
                    play_ten_in_row()  # NEW
                    await self.void_round()
                    return

            # Safety timeout: transition_time + 1 second
            safety_timeout = transition_time + 1.0
            if elapsed >= safety_timeout:
                if not is_rapid:
                    await bulb_control("off")
                    logger.info(f"Bulb turned OFF (safety timeout at {safety_timeout:.1f}s)")
                break

            await asyncio.sleep(0.033)  # 30Hz check

    async def signal_position_correction(self, position: str):
        """
        Signal that position was corrected after violation
        Blink bulb: ON for 1 second, then OFF
        """
        logger.info(f"Position {position.upper()} corrected")

        if position == 'down':
            await bulb_1_control("on")
            await asyncio.sleep(POSITION_CONFIRMATION_DURATION)
            await bulb_1_control("off")
        else:  # 'up'
            await bulb_2_control("on")
            await asyncio.sleep(POSITION_CONFIRMATION_DURATION)
            await bulb_2_control("off")

    # ========================================================================
    # TIME TRACKING
    # ========================================================================

    @property
    def current_training_goal(self) -> int:
        """Total training time needed (base + penalties, capped)"""
        return min(self.training_goal + self.penalty_time_added, MAX_TRAINING_TIME)

    @property
    def remaining_training_time(self) -> int:
        """Training time still needed"""
        return self.current_training_goal - self.completed_training_time

    @property
    def time_until_deadline(self) -> float:
        """Seconds until game deadline"""
        if self.deadline is None:
            return float('inf')
        return (self.deadline - datetime.now()).total_seconds()

    def is_deadline_reached(self) -> bool:
        """Check if game deadline has passed"""
        return self.time_until_deadline <= 0

    def get_level_config(self):
        """Get configuration for current level"""
        return LEVEL_CONFIG[self.current_level]

    def apply_round_result(self, passed: bool):
        """
        Apply round completion results - simplified version
        - Credits round time always
        - Awards 20 min bonus only on Hard pass
        - No penalties to training time
        """
        self._last_round_passed = passed
        config = self.get_level_config()

        # ALWAYS credit round time (unless voided)
        if not self.void_occurred:
            self.completed_training_time += self.current_round_duration
            logger.info(f"Round time credited: {self.current_round_duration / 60:.1f} min")

        if passed:
            logger.info(f"✓ ROUND PASSED!")
            logger.info(f"  Violations: {self.round_violations}/{config['violation_limit']}")

            # Advance level
            if self.current_level == 'easy':
                self.current_level = 'medium'
                logger.info("  → Next level: MEDIUM")
                self.extension_qualified = False

            elif self.current_level == 'medium':
                self.current_level = 'hard'
                logger.info("  → Next level: HARD")
                self.extension_qualified = False

            elif self.current_level == 'hard':
                # CYCLE COMPLETE! Award 20 min bonus
                self.completed_training_time += CYCLE_COMPLETION_BONUS
                logger.info(f"  ★ CYCLE COMPLETE! Bonus: {CYCLE_COMPLETION_BONUS / 60} min")
                self.current_level = 'easy'
                logger.info("  → Next level: EASY (new cycle)")
                self.extension_qualified = True  # Hard passed - qualify for extension

        else:  # Failed
            logger.warning(f"✗ ROUND FAILED!")
            logger.warning(f"  Violations: {self.round_violations} (limit: {config['violation_limit']})")
            logger.warning(f"  Restarting from EASY level")

            # Back to Easy
            self.current_level = 'easy'

            # Qualify for extension (failed round)
            if not self.void_occurred:
                self.extension_qualified = True
                logger.info("  Break extension qualified (round failed)")
            else:
                self.extension_qualified = False
                logger.warning("  NO extension allowed (round voided)")

        # Reset round violation counter
        self.round_violations = 0
        self.void_occurred = False

    # ========================================================================
    # STATE MACHINE
    # ========================================================================

    async def start_game(self):
        """Initialize and start the game"""
        self.game_started = True
        self.start_time = datetime.now()
        self.deadline = self.start_time + timedelta(hours=GAME_DURATION_HOURS)

        logger.info("=" * 60)
        logger.info(f"GAME STARTED: {self.start_time.strftime('%H:%M:%S')}")
        logger.info(f"Deadline: {self.deadline.strftime('%H:%M:%S')}")
        logger.info("=" * 60)

        play_second_press()

        # Go to first preparation phase
        await self.enter_preparation()

    async def enter_preparation(self):
        """
        Enter 20-second preparation phase
        - Play audio announcement
        - Turn on strobe light ONLY
        - Send vibration
        - Monitor buttons
        """
        self.state = GameState.PREPARATION
        logger.info("Entering preparation phase (20 seconds)")

        # Audio feedback - play and get duration
        prep_duration = play_round_starting()

        # Turn on ONLY strobe (all bulbs off)
        await all_bulbs_off()
        await strobe_control("on")

        # Send vibration
        await send_vibration()

        # Wait for preparation audio to finish before playing level audio
        if prep_duration > 0:
            await asyncio.sleep(prep_duration + 0.3)  # Add 0.3s buffer

        # Play level announcement
        if self.current_level == 'easy':
            play_easy_level()
        elif self.current_level == 'medium':
            play_medium_level()
        elif self.current_level == 'hard':
            play_hard_level()

        # If qualified for extension, play availability audio
        if self.extension_qualified:
            await asyncio.sleep(1.0)  # Brief pause between level and extension audio
            play_extension_available()

        # Monitor for 20 seconds (check buttons)
        prep_start = time.time()
        while time.time() - prep_start < PREPARATION_WINDOW:
            # Check Button_1 (extension request)
            pressed_1, self.last_button_1_value = await check_button_press(
                BUTTON_1, self.last_button_1_value
            )
            if pressed_1:
                if self.extension_qualified:
                    logger.info("Button 1 pressed - Extension granted!")
                    # Grant extension immediately
                    await self.start_extension()
                    # After extension ends, we'll return to prep to finish the window
                else:
                    # Not qualified - silent ignore
                    logger.debug("Button 1 pressed but not qualified for extension (ignored)")

            # Check Button_2 (rapid training) - Phase 1: just log it
            pressed_2, self.last_button_2_value = await check_button_press(
                BUTTON_2, self.last_button_2_value
            )
            if pressed_2:
                logger.info("Button 2 pressed during prep (rapid - not implemented yet)")

            await asyncio.sleep(BUTTON_CHECK_INTERVAL)

        # Preparation complete - turn off strobe
        await strobe_control("off")

        # Start round
        await self.start_round()

        # Preparation complete - turn off strobe
        await strobe_control("off")

        # Start round
        await self.start_round()

    async def start_round(self):
        """Start a training round"""
        self.state = GameState.ROUND
        config = self.get_level_config()
        self.current_round_duration = random.randint(*config['round_duration'])
        self.round_start_time = time.time()

        logger.info("=" * 60)
        logger.info(f"ROUND STARTED - Duration: {self.current_round_duration} seconds")
        logger.info("=" * 60)

        # Reset all violation tracking for fresh round
        self.consecutive_violations = 0
        self.current_pose_violations = 0
        self.round_violations = 0
        self._continuous_shock_start = None
        self._continuous_shock_count = None
        self._last_continuous_shock = None

        # Round starts with subject expected in DOWN position
        self.current_position = 'down'
        self.position_achieved = False  # NOT True - let run_round verify it

        logger.info("Round starts - verifying DOWN position")

        # Run round loop (it will verify DOWN first)
        await self.run_round()

    async def run_round(self):
        """
        Main round loop - Phase 1: Simple version
        Alternates between positions until round time expires
        Continuously monitors position achievement and maintenance

        Key mechanics:
        - If position not achieved: shock every 5 seconds until achieved or 10 shocks
        - If position violated after achievement: shock every 5 seconds until corrected or 10 shocks
        - Violations don't consume round time
        - 10 shocks = void round
        """
        # Round starts in DOWN - wait for it to be verified
        logger.info("⏱️ Waiting for initial DOWN position verification...")
        while not self.position_achieved and self.state == GameState.ROUND:
            if self.check_both_sensors_lost():
                await self.handle_sensor_loss_during_round()
                return

            if self.check_position_correct('down'):
                self.position_achieved = True
                self.position_start_time = time.time()
                logger.info(f"⏱️ [{self.position_start_time:.3f}] Initial DOWN position verified")

            await asyncio.sleep(0.1)

        # Generate random hold time for first position
        # Get hold time based on position and level
        config = self.get_level_config()
        if self.current_position == 'up':
            position_hold_target = random.uniform(*config['hold_time_up'])
        else:  # down
            position_hold_target = random.uniform(*config['hold_time_down'])
        logger.info(f"🎲 Initial position hold time: {position_hold_target:.1f} seconds")

        # Track time spent in violations (doesn't count toward round)
        violation_time_accumulated = 0

        while self.state == GameState.ROUND:
            # Continuously check sensor state
            _ = self.get_board_angle()

            # Check for sensor loss
            if self.check_both_sensors_lost():
                await self.handle_sensor_loss_during_round()
                return

            # Calculate adjusted round time (excluding violation time)
            round_elapsed = (time.time() - self.round_start_time) - violation_time_accumulated

            # Check if round time expired (adjusted for violations)
            if round_elapsed >= self.current_round_duration:
                logger.info(
                    f"Round complete: {round_elapsed:.1f}s (violations added {violation_time_accumulated:.1f}s)")
                await self.end_round()
                break

            # Check deadline
            if self.is_deadline_reached():
                await self.end_game()
                break

            # TWO STATES: Position achieved (holding) vs Position not achieved (waiting)

            if self.position_achieved:
                # STATE 1: Position achieved - monitor if it's maintained
                current_time = time.time()
                position_held_time = current_time - self.position_start_time
                hold_remaining = position_hold_target - position_held_time
                current_second = int(current_time)
                if current_second != self.last_countdown_second and hold_remaining > 0:
                    logger.info(f"⏱️ Hold countdown: {int(hold_remaining)} seconds")
                    self.last_countdown_second = current_second

                # Check if position is still correct
                if not self.check_position_correct(self.current_position):
                    current_time = time.time()

                    # Check if still in grace period
                    if current_time < self.position_transition_deadline:
                        # GRACE PERIOD - No punishment yet
                        logger.warning(
                            f"⚠️ Position {self.current_position.upper()} lost during grace period - waiting for correction")

                        # Wait for correction (no shocking during grace period)
                        while not self.check_position_correct(self.current_position) and self.state == GameState.ROUND:
                            if self.check_both_sensors_lost():
                                await self.handle_sensor_loss_during_round()
                                return

                            # Check if grace period expired
                            if time.time() >= self.position_transition_deadline:
                                logger.error("⚠️ Grace period EXPIRED - starting punishment")
                                break

                            await asyncio.sleep(0.1)

                        # Check result
                        if self.check_position_correct(self.current_position):
                            # Corrected within grace period!
                            logger.info(f"✓ Position corrected within grace period")
                            self.position_start_time = time.time()  # Reset hold timer
                            await asyncio.sleep(0.1)
                            continue
                        # else: grace period expired, fall through to punishment

                    # VIOLATION AFTER GRACE PERIOD - Position not maintained!
                    violation_start_time = time.time()
                    logger.warning(
                        f"⚠️ [{violation_start_time:.3f}] Position {self.current_position.upper()} NOT MAINTAINED - VIOLATION")

                    # Send shock and audio SIMULTANEOUSLY (non-blocking)
                    asyncio.create_task(send_pishock(mode=PISHOCK_MODE_SHOCK))
                    play_violation()

                    self.position_achieved = False
                    self.consecutive_violations += 1
                    self.round_violations += 1

                    # Track shocks during this violation period
                    shocks_this_violation = 1
                    last_shock_time = violation_start_time

                    # Keep shocking every 5 seconds until position corrected or 10 shocks
                    while not self.check_position_correct(self.current_position) and self.state == GameState.ROUND:
                        if self.check_both_sensors_lost():
                            await self.handle_sensor_loss_during_round()
                            return

                        current_time = time.time()
                        time_since_last_shock = current_time - last_shock_time

                        # Send shock every 5 seconds
                        if time_since_last_shock >= 5.0:
                            shocks_this_violation += 1
                            self.consecutive_violations += 1

                            logger.warning(f"⚠️ Position still not maintained - Shock #{shocks_this_violation}")
                            asyncio.create_task(send_pishock(mode=PISHOCK_MODE_SHOCK))

                            last_shock_time = current_time

                            # Check for 10-shock void condition
                            if shocks_this_violation >= MAX_PISHOCK_CYCLES:
                                logger.error(f"10 shocks delivered without correction - VOIDING ROUND")
                                play_ten_in_row()
                                await self.void_round()
                                return

                        await asyncio.sleep(0.1)

                    # Position corrected - calculate violation time
                    violation_end_time = time.time()
                    violation_duration = violation_end_time - violation_start_time
                    violation_time_accumulated += violation_duration

                    # Reset timer for this position
                    self.position_achieved = True
                    self.position_start_time = time.time()
                    self.consecutive_violations = 0  # Reset on success

                    logger.info(
                        f"✓ [{self.position_start_time:.3f}] Position {self.current_position.upper()} re-achieved")
                    logger.info(
                        f"   Violation lasted: {violation_duration:.1f}s (total violations: {violation_time_accumulated:.1f}s)")
                    logger.info(f"   Hold timer reset - must hold for {position_hold_target:.1f}s from now")

                    await asyncio.sleep(0.1)
                    continue

                # Check if hold time complete
                if position_held_time >= position_hold_target:
                    # Hold complete - switch position
                    logger.info(
                        f"⏱️ [{current_time:.3f}] Hold complete! Held for {position_held_time:.1f}s (target: {position_hold_target:.1f}s)")
                    logger.info(f"    Switching from {self.current_position.upper()} to opposite position")

                    self.current_position = 'up' if self.current_position == 'down' else 'down'

                    switch_time = time.time()
                    logger.info(f"⏱️ [{switch_time:.3f}] Commanding {self.current_position.upper()}")
                    await self.command_position(self.current_position, is_rapid=False)

                    # Reset countdown tracker
                    self.last_countdown_second = int(time.time())

                    # Wait for position to be achieved (monitor task sets this)
                    # BUT don't wait forever - timeout after transition deadline + 2 seconds
                    wait_timeout = self.position_transition_deadline + 2.0

                    while not self.position_achieved and self.state == GameState.ROUND:
                        _ = self.get_board_angle()
                        if self.check_both_sensors_lost():
                            await self.handle_sensor_loss_during_round()
                            return

                        # Check if we've exceeded timeout
                        current_time = time.time()
                        if current_time >= wait_timeout:
                            logger.warning(f"⚠️ Position {self.current_position.upper()} wait timeout - exiting loop")
                            break  # Exit loop, position not achieved

                        # Countdown logging
                        remaining = self.position_transition_deadline - current_time
                        current_second = int(current_time)

                        if current_second != self.last_countdown_second and remaining > 0:
                            logger.info(f"⏱️ Transition countdown: {int(remaining)} seconds")
                            self.last_countdown_second = current_second

                        await asyncio.sleep(0.1)

                    # Check if position was actually achieved
                    if self.position_achieved:
                        # Position achieved - EXPLICIT timer reset
                        self.position_start_time = time.time()
                        achievement_time = self.position_start_time

                        # Generate NEW hold time for this position
                        config = self.get_level_config()
                        if self.current_position == 'up':
                            position_hold_target = random.uniform(*config['hold_time_up'])
                        else:  # down
                            position_hold_target = random.uniform(*config['hold_time_down'])

                        logger.info(f"⏱️ [{achievement_time:.3f}] {self.current_position.upper()} achieved!")
                        logger.info(f"🎲 New position hold time: {position_hold_target:.1f} seconds")

                        # Reset consecutive shock tracking (position achieved successfully)
                        self.consecutive_violations = 0

                        # Continue to next iteration to start monitoring hold
                        continue
                    else:
                        # Position NOT achieved after timeout
                        # Fall through to next iteration - STATE 2 will handle continuous shocking
                        logger.warning(
                            f"⚠️ Position {self.current_position.upper()} not achieved - entering continuous shocking mode")
                        # Don't continue, don't generate hold time - just let next iteration handle it

            else:
                # STATE 2: Position not yet achieved - waiting and shocking if taking too long
                current_time = time.time()
                time_waiting = current_time - self.position_command_start

                # Check if position is now achieved
                if self.check_position_correct(self.current_position):
                    # Position achieved! (detected in main loop, not monitor task)
                    # Note: Monitor task may have already set position_achieved=True
                    # Hold time was already generated in STATE 1 after position switch
                    logger.debug(f"STATE 2: Position {self.current_position.upper()} achieved")
                    await asyncio.sleep(0.1)
                    continue

                # Position still not achieved - check if we need to shock
                # Initial transition-time violation is handled by monitor_position_achievement()
                # But we need to CONTINUE shocking every 5 seconds after that

                if time_waiting > self.position_transition_deadline - self.position_command_start:
                    # Beyond initial violation time - need continuous shocking
                    # Check when we last shocked (use None check, not hasattr)
                    if self._continuous_shock_start is None:
                        # First time entering continuous shock mode
                        self._continuous_shock_start = current_time
                        self._continuous_shock_count = 1  # monitor_position_achievement already sent first shock
                        self._last_continuous_shock = current_time - 2  # Allow next shock in 3 seconds

                    time_since_last_shock = current_time - self._last_continuous_shock

                    if time_since_last_shock >= 5.0:
                        self._continuous_shock_count += 1
                        self.consecutive_violations += 1

                        logger.warning(
                            f"⚠️ Position {self.current_position.upper()} still not achieved - Continuous shock #{self._continuous_shock_count}")
                        asyncio.create_task(send_pishock(mode=PISHOCK_MODE_SHOCK))
                        self._last_continuous_shock = current_time

                        # Check for 10-shock void condition
                        if self._continuous_shock_count >= MAX_PISHOCK_CYCLES:
                            logger.error(f"10 shocks delivered, position never achieved - VOIDING ROUND")
                            play_ten_in_row()
                            await self.void_round()
                            return
                else:
                    # Still within initial transition window
                    # Reset continuous shock tracking
                    self._continuous_shock_start = None
                    self._continuous_shock_count = None
                    self._last_continuous_shock = None

            await asyncio.sleep(0.1)

    async def end_round(self):
        """End current round and determine pass/fail"""
        logger.info("=" * 60)
        logger.info("ROUND ENDING")
        logger.info("=" * 60)

        # Turn off all bulbs
        await all_bulbs_off()

        # Send vibration
        await send_vibration()

        # Determine pass/fail
        config = self.get_level_config()
        passed = self.round_violations < config['violation_limit']

        # Apply results (credits time, awards bonus if hard passed, advances/resets level)
        self.apply_round_result(passed)

        logger.info(f"Completed training: {self.completed_training_time / 60:.1f} minutes")
        logger.info(f"Remaining: {self.remaining_training_time / 60:.1f} minutes")

        # Check if training goal met
        if self.remaining_training_time <= 0:
            await self.end_game()
        else:
            # Start break
            await self.start_break()

    async def start_break(self):
        """Start mandatory break"""
        self.state = GameState.BREAK
        self.current_break_duration = random.randint(BREAK_DURATION_MIN, BREAK_DURATION_MAX)
        self.break_start_time = time.time()

        logger.info(f"Break started: {self.current_break_duration} seconds")

        # Play round over audio and get duration
        round_over_duration = play_round_over()

        # Turn off all lights
        await all_bulbs_off()

        # Wait for round_over audio to finish before playing status
        if round_over_duration > 0:
            await asyncio.sleep(round_over_duration + 0.3)  # Add 0.3s buffer

        # Play round status audio (passed or failed)
        if hasattr(self, '_last_round_passed'):
            if self._last_round_passed:
                play_round_passed()
            else:
                play_round_failed()

        # Start white noise
        start_white_noise()

        # Wait for break to end
        await self.run_break()

    async def run_break(self):
        """
        Run break period
        Subject can request extension via Button 1:
        - 50% chance of approval (if time remains)
        - Extension has no fixed duration (subject ends it)
        - Total pool: 5 hours
        - Fan activates after 15-25 min of extension
        - Subject ends extension by pressing any button
        """
        # Initialize button state for this break
        initial_button_1 = await read_button(BUTTON_1)
        initial_button_2 = await read_button(BUTTON_2)
        if initial_button_1 is not None:
            self._last_button_1_value = initial_button_1
        if initial_button_2 is not None:
            self._last_button_2_value = initial_button_2

        while self.state == GameState.BREAK:
            # If extension is active, handle it differently
            if self.extension_active:
                await self.run_extension()
                continue  # Loop continues after extension

            # Normal break logic
            elapsed = time.time() - self.break_start_time

            # Check if break time expired
            if elapsed >= self.current_break_duration:
                await self.end_break()
                break

            # Check deadline
            if self.is_deadline_reached():
                await self.end_game()
                break

            # Check Button 1 for extension request
            current_button_1 = await read_button(BUTTON_1)

            if current_button_1 is not None and self._last_button_1_value is not None:
                # Detect rising edge (button press)
                if current_button_1 > self._last_button_1_value:
                    current_time = time.time()
                    time_since_last_request = current_time - self.last_extension_request_time

                    # Check if cooldown period has passed
                    if time_since_last_request >= EXTENSION_REQUEST_COOLDOWN:
                        await self.process_extension_request()
                    else:
                        # Still in cooldown
                        remaining = EXTENSION_REQUEST_COOLDOWN - time_since_last_request
                        logger.debug(f"Extension request ignored - cooldown ({remaining:.1f}s remaining)")

                # Update last button value
                self._last_button_1_value = current_button_1

            await asyncio.sleep(0.1)

    async def process_extension_request(self):
        """
        Process extension request from Button 1
        - Check if time remains in pool
        - 50% chance if time available
        - Denied if no time or bad luck
        """
        logger.info("=" * 60)
        logger.info("EXTENSION REQUEST")
        logger.info("=" * 60)

        remaining_time = TOTAL_EXTENSION_TIME_ALLOWED - self.total_extension_time_used
        logger.info(f"Extension time remaining: {remaining_time / 3600:.2f} hours")

        # Increment request counter
        self.total_extension_requests += 1
        self.last_extension_request_time = time.time()

        # Check if any time remains
        if remaining_time <= 0:
            # NO TIME LEFT
            logger.info("✗ Extension DENIED - No time remaining in pool")
            logger.info(f"  Total requests: {self.total_extension_requests}")
            play_extension_denied_limit()
            return

        # Time available - 50% chance
        if random.random() < BREAK_EXTENSION_CHANCE:
            # GRANTED
            logger.info("✓ Extension GRANTED")
            logger.info(f"  Total requests: {self.total_extension_requests}")
            play_extension_granted()

            # Start extension
            await self.start_extension()
        else:
            # DENIED (bad luck, not limit)
            logger.info("✗ Extension DENIED - Unlucky")
            logger.info(f"  Total requests: {self.total_extension_requests}")
            play_extension_denied()

    async def start_extension(self):
        """
        Start break extension
        - Open-ended duration (subject decides when to end)
        - Fan activates after 15-25 minutes
        - Subject ends by pressing any button
        """
        logger.info("=" * 60)
        logger.info("EXTENSION STARTED")
        logger.info("=" * 60)
        logger.info("Press any button to end extension")

        self.extension_active = True
        self.extension_start_time = time.time()
        self.extension_fan_triggered = False

        # Randomize fan trigger time (15-25 minutes)
        self.extension_fan_trigger_time = self.extension_start_time + random.randint(
            EXTENSION_FAN_ACTIVATION_MIN,
            EXTENSION_FAN_ACTIVATION_MAX
        )
        fan_trigger_minutes = (self.extension_fan_trigger_time - self.extension_start_time) / 60
        logger.info(f"Fan will activate after {fan_trigger_minutes:.1f} minutes")

        # Reset button states
        self._last_button_1_value = await read_button(BUTTON_1)
        self._last_button_2_value = await read_button(BUTTON_2)

    async def run_extension(self):
        """
        Run extension period
        - Monitor time for fan activation
        - Wait for button press to end
        """
        current_time = time.time()
        extension_elapsed = current_time - self.extension_start_time

        # Check if fan should activate
        if not self.extension_fan_triggered and current_time >= self.extension_fan_trigger_time:
            logger.info("⚠️  Extension time limit reached - FAN ON")
            await fan_control("on")
            self.extension_fan_triggered = True

        # Check for button press to end extension
        current_button_1 = await read_button(BUTTON_1)
        current_button_2 = await read_button(BUTTON_2)

        button_pressed = False

        # Check Button 1
        if current_button_1 is not None and self._last_button_1_value is not None:
            if current_button_1 > self._last_button_1_value:
                button_pressed = True
                logger.info("Button 1 pressed - ending extension")
            self._last_button_1_value = current_button_1

        # Check Button 2
        if current_button_2 is not None and self._last_button_2_value is not None:
            if current_button_2 > self._last_button_2_value:
                button_pressed = True
                logger.info("Button 2 pressed - ending extension")
            self._last_button_2_value = current_button_2

        if button_pressed:
            await self.end_extension()

        # Log progress every minute
        if int(extension_elapsed) % 60 == 0 and extension_elapsed > 0:
            logger.info(f"Extension active: {extension_elapsed / 60:.1f} minutes")

        await asyncio.sleep(0.1)

    async def end_extension(self):
        """
        End extension period
        - Track time used
        - Turn off fan
        - Return to normal break
        """
        extension_duration = time.time() - self.extension_start_time

        logger.info("=" * 60)
        logger.info("EXTENSION ENDED")
        logger.info("=" * 60)
        logger.info(f"Extension duration: {extension_duration / 60:.1f} minutes")

        # Add to total used time
        self.total_extension_time_used += extension_duration
        remaining = TOTAL_EXTENSION_TIME_ALLOWED - self.total_extension_time_used

        logger.info(f"Total extension used: {self.total_extension_time_used / 3600:.2f} hours")
        logger.info(f"Extension remaining: {remaining / 3600:.2f} hours")

        # Turn off fan if it was on
        if self.extension_fan_triggered:
            logger.info("Turning off fan")
            await fan_control("off")

        # Reset extension state
        self.extension_active = False
        self.extension_fan_triggered = False

        # Continue break from where it left off
        # Break timer keeps running during extension

    def check_rapid_eligibility(self) -> bool:
        """
        Check if subject is eligible for rapid training (Phase 7)
        Requirements:
        - At least 3 consecutive clean rounds
        - No extension requests used

        Note: This is for Phase 7 implementation
        """
        # Phase 1: Not implemented yet, always return False
        return False

        # Phase 7 implementation (uncomment when ready):
        # if self.consecutive_clean_rounds < 3:
        #     return False
        #
        # # Any extension request disqualifies
        # if self.total_extension_requests > 0:
        #     logger.debug(f"Rapid ineligible: {self.total_extension_requests} extension requests")
        #     return False
        #
        # return True

    async def end_break(self):
        """End break period"""
        logger.info("Break ending...")

        # Stop white noise
        stop_white_noise()

        # Turn off fan if it's on (safety)
        if self.fan_active:
            await fan_control("off")
            self.fan_active = False

        # Go to preparation phase
        await self.enter_preparation()

    async def end_game(self):
        """End the game"""
        self.state = GameState.FINISHED
        self.is_running = False

        logger.info("=" * 60)
        logger.info("GAME ENDED")
        logger.info(f"Training completed: {self.completed_training_time / 60:.1f} minutes")
        logger.info(f"Training goal: {self.current_training_goal / 60:.1f} minutes")

        if self.remaining_training_time <= 0:
            logger.info("STATUS: GOAL ACHIEVED")
        elif self.is_deadline_reached():
            logger.info("STATUS: TIME EXPIRED")
        else:
            logger.info("STATUS: TERMINATED")
        logger.info("=" * 60)

        # Play end audio
        play_training_ended()

        # Start game end sequence (plug + all lights on forever)
        asyncio.create_task(game_end_sequence())

    # ========================================================================
    # MAIN UPDATE LOOP
    # ========================================================================

    async def update(self, delta_time: float):
        """Main game update - called every frame"""
        try:
            self.game_time += delta_time

            # Check for critical error
            if self.critical_error:
                await emergency_shutdown()
                return

            # Waiting for game start
            if not self.game_started:
                # Check button press to start
                pressed, self.last_button_1_value = await check_button_press(
                    BUTTON_1, self.last_button_1_value
                )
                if pressed:
                    await self.start_game()
                return

            # Game is running - state machine handles the rest
            # (update loops are in each state's run method)

        except Exception as e:
            logger.critical(f"Critical error in game update: {e}", exc_info=True)
            self.critical_error = True


# ============================================================================
# GAME LOOP
# ============================================================================

async def game_loop(game: UpDownGame):
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