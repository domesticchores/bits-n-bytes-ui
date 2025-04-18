###############################################################################
#
# File: old_shelf_manager.py
#
# Purpose: Handle all interaction with shelves. The 'main_loop' function should
# be placed in a separate thread and provides watchdog functionality for
# shelves.
#
###############################################################################
from threading import Thread, Lock
from types import new_class
from typing import Dict

import bnb.database as database
from models import Shelf, Slot, Item
import time
import datetime
import json
from bnb.mqtt import MqttClient
from os import environ

KNOWN_TARE_WEIGHT_G = 226.0

SHELF_ITEM_MAP = {
    "MAC_1": [Slot([]), Slot([]), Slot([]), Slot([])],
    "80:65:99:49:EF:8E": [ Slot([database.MOCK_ITEMS[9]]) , Slot([database.MOCK_ITEMS[14]]) , Slot([database.MOCK_ITEMS[1]]) , Slot([database.MOCK_ITEMS[6]]) ],
    "80:65:99:E3:EF:50": [ Slot([database.MOCK_ITEMS[9]]) , Slot([database.MOCK_ITEMS[14]]) , Slot([database.MOCK_ITEMS[1]]) , Slot([database.MOCK_ITEMS[6]]) ],
    "80:65:99:E3:8B:92": [ Slot([database.MOCK_ITEMS[13]]) , Slot([database.MOCK_ITEMS[11]]) , Slot([database.MOCK_ITEMS[10]]) , Slot([database.MOCK_ITEMS[12]]) ],
}
NUM_SLOTS_PER_SHELF = 4
LOOP_DELAY_MS = 200

SHELF_MQTT_BROKER_URL = environ.get('SHELF_MQTT_BROKER_URL', None)
SHELF_MQTT_BROKER_PORT = environ.get('SHELF_MQTT_BROKER_PORT', 1883)


class ShelfManager:

    _signal_end_lock: Lock
    _signal_end: bool
    _last_loop_ms: float
    _mac_to_shelf_map: Dict[str, Shelf]
    _mqtt_client: MqttClient | None

    def __init__(self, add_to_cart_cb = None, remove_from_cart_cb = None):
        self._signal_end_lock = Lock()
        self._signal_end = False
        self._mac_to_shelf_map = dict()
        self._last_loop_ms = 0
        self.add_to_cart_cb = add_to_cart_cb
        self.remove_from_cart_cb = remove_from_cart_cb

        # Configure MQTT client for the shelves
        if SHELF_MQTT_BROKER_URL is None:
            self._mqtt_client = None
        else:
            self._mqtt_client = MqttClient(SHELF_MQTT_BROKER_URL, SHELF_MQTT_BROKER_PORT)
            # Link the shelf data function to trigger when a packet is received on the 'shelf/data' topic
            self._mqtt_client.add_topic('shelf/data', self.on_shelf_data_cb)

        # TODO run main_loop() when it has real contents


    def on_shelf_data_cb(self, msg):
        """
        Callback for when MQTT data is received on the shelf data topic.
        :param msg:
        :return:
        """
        print("Received shelf data")


    def old_on_shelf_data_cb(self, client, userdata, msg):
        """
        Callback function for there is MQTT data received on the shelf data
        topic. This callback can be provided directly to the paho-mqtt library
        and no additional parsing is required.
        Args:
            client:
            userdata:
            msg:

        Returns:

        """
        received_time = datetime.datetime.now()

        # Parse MQTT message as JSON
        json_data = json.loads(msg.payload.decode("utf-8"))
        if "id" not in json_data or "data" not in json_data:
            # Ignore the JSON if it doesn't contain an "id" and "data" field
            print("ShelfManager: Received MQTT data without 'id' or 'data' field.")
            return

        mac = json_data["id"]
        raw_data = json_data["data"]

        # Check that shelf data matches expected format
        if not isinstance(raw_data, list):
            print(f"ShelfManager: Received invalid shelf data via MQTT ({mac})")
            return
        if len(raw_data) != NUM_SLOTS_PER_SHELF:
            print(f"ShelfManager: Received invalid shelf data via MQTT ({mac})")
            return

        # Cast all datapoints to floats
        data = list()
        for raw_data_point in raw_data:
            try:
                data.append(float(raw_data_point))
            except TypeError | ValueError:
                print(f"ShelfManager: Error casting datapoint '{raw_data_point}' to float. Using None instead.")
                data.append(None)

        # Check if this is a new or existing shelf
        if mac not in self._mac_to_shelf_map:
            # New shelf
            print(f"ShelfManager: New shelf connected ({mac})")
            # Check that the shelf is in the item map
            if mac not in SHELF_ITEM_MAP:
                print("ShelfManager: Above shelf not in SHELF_ITEM_MAP. Can't initialize!")
                return

            new_shelf = Shelf(SHELF_ITEM_MAP[mac], received_time, data)
            self._mac_to_shelf_map[mac] = new_shelf
        else:
            #print("ShelfManager: Received data from existing shelf")
            # Existing shelf
            item_quantity_changes = self._mac_to_shelf_map[mac].update(data, received_time)
            for item, quantity_change in item_quantity_changes:
                if quantity_change > 0:
                    for i in range(quantity_change):
                        self.remove_from_cart_cb(item)
                elif quantity_change < 0:
                    for i in range(abs(quantity_change)):
                        self.add_to_cart_cb(item)


    def set_conversion_factor(self, shelf_mac: str, slot_index: int, conversion_factor: float):
        if shelf_mac in self._mac_to_shelf_map:
            self._mac_to_shelf_map[shelf_mac].slots[slot_index].set_conversion_factor(conversion_factor)


    def tare_shelf(self, shelf_mac: str, slot_index: int, zero_weight: float, loaded_weight: float):
        """
        Tare a shelf
        Args:
            shelf_mac:
            slot_index:
            zero_weight:
            loaded_weight:

        Returns:

        """
        if shelf_mac in self._mac_to_shelf_map:
            conversion_factor = self._mac_to_shelf_map[shelf_mac].slots[slot_index].calc_conversion_factor(zero_weight, loaded_weight, KNOWN_TARE_WEIGHT_G)
            return conversion_factor


    def get_most_recent_value(self, shelf_mac: str, slot_index: int) -> float | None:
        if shelf_mac in self._mac_to_shelf_map:
            return self._mac_to_shelf_map[shelf_mac].slots[slot_index].get_previous_raw_weight()
        else:
            print("Get most recent value: Shelf not found")
            return None


    def main_loop(self):
        """
        Main loop for a thread
        Returns:
        """

        self._last_loop_ms = time.time() * 1000

        while True:

            # Break out of loop if end flag was set
            with self._signal_end_lock:
                if self._signal_end:
                    break

            # TODO add shelf watchdog

            # TODO post what shelves are available on an endpoint somewhere

            # Wait for next iteration
            while time.time() < (self._last_loop_ms + LOOP_DELAY_MS) / 1000:
                pass
            last_loop_ms = time.time() * 1000