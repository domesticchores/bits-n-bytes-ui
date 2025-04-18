from statistics import median
from unicodedata import normalize

from PySide6.QtCore import Qt, QAbstractListModel, QModelIndex
from typing import List, Any, Tuple
import copy
import datetime

WEIGHT_UNIT = "g"
CERTAINTY_CONSTANT = 2  # number of update iterations before an item is classified as "added" or "removed"
ITERS_REQD_NO_UPDATE = 0
EXTRANEOUS_VALUE_LIMIT = 5000

class Item:
    def __init__(
            self, item_id, name, upc, price, units, avg_weight, std_weight,
            thumbnail_url, vision_class
    ):
        self.item_id = item_id
        self.name = name
        self.upc = upc
        self.price = price
        self.units = units
        self.avg_weight = avg_weight
        self.std_weight = std_weight
        self.thumbnail_url = thumbnail_url
        self.vision_class = vision_class

    def __str__(self):
        return (f'Item[{self.item_id},{self.name},UPC:{self.upc},${self.price},'
                f'{self.units}units,{self.avg_weight}{WEIGHT_UNIT},'
                f'{self.std_weight}{WEIGHT_UNIT},{self.thumbnail_url},'
                f'{self.vision_class}]')


    def __eq__(self, other):
        if isinstance(other, Item):
            return self.item_id == other.item_id
        else:
            return False


    def __hash__(self):
        return hash(self.item_id)


    
class User:
    def __init__(self, uid, name, thumb_img, balance, email, phone):
        self.uid = uid
        self.name = name
        self.thumb_img = thumb_img
        self.balance = balance
        self.email = email
        self.phone = phone
    
    def __str__(self):
        return (f'User[ID: {self.uid}, Name: {self.name}, Balance: {self.balance},\n Email: {self.email}, Phone: {self.phone}]')
    
class NFC:
    def __init__(self, id, assigned_user, type):
        self.uid = id
        self.assigned_user = assigned_user
        self.type = type
    
    def __str__(self):
        return (f'NFC[ID: {self.id}, UserID: {self.assigned_user}, Type: {self.type}]')



class Slot:

    items: List[Item]
    _previous_weight_g: float | None
    _conversion_factor: float
    _weight_store: list
    _last_pos: bool
    _last_neg: bool
    _previous_raw_weight: float | None
    _iterations_no_update: int

    def __init__(self, items: List[Item]):
        """
        Create a Slot
        :param items: A list of items in this slot
        """
        self.items = copy.deepcopy(items)
        self._previous_weight_g = None
        self._conversion_factor = .44
        self._weight_store = [0] * CERTAINTY_CONSTANT
        self._last_pos = False
        self._last_neg = False
        self._previous_raw_weight = 0
        self._iterations_no_update = 0


    def set_previous_weight(self, weight: float | None) -> None:
        """
        Set the previous weight of this shelf to this weight
        Args:
            weight: The weight to set as a float

        Returns:
        """
        self._previous_weight_g = weight


    def get_previous_weight(self) -> float | None:
        """
        Get previous weight of this slot
        Returns:

        """
        return copy.deepcopy(self._previous_weight_g)


    def set_previous_raw_weight(self, weight: float | None) -> None:
        """
        Set the previous weight of this shelf to this weight
        Args:
            weight: The weight to set as a float

        Returns:
        """
        self._previous_raw_weight = weight


    def get_previous_raw_weight(self) -> float | None:
        """
        Get previous weight of this slot
        Returns:

        """
        return copy.deepcopy(self._previous_raw_weight)


    def calc_conversion_factor(self, zero_weight_g: float, loaded_weight_g: float, known_weight_g: float) -> float:
        """
        Calculate and set the conversion factor of this slot.
        Args:
            zero_weight_g: The weight recorded by the load cells with nothing
            loaded on the platform.
            loaded_weight_g: The weight recorded by the load cells with an
            object of a known weight loaded on the platform
            known_weight_g: The known weight of the object

        Returns:

        """
        if loaded_weight_g == zero_weight_g:
            print("Loaded weight and zero weight are the same, can't calculate conversion factor.")
        else:
            self._conversion_factor = known_weight_g / (loaded_weight_g - zero_weight_g)
        return self._conversion_factor


    def set_conversion_factor(self, conversion_factor: float):
        self._conversion_factor = conversion_factor


    def update(self, new_weight: float, print_debug=False) -> List[Tuple[Item, int]]:
        """
        Update this shelf with a new weight value. This calculates what items
        were removed, and returns a list of tuples of (Item, int).  Positive
        numbers add to the cart, and negative remove from it.
        Args:
            new_weight: The new weight for this shelf.

        Returns:
        """
        self._previous_raw_weight = new_weight
        item = self.items[0]
        # Normalize weight using conversion factor
        normalized_weight_g = new_weight * self._conversion_factor
        #print(f"Normalized weight: {normalized_weight_g}g")
        # Add this weight to the weight store, and remove the oldest stored weight
        self._weight_store.insert(0, normalized_weight_g)
        oldest_weight = self._weight_store.pop()
        # Calculate rolling median weight
        rolling_median = median(self._weight_store)
        # Difference from previous iteration to now
        difference_g = rolling_median - self._previous_weight_g
        remainder_weight = abs(difference_g % item.avg_weight)
        if print_debug:
            print(f"Weight diff g: {difference_g}")
            print(f"\tRemainder: {remainder_weight}")
        if abs(difference_g) > EXTRANEOUS_VALUE_LIMIT:
            print(f"\tExtraneous value, ignoring.")
            return []
        quantity_to_modify_cart = 0
        # Check that remainder is within top std_dev or bottom_std of the avg_weight
        if  item.avg_weight - item.std_weight <= remainder_weight or remainder_weight <= item.std_weight:
            # Calculate quantity removed
            quantity = round(difference_g / item.avg_weight)
            if quantity > 0:
                if not self._last_pos:
                    print(f"\t{quantity} item(s) placed back")
                    quantity_to_modify_cart = quantity
                    self._last_pos = True
                    self._last_neg = 0
                    self._iterations_no_update = 0
            elif quantity < 0:
                if self._last_neg == 0:
                    print(f"\t{quantity} item(s) removed")
                    quantity_to_modify_cart = quantity
                    self._last_neg = abs(quantity)
                    self._last_pos = False
                    self._iterations_no_update = 0
            else:
                #print("No cart updates")
                if self._iterations_no_update >= ITERS_REQD_NO_UPDATE:
                    self._last_pos = False
                    self._last_neg = 0
                else:
                    self._iterations_no_update += 1
        self._previous_weight_g = oldest_weight
        return [(item, quantity_to_modify_cart)]



class Shelf:

    slots: List[Slot]
    last_report_time: datetime.datetime

    def __init__(self, slots: List[Slot], created_time: datetime.datetime, initial_weights: List[float | None]):
        """
        Args:
            slots: List of slots in this shelf
            created_time: The time the message was received that caused the
            creation of this shelf.
            initial_weights: A list of the initial weights for each slot.
        """
        self.slots = slots
        self.last_report_time = datetime.datetime(2022, 2, 2, 2, 2, 2, 2)
        # Only iterate the lowest number of times if the lengths are not equal to avoid errors
        j = min(len(initial_weights), len(slots))
        for i in range(j):
            if initial_weights[i] is not None:
                self.slots[i].set_previous_weight(initial_weights[i])



    def update(self, raw_weights: List[float], update_received_time: datetime.datetime) -> List[Tuple[Item, int]]:
        """
        Update this shelf with raw weights for each slot.
        Args:
            raw_weights: The raw weights from this update.
            update_received_time: The time the update was received.

        Returns:
        A list of tuples containing (Item, int) pairs, mapping Items that were
        added or removed from the cart with the quantity added or removed.
        Positive numbers add to the cart, negative remove from it.
        """
        self.last_report_time = update_received_time
        results_dict = dict()
        # Iterate through all weight values
        for i in range(4):
            # Make sure a slot corresponds to this weight
            if i < len(self.slots) and raw_weights[i] is not None:
                # Update the weight
                if self.slots[i] is not None:
                    items_added_list = self.slots[i].update(raw_weights[i], print_debug=False)
                    # Add items returned to the dictionary of total item differences
                    for item_added, quantity_added in items_added_list:
                        if item_added not in results_dict:
                            results_dict[item_added] = quantity_added
                        else:
                            results_dict[item_added] += quantity_added
        # Convert dictionary to list of tuples for returning
        results_list = list()
        for item in results_dict:
            results_list.append((item, results_dict[item]))
        return results_list



class Cart:
    def __init__(self):
        self.items = {}
        self.subtotal = 0.0;

    def add(self, item: Item):
        if item in self.items:
            self.items[item] += 1
        else:
            self.items[item] = 1

    def remove(self, item: Item):
        if item in self.items:
            self.items[item] -= 1

    def update_subtotal(self, caller):
        from screens.cart_screen import CartScreen
        if isinstance(caller, CartScreen):
            for item, quantity in self.items.items():
                print("Item:", item)
                print("Quantity:", quantity)
                self.subtotal += item.price
            print("Subtotal:", self.subtotal)
            return self.subtotal

    def get_subtotal(self):
        return self.subtotal
    
    def clear(self):
        print("Clearing cart")
        self.items = {}
        self.subtotal = 0.0

class ItemListModel(QAbstractListModel):
    def __init__(self, cart: Cart, parent=None):
        super().__init__(parent)
        self.cart = cart

    def rowCount(self, parent=QModelIndex()):
        return len(self.cart.items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.cart.items)):
            return None  # Return None for invalid index

        item_list = list(self.cart.items.keys())
        if not item_list:
            return None  # No items in the cart, return None

        item = item_list[index.row()]
        quantity = self.cart.items[item]

        if role == Qt.DisplayRole:
            return f"{item.name} (x{quantity})"
        elif role == Qt.ToolTipRole:
            return f"Price: ${item.price:.2f} each"  # Access price directly from the Item object

        return None

    def addItem(self, item, caller):
        if item not in self.cart.items:
            # Insert a new row if the item is not already in the cart
            position = len(self.cart.items)
            self.beginInsertRows(QModelIndex(), position, position)
            self.cart.add(item)
            self.endInsertRows()
        else:
            # Just update the existing item's quantity
            from screens.cart_screen import CartScreen
            position = list(self.cart.items.keys()).index(item)
            if isinstance(caller, CartScreen):
                self.cart.add(item)
            top_left = self.index(position, 0)
            self.dataChanged.emit(top_left, top_left, [Qt.DisplayRole])

    def removeItem(self, item):
        if item in self.cart.items:
            position = list(self.cart.items.keys()).index(item)
            self.cart.remove(item)
            if self.cart.items[item] <= 0:
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
        self.cart.items.clear()
        self.endResetModel()