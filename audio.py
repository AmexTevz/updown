import os
import random
import logging
import asyncio
from typing import Optional
from pathlib import Path

try:
    import pygame

    pygame.mixer.init()
    AUDIO_AVAILABLE = True
except:
    AUDIO_AVAILABLE = False

from config import AUDIO_BASE_PATH, AUDIO_VOLUME

logger = logging.getLogger(__name__)


# ============================================================================
# AUDIO CONTEXT REGISTRY
# ============================================================================

class AudioRegistry:
    """
    Central registry for all audio feedback points
    Maps to actual folder names
    """

    # Startup/Calibration (main.py)
    FIRST_PRESS = "first_press"
    SECOND_PRESS = "second_press"

    # Position Commands (game.py)
    POSITION_DOWN = "down"
    POSITION_UP = "up"

    # Round Events (game.py)
    ROUND_STARTING = "round_starting"
    ROUND_OVER = "round_over"
    VIOLATION = "violation"  # First violation in pose only
    TEN_IN_ROW = "ten_in_row"  # 10 consecutive violations

    # Sensor Events (game.py)
    SENSOR_ISSUE = "sensor_issue"
    SENSOR_ISSUE_RESOLVED = "sensor_issue_resolved"

    # Extensions (Phase 6)
    EXTENSION_GRANTED = "extension_granted"
    EXTENSION_DENIED = "extension_denied"
    EXTENSION_DENIED_LIMIT = "extension_denied_limit"

    # Level announcements (Phase 6)
    EASY_LEVEL = "easy_level"
    MEDIUM_LEVEL = "medium_level"
    HARD_LEVEL = "hard_level"

    # Round status (Phase 6)
    ROUND_PASSED = "round_passed"
    ROUND_FAILED = "round_failed"

    EXTENSION_ENDED = "extension_ended"
    EXTENSION_EXPIRED = "extension_expired"

    # Game End (game.py)
    TRAINING_ENDED = "training_ended"


    @classmethod
    def get_all_contexts(cls):
        """Get all registered audio contexts"""
        return [
            value for name, value in vars(cls).items()
            if not name.startswith('_') and isinstance(value, str)
        ]


# ============================================================================
# AUDIO MANAGER
# ============================================================================

class AudioManager:
    def __init__(self):
        self.audio_available = AUDIO_AVAILABLE
        self.contexts = {}
        self.white_noise_file = None
        self.white_noise_playing = False
        self.white_noise_task = None

        if self.audio_available:
            logger.info("Audio system initialized")
            self._scan_audio_directory()
        else:
            logger.warning("Audio system not available - pygame not loaded")

    def _scan_audio_directory(self):
        """Scan audio directory for context folders and variations"""
        base_path = Path(AUDIO_BASE_PATH)

        if not base_path.exists():
            logger.warning(f"Audio directory not found: {AUDIO_BASE_PATH}")
            return

        logger.info(f"Scanning audio directory: {AUDIO_BASE_PATH}")

        # Scan for context folders
        for context_folder in base_path.iterdir():
            if context_folder.is_dir():
                context_name = context_folder.name
                variations = list(context_folder.glob("*.wav"))

                if variations:
                    self.contexts[context_name] = variations
                    logger.debug(f"  Found {len(variations)} variations for '{context_name}'")

        # Check for white_noise.wav in root
        white_noise = base_path / "white_noise.wav"
        if white_noise.exists():
            self.white_noise_file = str(white_noise)
            logger.info(f"  White noise file found")
        else:
            logger.warning(f"  White noise file not found: {white_noise}")

        logger.info(f"Audio scan complete: {len(self.contexts)} contexts found")

    def play(self, context: str, fallback_text: str = "") -> float:
        """
        Play audio for given context
        Randomly selects from available variations
        Falls back to logging if no audio file found
        Prevents overlapping audio by stopping previous sound

        Returns: Duration of the audio in seconds (0.0 if failed or unavailable)
        """
        if not self.audio_available:
            logger.info(f"[AUDIO] {fallback_text or context}")
            return 0.0

        if context not in self.contexts:
            logger.warning(f"[AUDIO] No audio for context '{context}' - using fallback")
            logger.info(f"[AUDIO - Missing files] {fallback_text or context}")
            return 0.0

        try:
            # Stop any currently playing non-white-noise audio
            # (Keep white noise playing on its dedicated channel)
            pygame.mixer.stop()  # Stops all channels except reserved ones

            # Select random variation
            audio_file = random.choice(self.contexts[context])
            logger.info(f"[AUDIO] Playing: {context} -> {audio_file.name}")

            # Load and play
            sound = pygame.mixer.Sound(str(audio_file))
            sound.set_volume(AUDIO_VOLUME)
            sound.play()

            # Get and return duration
            duration = sound.get_length()
            logger.debug(f"[AUDIO] Duration: {duration:.2f}s")
            return duration

        except Exception as e:
            logger.error(f"[AUDIO] Failed to play '{context}': {e}")
            logger.info(f"[AUDIO - Error fallback] {fallback_text or context}")
            return 0.0

    def start_white_noise_loop(self):
        """
        Start white noise with random restart every 25-50 seconds
        Runs as background task
        """
        if self.white_noise_playing:
            logger.warning("White noise already playing")
            return

        if not self.white_noise_file or not self.audio_available:
            logger.warning("White noise not available - file missing or audio disabled")
            return

        self.white_noise_playing = True
        self.white_noise_task = asyncio.create_task(self._white_noise_loop())
        logger.info("White noise loop started")

    async def _white_noise_loop(self):
        """
        Internal white noise loop
        Plays, waits 25-50 seconds, restarts
        """
        try:
            while self.white_noise_playing:
                try:
                    # Load and play white noise
                    sound = pygame.mixer.Sound(self.white_noise_file)
                    sound.set_volume(AUDIO_VOLUME * 0.7)  # Slightly quieter than feedback
                    channel = sound.play()

                    # Random duration: 25-50 seconds
                    duration = random.randint(25, 50)
                    logger.debug(f"White noise playing for {duration} seconds")

                    # Wait for duration
                    await asyncio.sleep(duration)

                    # Stop current playback
                    if channel and channel.get_busy():
                        channel.stop()

                    # Brief pause before restart (0.5-1 second)
                    await asyncio.sleep(random.uniform(0.5, 1.0))

                except Exception as e:
                    logger.error(f"Error in white noise loop: {e}")
                    await asyncio.sleep(5)  # Wait before retry

        except asyncio.CancelledError:
            logger.info("White noise loop stopped")

    def stop_white_noise(self):
        """Stop white noise loop"""
        if not self.white_noise_playing:
            return

        self.white_noise_playing = False

        if self.white_noise_task:
            self.white_noise_task.cancel()
            self.white_noise_task = None

        # Stop any currently playing white noise
        pygame.mixer.stop()

        logger.info("White noise stopped")

    def cleanup(self):
        """Cleanup audio system"""
        self.stop_white_noise()
        if self.audio_available:
            pygame.mixer.quit()


# ============================================================================
# GLOBAL AUDIO MANAGER INSTANCE
# ============================================================================

audio_manager = AudioManager()


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def play_audio(context: str, fallback_text: str = "") -> float:
    """
    Play audio for given context with fallback text
    Returns: Duration of the audio in seconds
    """
    return audio_manager.play(context, fallback_text)


def start_white_noise():
    """Start looping white noise"""
    audio_manager.start_white_noise_loop()


def stop_white_noise():
    """Stop white noise"""
    audio_manager.stop_white_noise()


def cleanup_audio():
    """Cleanup audio system"""
    audio_manager.cleanup()


# ============================================================================
# CONTEXT-SPECIFIC FUNCTIONS (all return duration in seconds)
# ============================================================================

# Startup/Calibration
def play_first_press() -> float:
    return play_audio(AudioRegistry.FIRST_PRESS, "Press again to confirm")


def play_second_press() -> float:
    return play_audio(AudioRegistry.SECOND_PRESS, "Game will start shortly")


# Position Commands
def play_position_down() -> float:
    return play_audio(AudioRegistry.POSITION_DOWN, "Down")


def play_position_up() -> float:
    return play_audio(AudioRegistry.POSITION_UP, "Up")


# Round Events
def play_round_starting() -> float:
    return play_audio(AudioRegistry.ROUND_STARTING, "Round starting")


def play_round_over() -> float:
    return play_audio(AudioRegistry.ROUND_OVER, "Round complete")


def play_violation() -> float:
    """Play on FIRST violation in a pose only"""
    return play_audio(AudioRegistry.VIOLATION, "Violation")


def play_ten_in_row() -> float:
    """Play when 10 consecutive violations trigger void"""
    return play_audio(AudioRegistry.TEN_IN_ROW, "Ten consecutive violations - round voided")


# Sensor Events
def play_sensor_issue() -> float:
    return play_audio(AudioRegistry.SENSOR_ISSUE, "Sensor disconnected")


def play_sensor_issue_resolved() -> float:
    return play_audio(AudioRegistry.SENSOR_ISSUE_RESOLVED, "Sensor reconnected")


# Extensions
def play_extension_granted() -> float:
    return play_audio(AudioRegistry.EXTENSION_GRANTED, "Extension granted")


def play_extension_denied() -> float:
    return play_audio(AudioRegistry.EXTENSION_DENIED, "Extension denied")


def play_extension_denied_limit() -> float:
    return play_audio(AudioRegistry.EXTENSION_DENIED_LIMIT, "No extension time remaining")


# Level announcements
def play_easy_level() -> float:
    return play_audio(AudioRegistry.EASY_LEVEL, "Easy level")


def play_medium_level() -> float:
    return play_audio(AudioRegistry.MEDIUM_LEVEL, "Medium level")


def play_hard_level() -> float:
    return play_audio(AudioRegistry.HARD_LEVEL, "Hard level")


# Round status
def play_round_passed() -> float:
    return play_audio(AudioRegistry.ROUND_PASSED, "Round passed")


def play_round_failed() -> float:
    return play_audio(AudioRegistry.ROUND_FAILED, "Round failed")


# Game End
def play_training_ended() -> float:
    return play_audio(AudioRegistry.TRAINING_ENDED, "Training complete")

def play_extension_ended() -> float:
    return play_audio(AudioRegistry.EXTENSION_ENDED, "Extension ended")


def play_extension_expired() -> float:
    return play_audio(AudioRegistry.EXTENSION_EXPIRED, "Extension time expired")