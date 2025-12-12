import asyncio
import bleak
import math
from collections import deque
from dataclasses import dataclass
import time
import threading
from enum import Enum
from typing import Dict, Optional
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PRINT_ANGLES = True

def set_angle_printing(enabled: bool):
    """Control whether angles are continuously printed"""
    global PRINT_ANGLES
    PRINT_ANGLES = enabled

class SensorState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class SensorFrame:
    """A data class representing a single frame of sensor data.

    This class encapsulates data from a single sensor reading, including the sensor's
    identifier, timestamp of the reading, and the measured angle on the X-axis.

    Attributes:
        sensor_id (str): Unique identifier for the sensor that generated this frame.
        timestamp (float): Unix timestamp when the sensor reading was taken.
        angle_x (int): The measured angle on the X-axis in degrees, ranging from -180 to 180.
    """
    sensor_id: str
    timestamp: float
    angle_x: int  # Just store the X angle as integer

    def is_valid(self) -> bool:
        """Validates the sensor frame data.

        Performs basic validation checks on the sensor data to ensure it's within
        acceptable ranges and properly formatted.

        Returns:
            bool: True if the sensor data is valid, False otherwise.

        Note:
            - Checks if angle_x is within -180 to 180 degrees
            - Logs the angle value for debugging purposes
            - Catches and logs any validation errors
        """
        try:
            if PRINT_ANGLES:
                # Just log the angle value
                logger.info(f"{self.sensor_id} Angle X: {self.angle_x}°")
            return -180 <= self.angle_x <= 180
        except Exception as ex:
            logger.error(f"Validation error for sensor {self.sensor_id}: {ex}")
            return False


class SensorDataQueue:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Keep track of all sensors
            cls._instance.queues = {
                'w_back.txt': deque(maxlen=100),
                'w_left.txt': deque(maxlen=100),
                'w_right.txt': deque(maxlen=100),
                'Orientation.txt': deque(maxlen=100)
            }
            cls._instance.sensor_states: Dict[str, SensorState] = {
                'w_back.txt': SensorState.DISCONNECTED,
                'w_left.txt': SensorState.DISCONNECTED,
                'w_right.txt': SensorState.DISCONNECTED,
                'Orientation.txt': SensorState.DISCONNECTED
            }
            cls._instance.last_update_time: Dict[str, float] = {}
        return cls._instance

    def add_frame(self, sensor_file: str, frame: SensorFrame):
        with self._lock:
            if sensor_file not in self.queues:
                return

            if not frame.is_valid():
                logger.warning(f"Invalid sensor data received from {sensor_file}")
                return

            self.queues[sensor_file].append(frame)
            self.last_update_time[sensor_file] = time.time()
            self.sensor_states[sensor_file] = SensorState.CONNECTED

    def get_all_angles(self) -> Dict[str, int]:
        """Get current X angles from all sensors"""
        with self._lock:
            angles = {}
            for sensor_id, queue in self.queues.items():
                if queue:  # If queue has data
                    frame = queue[-1]  # Get latest frame
                    angles[sensor_id] = frame.angle_x
                else:
                    angles[sensor_id] = 0
            return angles

    def get_sensor_state(self, sensor_id: str) -> SensorState:
        """Get the current state of a sensor"""
        with self._lock:
            # Check if sensor hasn't updated in 5 seconds
            last_update = self.last_update_time.get(sensor_id, 0)
            if time.time() - last_update > 5:
                self.sensor_states[sensor_id] = SensorState.DISCONNECTED
            return self.sensor_states.get(sensor_id, SensorState.DISCONNECTED)

    def set_sensor_state(self, sensor_id: str, state: SensorState):
        """Set the state of a sensor"""
        with self._lock:
            if sensor_id in self.sensor_states:
                self.sensor_states[sensor_id] = state
                if state == SensorState.DISCONNECTED:
                    self.last_update_time[sensor_id] = 0


# Fixed mapping between sensor UUIDs and file names
ADDRESS_TO_FILE = {
    '81A3B8DF-59E8-B337-09DC-0C33863CF264': 'w_back.txt',
    'FE0D4665-559D-D7E3-B73C-C8D1397B6E28': 'w_left.txt',
    '094423B0-FCBC-0FBE-4C7F-1B882B588D72': 'w_right.txt',
    '13BF5CF8-B446-0026-588C-18F82496855C': 'Orientation.txt',
    '427021DB-CEB1-2F93-A6E6-3C495FC42BCD': 'Orientation.txt'
}

# Create global sensor queue
sensor_queue = SensorDataQueue()


class DeviceModel:
    def __init__(self, deviceName, mac, callback_method, sensor_file, uuids=None):
        logger.info(f"Initialize device model for sensor {sensor_file}")
        self.deviceName = deviceName
        self.mac = mac
        self.client = None
        self.writer_characteristic = None
        self.isOpen = False
        self.callback_method = callback_method
        self.deviceData = {}
        self.TempBytes = []
        self.sensor_file = sensor_file
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.last_error_time = 0
        self.uuids = uuids or {
            'service': "0000ffe5-0000-1000-8000-00805f9a34fb",
            'read': "0000ffe4-0000-1000-8000-00805f9a34fb",
            'write': "0000ffe9-0000-1000-8000-00805f9a34fb"
        }

    async def openDevice(self):
        """
        Keep trying to connect forever
        Exponential backoff but never give up
        """
        while True:
            try:
                sensor_queue.set_sensor_state(self.sensor_file, SensorState.CONNECTING)
                logger.info(f"[{self.sensor_file}] Opening device (attempt #{self.reconnect_attempts + 1})...")

                async with bleak.BleakClient(self.mac, timeout=20.0) as client:
                    self.client = client
                    self.isOpen = True
                    self.reconnect_attempts = 0  # Reset on successful connection

                    logger.info(f"✓ [{self.sensor_file}] Connected successfully!")
                    sensor_queue.set_sensor_state(self.sensor_file, SensorState.CONNECTED)

                    await self._setup_characteristics()

                    # Stay connected
                    while self.isOpen and client.is_connected:
                        await asyncio.sleep(1)

                    # If we get here, connection was lost
                    logger.warning(f"⚠️ [{self.sensor_file}] Connection lost")
                    self.isOpen = False

            except bleak.BleakError as ex:
                # Bluetooth-specific errors
                self.isOpen = False
                self.reconnect_attempts += 1
                sensor_queue.set_sensor_state(self.sensor_file, SensorState.ERROR)

                logger.warning(f"✗ [{self.sensor_file}] BLE error: {ex}")

            except asyncio.TimeoutError:
                # Connection timeout
                self.isOpen = False
                self.reconnect_attempts += 1
                sensor_queue.set_sensor_state(self.sensor_file, SensorState.ERROR)

                logger.warning(f"✗ [{self.sensor_file}] Connection timeout")

            except Exception as ex:
                # Other errors
                self.isOpen = False
                self.reconnect_attempts += 1
                sensor_queue.set_sensor_state(self.sensor_file, SensorState.ERROR)

                logger.error(f"✗ [{self.sensor_file}] Unexpected error: {ex}")

            # Exponential backoff (cap at 30 seconds)
            wait_time = min(30, 2 ** min(self.reconnect_attempts, 5))
            logger.info(f"[{self.sensor_file}] Retrying in {wait_time} seconds...")
            await asyncio.sleep(wait_time)

            # NEVER BREAK - keep trying forever

    async def _setup_characteristics(self):
        target_service_uuid = self.uuids['service']
        target_characteristic_uuid_read = self.uuids['read']
        target_characteristic_uuid_write = self.uuids['write']

        for service in self.client.services:
            if service.uuid == target_service_uuid:
                for characteristic in service.characteristics:
                    if characteristic.uuid == target_characteristic_uuid_read:
                        await self.client.start_notify(characteristic.uuid, self.onDataReceived)
                    elif characteristic.uuid == target_characteristic_uuid_write:
                        self.writer_characteristic = characteristic
                        asyncio.create_task(self.sendDataTh())

        if not self.writer_characteristic:
            raise Exception("Required characteristics not found")

    def set(self, key, value):
        try:
            if key.startswith("Ang"):
                value = min(max(math.ceil(value), -180), 180)
            elif key.startswith("Acc"):
                value = min(max(math.ceil(value), -16), 16)
            elif key.startswith("As"):
                value = min(max(math.ceil(value), -2000), 2000)
            elif key.startswith("H"):
                value = min(max(math.ceil(value), -4900), 4900)
            elif key.startswith("Q"):
                value = min(max(math.ceil(value * 1000), -1000), 1000)
            self.deviceData[key] = value
        except Exception as ex:
            logger.error(f"Error setting value for {key}: {ex}")

    def get(self, key):
        return self.deviceData.get(key)

    async def sendDataTh(self):
        await asyncio.sleep(3)
        while self.isOpen:
            await self.readReg(0x3A)
            await asyncio.sleep(0.1)
            await self.readReg(0x51)
            await asyncio.sleep(0.1)

    def onDataReceived(self, sender, data):
        tempdata = bytes.fromhex(data.hex())
        for var in tempdata:
            self.TempBytes.append(var)
            if len(self.TempBytes) == 1 and self.TempBytes[0] != 0x55:
                del self.TempBytes[0]
                continue
            if len(self.TempBytes) == 2 and (self.TempBytes[1] != 0x61 and self.TempBytes[1] != 0x71):
                del self.TempBytes[0]
                continue
            if len(self.TempBytes) == 20:
                self.processData(self.TempBytes)
                self.TempBytes.clear()

    def processData(self, Bytes):
        if Bytes[1] == 0x61:
            Ax = self.getSignInt16(Bytes[3] << 8 | Bytes[2]) / 32768 * 16
            Ay = self.getSignInt16(Bytes[5] << 8 | Bytes[4]) / 32768 * 16
            Az = self.getSignInt16(Bytes[7] << 8 | Bytes[6]) / 32768 * 16
            Gx = self.getSignInt16(Bytes[9] << 8 | Bytes[8]) / 32768 * 2000
            Gy = self.getSignInt16(Bytes[11] << 8 | Bytes[10]) / 32768 * 2000
            Gz = self.getSignInt16(Bytes[13] << 8 | Bytes[12]) / 32768 * 2000
            AngX = self.getSignInt16(Bytes[15] << 8 | Bytes[14]) / 32768 * 180
            AngY = self.getSignInt16(Bytes[17] << 8 | Bytes[16]) / 32768 * 180
            AngZ = self.getSignInt16(Bytes[19] << 8 | Bytes[18]) / 32768 * 180
            self.set("AccX", Ax)
            self.set("AccY", Ay)
            self.set("AccZ", Az)
            self.set("AsX", Gx)
            self.set("AsY", Gy)
            self.set("AsZ", Gz)
            self.set("AngX", AngX)
            self.set("AngY", AngY)
            self.set("AngZ", AngZ)
            self.callback_method(self, self.sensor_file)
        else:
            if Bytes[2] == 0x3A:
                Hx = self.getSignInt16(Bytes[5] << 8 | Bytes[4]) / 120
                Hy = self.getSignInt16(Bytes[7] << 8 | Bytes[6]) / 120
                Hz = self.getSignInt16(Bytes[9] << 8 | Bytes[8]) / 120
                self.set("HX", Hx)
                self.set("HY", Hy)
                self.set("HZ", Hz)
            elif Bytes[2] == 0x51:
                Q0 = self.getSignInt16(Bytes[5] << 8 | Bytes[4]) / 32768
                Q1 = self.getSignInt16(Bytes[7] << 8 | Bytes[6]) / 32768
                Q2 = self.getSignInt16(Bytes[9] << 8 | Bytes[8]) / 32768
                Q3 = self.getSignInt16(Bytes[11] << 8 | Bytes[10]) / 32768
                self.set("Q0", Q0)
                self.set("Q1", Q1)
                self.set("Q2", Q2)
                self.set("Q3", Q3)

    @staticmethod
    def getSignInt16(num):
        if num >= pow(2, 15):
            num -= pow(2, 16)
        return num

    async def sendData(self, data):
        try:
            if self.client.is_connected and self.writer_characteristic is not None:
                await self.client.write_gatt_char(self.writer_characteristic.uuid, bytes(data))
        except Exception as ex:
            logger.error(f"Error sending data: {ex}")

    async def readReg(self, regAddr):
        await self.sendData(self.get_readBytes(regAddr))

    @staticmethod
    def get_readBytes(regAddr):
        return [0xff, 0xaa, 0x27, regAddr, 0]


def updateData(DeviceModel, sensor_file=None):
    if not sensor_file:
        return

    try:
        # Get the X angle and convert to integer
        angle_x = int(round(float(DeviceModel.get("AngX") or 0)))

        # Create sensor frame
        frame = SensorFrame(
            sensor_id=sensor_file,
            timestamp=time.time(),
            angle_x=angle_x
        )

        # Add to real-time queue
        sensor_queue.add_frame(sensor_file, frame)

    except Exception as ex:
        logger.error(f"Error updating data for {sensor_file}: {ex}")
        logger.error(f"Raw device data: {DeviceModel.deviceData}")
        sensor_queue.set_sensor_state(sensor_file, SensorState.ERROR)


async def scan():
    try:
        devices = await bleak.BleakScanner.discover()
        found_devices = []
        for d in devices:
            if d.name is not None and "WT" in d.name:
                # Use advertisement_data instead of metadata
                if hasattr(d, 'advertisement_data'):
                    uuids = d.advertisement_data.service_uuids
                else:
                    uuids = []
                logger.info(f"Device: {d.name}, Address: {d.address}, UUIDs: {uuids}")
                found_devices.append(d)
        if len(found_devices) == 0:
            pass
        return found_devices
    except Exception as ex:
        logger.error(f"Bluetooth search failed to start: {ex}")
        return []


async def connect_to_devices(device_list):
    tasks = []
    for device in device_list:
        try:
            sensor_file = ADDRESS_TO_FILE.get(device.address)
            if sensor_file:
                logger.info(f"Connecting to {device.address} and mapping to {sensor_file}")
                sensor_device = DeviceModel(f"Sensor_{device.address}", device.address, updateData, sensor_file)
                tasks.append(asyncio.create_task(sensor_device.openDevice()))
            else:
                logger.warning(f"Address {device.address} not found in ADDRESS_TO_FILE mapping.")
        except Exception as e:
            logger.error(f"Error connecting to device {device.address}: {e}")

    await asyncio.gather(*tasks)


async def main():
    """
    Main sensor loop - runs continuously throughout the game
    Scans for sensors, connects, and automatically reconnects when they drop
    Periodic rescanning to catch reconnected sensors
    Never gives up, keeps trying forever
    """
    logger.info("=" * 70)
    logger.info("SENSOR MONITORING SYSTEM STARTED")
    logger.info("Will continuously scan and reconnect throughout game")
    logger.info("=" * 70)

    scan_count = 0
    active_connections = {}  # Track connection tasks by address
    last_scan_time = 0
    RESCAN_INTERVAL = 10  # Rescan every 10 seconds

    while True:  # ← INFINITE LOOP - Never stops trying
        try:
            current_time = time.time()

            # Time to scan (initial or periodic)
            if current_time - last_scan_time >= RESCAN_INTERVAL:
                scan_count += 1
                logger.debug(f"Sensor scan #{scan_count}...")
                last_scan_time = current_time

                # Scan for Bluetooth devices
                found_devices = await scan()

                if len(found_devices) == 0:
                    if scan_count % 6 == 0:  # Log every minute (6 scans * 10 sec)
                        pass
                else:
                    # Limit to 4 devices
                    if len(found_devices) > 4:
                        found_devices = found_devices[:4]

                    # Check each found device
                    for device in found_devices:
                        sensor_file = ADDRESS_TO_FILE.get(device.address)
                        if not sensor_file:
                            continue

                        # Check if we already have a connection task for this device
                        if device.address in active_connections:
                            task = active_connections[device.address]

                            # Check if task is still running
                            if not task.done():
                                # Task running - check if sensor is actually connected
                                state = sensor_queue.get_sensor_state(sensor_file)

                                if state == SensorState.CONNECTED:
                                    # All good, skip
                                    continue
                                else:
                                    # Task running but sensor not connected (connecting/error)
                                    # Let it keep trying, skip for now
                                    continue
                            else:
                                # Task completed/crashed - restart it
                                logger.warning(f"[{sensor_file}] Connection task ended, restarting...")

                                # Check if task had an exception
                                try:
                                    task.result()
                                except Exception as e:
                                    logger.error(f"[{sensor_file}] Task exception: {e}")

                                del active_connections[device.address]

                        # Start new connection task
                        logger.info(f"Starting connection to {device.address} ({sensor_file})")
                        sensor_device = DeviceModel(
                            f"Sensor_{device.address}",
                            device.address,
                            updateData,
                            sensor_file
                        )
                        task = asyncio.create_task(sensor_device.openDevice())
                        active_connections[device.address] = task

            # Clean up completed tasks
            for address in list(active_connections.keys()):
                if active_connections[address].done():
                    del active_connections[address]

            # Sleep briefly before next check
            await asyncio.sleep(1)

        except asyncio.CancelledError:
            # Game is shutting down, exit gracefully
            logger.info("Sensor system shutdown requested")

            # Cancel all active connection tasks
            for task in active_connections.values():
                task.cancel()

            break

        except Exception as e:
            # Handle any unexpected errors
            logger.error(f"Sensor system error: {e}", exc_info=True)
            await asyncio.sleep(5)
            # Loop continues - never gives up

    logger.info("Sensor monitoring system stopped")

if __name__ == "__main__":
    asyncio.run(main())