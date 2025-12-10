"""
Configuration file for Up/Down Training Game
"""

# ============================================================================
# HARDWARE ADDRESSES
# ============================================================================
BULB_1 = 206  # DOWN position indicator
BULB_2 = 202  # UP position indicator
STROBE = 225  # Warning/preparation strobe light
FAN = 211     # Extended break fan (>10 min)
PLUG = 226    # Game end signal

BUTTON_1 = 227  # Break extension request
BUTTON_2 = 204  # Rapid training request

BASE_IP = "192.168.1."

# ============================================================================
# PISHOCK API - UPDATED WORKING CREDENTIALS
# ============================================================================
PISHOCK_API_KEY = "10d3642a-4faa-4d32-b7d4-0adb4f78adb9"
PISHOCK_USER = "tevzuss"
API_URL = "https://do.pishock.com/api/apioperate"

PISHOCK_EMITTER_1 = "34C8335871E"

# Mode 0 = shock, Mode 1 = vibrate
PISHOCK_MODE_SHOCK = "shock"
PISHOCK_MODE_VIBRATE = "vibrate"
PISHOCK_INTENSITY_MIN = 60
PISHOCK_INTENSITY_MAX = 100
PISHOCK_DURATION_MIN = 1
PISHOCK_DURATION_MAX = 3
MAX_PISHOCK_CYCLES = 10  # 10 consecutive violations = void round




# ============================================================================
# GAME TIMING
# ============================================================================
GAME_DURATION_HOURS = 10

TRAINING_TIME_MIN = 150 * 60
TRAINING_TIME_MAX = 240 * 60

ROUND_DURATION_MIN = 3 * 60
ROUND_DURATION_MAX = 6 * 60

BREAK_EXTENSION_CHANCE = 1.0                    # 50% chance of approval
TOTAL_EXTENSION_TIME_ALLOWED = 4 * 3600        # 5 hours total pool
EXTENSION_REQUEST_COOLDOWN = 15                 # 15 seconds between requests
EXTENSION_FAN_ACTIVATION_MIN = 15 * 60          # 15 minutes
EXTENSION_FAN_ACTIVATION_MAX = 25 * 60

POSITION_HOLD_MIN = 3
POSITION_HOLD_MAX = 15

PREPARATION_WINDOW = 20  # Strobe + audio, 15 sec before round
WARNING_PHASE = 10       # (not used now since prep = warning)

TRANSITION_TIME_NORMAL = 7
TRANSITION_TIME_RAPID = 5

VIOLATION_CORRECTION_TIME = 5
VOID_BREAK_DURATION = 3 * 60

MAX_EXTENSION_TIME = 5 * 3600
MAX_TRAINING_TIME = 5 * 3600
FAN_ACTIVATION_TIME = 10 * 60

BUTTON_LOSS_PATIENCE = 5 * 60

CLEAN_ROUND_BONUS = 5 * 60
THRESHOLD_PENALTY = 5 * 60
ADDITIONAL_VIOLATION_PENALTY = 1 * 60

RAPID_HOLD_TIME = 2
RAPID_DURATION_MIN = 2 * 60
RAPID_DURATION_MAX = 4 * 60
RAPID_SUSPENSE_WAIT = 3 * 60

BREAK_DURATION_MIN = 120  # 2 minutes
BREAK_DURATION_MAX = 240  # 4 minutes


# Pre-game wait time (after button confirmation)
# PREGAME_WAIT_MIN = 2 * 60  # 2 minutes (normal)
# PREGAME_WAIT_MAX = 4 * 60  # 4 minutes (normal)

PREGAME_WAIT_MIN = 10
PREGAME_WAIT_MAX = 15


PREGAME_WAIT_MIN_TESTING = 5   # 5 seconds (testing)
PREGAME_WAIT_MAX_TESTING = 10  # 10 seconds (testing)
# ============================================================================
# SENSOR THRESHOLDS
# ============================================================================
ANGLE_DOWN_THRESHOLD = 20
ANGLE_UP_THRESHOLD = 80

SENSOR_CHECK_RATE = 30
SENSOR_PATIENCE_TIME = 2 * 3600  # 2 HOURS patience for sensor reconnection

# ============================================================================
# AUDIO
# ============================================================================
AUDIO_BASE_PATH = "audio"
AUDIO_VOLUME = 0.7

# ============================================================================
# NETWORK
# ============================================================================
NETWORK_RETRY_DELAY = 2
NETWORK_MAX_RETRIES = 3
BUTTON_CHECK_INTERVAL = 0.1

# ============================================================================
# LIGHTING BEHAVIOR
# ============================================================================
POSITION_CONFIRMATION_DURATION = 1.0  # Bulb stays ON 1 second to confirm
BULB_SAFETY_TIMEOUT = 8  # Turn off after 8 sec if never achieved

# ============================================================================
# HARDWARE MONITORING
# ============================================================================
HARDWARE_MONITOR_INTERVAL = 10  # Check every 10 seconds for reconnection

# ============================================================================
# TESTING MODE
# ============================================================================

# ============================================================================
# LEVEL SYSTEM (Phase 6 - Simplified)
# ============================================================================


LEVEL_CONFIG = {
    'easy': {
        'round_duration': (180, 300),      # 3-5 minutes
        'transition_time': (8, 12),        # 8-12 seconds random per command
        'hold_time_up': (3, 9),            # 3-9 seconds
        'hold_time_down': (6, 18),         # 6-18 seconds
        'violation_limit': 6               # Less than 6 to pass
    },
    'medium': {
        'round_duration': (240, 360),      # 4-6 minutes
        'transition_time': (6, 10),        # 6-10 seconds
        'hold_time_up': (6, 15),           # 6-15 seconds
        'hold_time_down': (5, 12),         # 5-12 seconds
        'violation_limit': 4               # Less than 4 to pass
    },
    'hard': {
        'round_duration': (300, 420),      # 5-7 minutes
        'transition_time': (5, 8),         # 5-8 seconds
        'hold_time_up': (10, 20),          # 10-20 seconds
        'hold_time_down': (3, 10),         # 3-10 seconds
        'violation_limit': 2               # Less than 2 to pass
    }
}

# Cycle completion bonus (awarded only when all three levels passed)
CYCLE_COMPLETION_BONUS = 20 * 60  # 20 minutes
TESTING_MODE = False

if TESTING_MODE:
    print("="*60)
    print("TESTING MODE - Shortened times")
    print("="*60)

    GAME_DURATION_HOURS = 1
    TRAINING_TIME_MIN = 5 * 60
    TRAINING_TIME_MAX = 10 * 60
    ROUND_DURATION_MIN = 60
    ROUND_DURATION_MAX = 120
    BREAK_DURATION_MIN = 20
    BREAK_DURATION_MAX = 30
    POSITION_HOLD_MIN = 8
    POSITION_HOLD_MAX = 20
    PREPARATION_WINDOW = 20
    VOID_BREAK_DURATION = 30
    SENSOR_PATIENCE_TIME = 2 * 60  # 2 minutes in testing mode
