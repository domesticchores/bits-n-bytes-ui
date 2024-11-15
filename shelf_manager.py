###############################################################################
#
# File: shelf_manager.py
#
# Purpose: Handle all interaction with shelves. The 'main_loop' function should
# be placed in a separate thread and provides watchdog functionality for
# shelves.
#
###############################################################################
from threading import Thread, Lock
from types import new_class
from typing import Dict
from models import Shelf, Slot, Item
import time
import datetime
import json

SHELF_ITEM_MAP = {
    "MAC_1": [ Slot([]) , Slot([]) , Slot([]) , Slot([]) ],
    "MAC_2": [ Slot([]) , Slot([]) , Slot([]) , Slot([]) ],
    "MAC_3": [ Slot([]) , Slot([]) , Slot([]) , Slot([]) ],
    "MAC_4": [ Slot([]) , Slot([]) , Slot([]) , Slot([]) ],
}
NUM_SLOTS_PER_SHELF = 4
LOOP_DELAY_MS = 200

class ShelfManager:

    _signal_end_lock: Lock
    _signal_end: bool
    _last_loop_ms: float
    _mac_to_shelf_map: Dict[str, Shelf]

    def __init__(self, add_to_cart_cb = None, remove_from_cart_cb = None):
        self._signal_end_lock = Lock()
        self._signal_end = False
        self._mac_to_shelf_map = dict()
        self._last_loop_ms = 0
        self.add_to_cart_cb = add_to_cart_cb
        self.remove_from_cart_cb = remove_from_cart_cb


    def on_shelf_data_cb(self, client, userdata, msg):
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
        json_data = json.load(msg)
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
            # Existing shelf
            item_quantity_changes = self._mac_to_shelf_map[mac].update(data, received_time)
            for item, quantity_change in item_quantity_changes:
                if quantity_change > 0:
                    for i in range(quantity_change):
                        self.add_to_cart_cb(item)
                elif quantity_change < 0:
                    for i in range(abs(quantity_change)):
                        self.remove_from_cart_cb(item)


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

            # TODO thread contents. Watchdog, etc.

            # Wait for next iteration
            while time.time() < (self._last_loop_ms + LOOP_DELAY_MS) / 1000:
                pass
            last_loop_ms = time.time() * 1000