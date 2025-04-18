###############################################################################
#
# File: app_controller.py
#
# Purpose: Provide callback functions for various UI elements like buttons that
# will be used to interface with the model.
#
###############################################################################
from PySide6.QtCore import QObject, QTimer, Slot, QMetaObject, QUrl, Q_ARG, Qt, Property, Signal, QAbstractListModel, QModelIndex
from PySide6.QtWidgets import QApplication, QStackedLayout
from PySide6.QtQml import QQmlComponent

import json
import os
from bnb.nfc import NFCListenerThread
from bnb.model import Model, Cart
from bnb import config
from typing import List, Callable
from bnb.mqtt import MqttClient
from bnb.email.send_email import send_order_confirmation_email
from twilio.rest import Client


open_doors_topic = "aux/control/doors"
open_hatch_topic = "aux/control/hatch"
open_doors_and_hatch_msg = "open"
shelf_data_topic = "shelf/data"
doors_status_topic = "aux/status/doors"
hatch_status_topic = "aux/status/hatch"

MQTT_LOCAL_BROKER_URL = os.getenv('MQTT_LOCAL_BROKER_URL', None)
MQTT_REMOTE_BROKER_URL = os.getenv('', None)

SHELF_1_MAC_ADDRESS = None
SHELF_2_MAC_ADDRESS = None
SHELF_3_MAC_ADDRESS = None
SHELF_4_MAC_ADDRESS = None

class CartModel(QAbstractListModel):
    def __init__(self, cart: Cart, parent=None):
        super().__init__(parent)
        self.cart = cart
        self._image_cache = {}  # Cache for image paths

    def roleNames(self):
        return {
            Qt.DisplayRole: b"display",
            Qt.UserRole + 1: b"name",
            Qt.UserRole + 2: b"price",
            Qt.UserRole + 3: b"quantity",
            Qt.UserRole + 4: b"image"  # New role for image path
        }
    
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.cart.get_all_items()):
            return None
            
        item = self.cart.get_all_items()[index.row()]
        quantity = self.cart.get_quantity(item)
        
        if role == Qt.DisplayRole:
            return f"{item.name} (x{quantity})"
        elif role == Qt.UserRole + 1:  # name
            return item.name
        elif role == Qt.UserRole + 2:  # price
            return item.price
        elif role == Qt.UserRole + 3:  # quantity
            return quantity
        elif role == Qt.UserRole + 4:  # image
            return self._get_image_path(item)
        return None
    
    def _get_image_path(self, item):
        # Get absolute path to images folder
        base_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__),  # Current file's directory (models/)
            "..",  # Move up to project root
            "images"  # Images folder
        ))
        
        # Default placeholder path
        placeholder = os.path.join(base_path, "placeholder.png")
        
        # Check if item has valid image
        if not hasattr(item, "image_path"):
            return placeholder  # Returns: /Users/.../bits-n-bytes-ui/images/placeholder.png
        
        # Build item's image path
        item_image = os.path.join(base_path, item.image_path)
        return item_image if os.path.exists(item_image) else placeholder

    def rowCount(self, parent=QModelIndex()):
        return len(self.cart.get_all_items())

    def addItem(self, item, caller):
        if item not in self.cart.get_all_items():
            # Insert a new row if the item is not already in the cart
            print(item.thumbnail_url)
            position = len(self.cart)
            self.beginInsertRows(QModelIndex(), position, position)
            self.cart.add_item(item)
            self.endInsertRows()
        else:
            # Just update the existing item's quantity
            position = self.cart.get_index(item)
            self.cart.add_items(item)
            top_left = self.index(position, 0)
            self.dataChanged.emit(top_left, top_left, [Qt.DisplayRole])

    def removeItem(self, item):
        if item in self.cart.items:
            position = list(self.cart.items.keys()).index(item)
            self.cart.remove_item(item)
            if self.cart.get_quantity(item) <= 0:
                # Remove the row if quantity reaches 0
                self.beginRemoveRows(QModelIndex(), position, position)
                del self.cart.items[item]
                self.endRemoveRows()
            else:
                # Just update the quantity
                top_left = self.index(position, 0)
                self.dataChanged.emit(top_left, top_left, [Qt.DisplayRole])

    def clear(self):
        self.beginResetModel()
        self.cart.clear_cart()
        self.endResetModel()

class Countdown(QObject):
    remainingTimeChanged = Signal()
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__()
        self._remaining_time = 10
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.updateTime)

    @Property(int, notify=remainingTimeChanged)
    def remainingTime(self):
        return self._remaining_time
        
    @Slot()
    def startCountdown(self):
        self._remaining_time = 10
        self.remainingTimeChanged.emit()  # Immediately update display
        self.timer.start()

    @Slot()
    def updateTime(self):
        if self._remaining_time > 0:
            self._remaining_time -= 1
            self.remainingTimeChanged.emit()
        else:
            self.finished.emit()
            self.timer.stop()
    
    @Slot()
    def stopTime(self):
        self.timer.stop()
    
    @Slot()
    def resumeTime(self):
        self.timer.start()

class AppController(QObject):
    
    openAdmin = Signal()
    notifyAdminUnlock = Signal()
    notifyEmailInput = Signal()
    notifyPhoneInput = Signal()
    hatchUnlock = Signal()
    doorsUnlock = Signal()

    _cartModel: CartModel
    _mqttRemoteClient: MqttClient
    _mqttLocalClient: MqttClient
    _countdown: Countdown
    _model: Model
    _nfc: NFCListenerThread
    _input: List
    _pattern: List

    def __init__(self):
        super().__init__()
        self._input = []
        self._pattern = json.loads(os.getenv("BNB_ADMIN_PATTERN"))
        self._nfc = NFCListenerThread()
        self._model = Model()
        self._countdown = Countdown(self)
        self._cartModel = CartModel(self._model._cart, self)
        self._phone_num = str
        self._email = str
        if(MQTT_LOCAL_BROKER_URL is not None):
            self._mqttLocalClient = MqttClient(MQTT_LOCAL_BROKER_URL, 1883)
            self._mqttLocalClient.add_topic(doors_status_topic, self.notifyDoorUnlock, qos=0)
            self._mqttLocalClient.add_topic(hatch_status_topic, self.notifyHatchUnlock, qos=1)
            self._mqttLocalClient.start()
        if(MQTT_REMOTE_BROKER_URL is not None):
            self._mqttRemoteClient = MqttClient(MQTT_REMOTE_BROKER_URL, 1883)
            self._mqttRemoteClient.add_topic(doors_status_topic, self.notifyDoorUnlock, qos=0)
            self._mqttRemoteClient.add_topic(hatch_status_topic, self.notifyHatchUnlock, qos=1)
            self._mqttRemoteClient.start()
    
    @Property(QObject, constant=True)
    def mqtt(self):
        return self._mqttClient

    @Property(QObject, constant=True)
    def cart(self):
        return self._cartModel

    @Property(QObject, constant=True)
    def countdown(self):
        return self._countdown

    @Property(QObject, constant=True)
    def shelf_manager(self):
        return self._model._shelf_manager
    
    def notifyDoorUnlock(self, msg: str):
        if msg == "open":
            self.doorsUnlock.emit()
        else:
            print("Unknown message received: ", msg)

    def notifyHatchUnlock(self, msg: str):
        if msg == "open":
            self.hatchUnlock.emit()
        else:
            print("Unknown message recieved: ", msg)

    @Slot()
    def open_doors(self):
       result = self._mqttLocalClient.post_message(open_doors_topic, open_doors_and_hatch_msg)
       return result[0] == 0 
    
    @Slot()
    def open_hatch(self):
        result = self._mqttLocalClient.post_message(open_hatch_topic, open_doors_and_hatch_msg)
        return result[0] == 0
    
    @Slot(result=str)
    def getName(self):
        return self._model.get_user_name()

    @Slot(result=float)
    def getSubtotal(self):
        return self._model._cart.get_subtotal()

    @Slot(result=str)
    def send_email(self):
        items = list()
        for item in self._model._cart._items:
            item_dict = {key: value for key, value in item.__dict__.items() if key in ['name', 'price', 'quantity']}
            items.append(item_dict)
        send_order_confirmation_email("sahil.h.patel@gmail.com", items, self.getSubtotal())
    
    @Slot()
    def send_sms(self):
        pass

    @Slot(str)
    def getPhoneNum(self, phone_num):
        self._phone_num = phone_num
        self.notifyPhoneInput.emit()

    @Slot(str)
    def getEmail(self, email):
        self._email = email
        self.notifyEmailInput.emit()

    def get_user_email(self):
        return self._email
    
    @Slot()
    def runNFC(self):
        if self.is_welcome_active:
            self._nfc.run()
        else:
            self.stopNFC()
    
    @Slot()
    def stopNFC(self):
        self._nfc.stop()

    @Slot()
    def checkSeq(self):
        if self._pattern == None:
            return "BNB_ADMIN_PATTERN not implemented in config.py"
        if self._input == self._pattern:
            self.openAdmin.emit()
            self.notifyAdminUnlock.emit()
            self._input.clear()
        elif len(self._input) == len(self._pattern):
            print("Incorrect pattern, try again.")

    @Slot()
    def getSlots(self):
        return self.shelf_manager.get_all_shelves()

    @Slot(int)
    def pushInput(self, num):
        self._input.append(num)

    @Slot()
    def exit(self):
        QApplication.instance().quit()

    @Slot()
    def start_shelf_manager(self):
        self._model._shelf_manager.start_loop()

if __name__ == "__main__":
    app = AppController()
    app.send_email()



