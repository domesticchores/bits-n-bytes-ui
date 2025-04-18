###############################################################################
#
# File: database.py
#
# Author: Isaac Ingram
#
# Purpose: Provide a connection to the database
#
###############################################################################
import os
import requests
from models import Item, User, NFC
from typing import List
import config

API_ENDPOINT = os.getenv("BNB_API_ENDPOINT", '')
AUTHORIZATION_KEY = os.getenv("BNB_AUTHORIZATION_KEY", '')

MOCK_ITEMS = {
    1: Item(1, "Little Bites Chocolate", "123456789012", 2.10, 100, 47, 10, "images/item_placeholder.png", "pouch"),
    2: Item(2, "Little Bites Party", "234567890123", 2.10, 50, 47, 10, "images/item_placeholder.png", "pouch"),
    3: Item(3, "Skittles Gummies", "345678901234", 2.40, 75, 164.4, 15, "images/item_placeholder.png", "bottle"),
    4: Item(4, "Swedish Fish Mini Tropical", "456789012345", 3.50, 120, 226, 10, "images/item_placeholder.png", "pouch"),
    5: Item(5, "Sour Patch Peach", "567890123456", 3.50, 90, 228, 15, "images/item_placeholder.png", "cylinder"),
    6: Item(6, "Brownie Brittle Chocolate Chip", "678901234567", 34.99, 60, 78, 10, "images/item_placeholder.png", "rectangle"),
    7: Item(7, "Swedish Fish Original", "789012345678", 19.99, 100, 141, 10, "images/item_placeholder.png", "pouch"),
    8: Item(8, "Welch's Fruit Snacks", "890123456789", 39.99, 40, 142, 14, "images/item_placeholder.png", "rectangle"),
    9: Item(9, "Sour Patch Kids", "", 3.50, 100, 226, 20, "images/item_placeholder.png", "sour-patch"),
    10: Item(10, "12 Pack Wild Cherry Pepsi", "", 5.50, 100, 4000, 500, "images/item_placeholder.png", "pepsi-box"),
    11: Item(11, "12 Pack Loganberry", "", 5.50, 100, 4000, 500, "images/item_placeholder.png", "loganberry-box"),
    12: Item(12, "EMPTY", "", 0, 100, 10000000, 0, "images/item_placeholder.png", ""),
    13: Item(13, "Wild Cherry Pepsi Can", "", 2.50, 100, 200, 20, "images/item_placeholder.png", ""),
    14: Item(14, "Little Bites Blueberry", "123456789012", 2.10, 100, 47, 10, "images/item_placeholder.png", "pouch"),
}

MOCK_USERS = {
    # 1: User(1, "Tag 1", "258427912599", 20.00, "imagine", "", ""),
    1: User(1, "User1", "", 10.00, "test@ema.il", "1234567")

}

MOCK_NFC = {
    1: NFC(1, 1, "MIFARE")
}

# Use mock data if USE_MOCK_DATA environment variable is set to 'true'. If it
# isn't set to 'true' (including not being set at all), it this defaults to
# False.
USE_MOCK_DATA = os.getenv("USE_MOCK_DATA", 'false').lower() == 'true'

REQUEST_HEADERS = {"Authorization": AUTHORIZATION_KEY}

def is_reachable() -> bool:
    """
    Check if the database is reachable
    :return: True if the database is reachable, False otherwise
    """
    if USE_MOCK_DATA:
        return True
    else:
        print("Check If Reachable (GET)")
        try:
            requests.get(API_ENDPOINT, headers=REQUEST_HEADERS)
            return True
        except requests.RequestException:
            print(f"\tExperienced Request Exception")
            return False


def get_items() -> List[Item]:
    """
    Get all items
    :return: A List of Item. If there is an error, an empty list is returned
    """
    print("GET /items")
    if USE_MOCK_DATA:
        return list(MOCK_ITEMS.values())
    else:
        url = API_ENDPOINT + "/items"
        # Make request
        response = requests.get(url, headers={"Authorization": AUTHORIZATION_KEY})
        # Check response code
        if response.status_code == 200:
            # Create list of items
            result = list()
            for item_raw in response.json():
                result.append(Item(
                    item_raw['id'],
                    item_raw['name'],
                    item_raw['upc'],
                    item_raw['price'],
                    item_raw['quantity'],
                    item_raw['weight_avg'],
                    item_raw['weight_std'],
                    item_raw['thumb_img'],
                    item_raw['vision_class']
                ))
            return result
        else:
            # Something went wrong so print info and return empty list
            print(f"\tReceived response {response.status_code}:")
            print(f"\t{response.content}")
            return list()


def get_item(item_id: int) -> Item | None:
    """
    Get an item from its ID
    :return: An Item or None if the item does not exist
    """
    print(f"GET /items/{item_id}")
    if USE_MOCK_DATA:
        if item_id in MOCK_ITEMS:
            return MOCK_ITEMS[item_id]
        else:
            return None
    else:
        url = API_ENDPOINT + f"/items/{item_id}"
        # Make request
        response = requests.get(url, headers=REQUEST_HEADERS)
        # Check response code
        if response.status_code == 200:
            item = response.json()
            return Item(
                item['id'],
                item['name'],
                item['upc'],
                item['price'],
                item['units'],
                item['avg_weight'],
                item['std_weight'],
                item['thumbnail'],
                item['vision_class']
            )
        else:
            # Something went wrong so print info and return None
            print(f"\tReceived response {response.status_code}:")
            print(f"\t{response.content}")
            return None


def get_user(user_id=None, nfc_id=None) -> User | None:
    """
    Get user from either the user id or token
    :param user_id: Optional User ID
    :param user_token: Optional User Token
    :return: A User or None if the User does not exist or no identifier (ID or
    token) was provided
    """
    if USE_MOCK_DATA:
        # Check if nfc id should be used
        if nfc_id is not None:
            # Get user from nfc id
            print(f"GET /nfc/{nfc_id}")
            for nfc in MOCK_NFC:
                if MOCK_USERS.get(nfc) != None:
                    return MOCK_USERS[nfc]
            return None
        # Check if user id should be used
        elif user_id is not None:
            # Get user from ID
            print(f"GET /users/{user_id}")
            if user_id in MOCK_USERS:
                return MOCK_USERS[user_id]
            else:
                return None
        # Can't use token or ID so return None
        else:
            return None
    else:
        # Determine whether URL should query based on nfc ID or user ID
        url = ""
        if nfc_id is not None:
            # Query based on nfc id
            print(f"GET /nfc/{nfc_id}")
            url = API_ENDPOINT + f"/nfc/{nfc_id}"
        elif user_id is not None:
            # Query based on user id
            print(f"GET /users/{user_id}")
            url = API_ENDPOINT + f"/users/{user_id}"
        else:
            # Neither so return None
            return None

        # Make query determined above
        response = requests.get(url, headers=REQUEST_HEADERS)
        # Check response code
        if response.status_code == 200:
            if nfc_id is not None:
                UID = response.json()['assigned_user']
                print(f"GET /users/{UID}")
                url = API_ENDPOINT + f"/users/{UID}"
                response = requests.get(url, headers=REQUEST_HEADERS)
                user = response.json()
                return User(
                    user['id'],
                    user['name'],
                    user['thumb_img'],
                    user['balance'],
                    user['email'],
                    user['phone']
                )
                    
            if user_id is not None:
                user = response.json()
                return User(
                    user['id'],
                    user['name'],
                    user['thumb_img'],
                    user['balance'],
                    user['email'],
                    user['phone']
                )
        else:
            # Something went wrong so print info and return None
            print(f"\tReceived response {response.status_code}")
            print(f"\t{response.content}")
            return None


def update_user(user: User) -> User | None:
    """
    Update a User
    :param user: Updated User
    :return: The new User if the update was successful, otherwise None
    """
    print(f"PUT /users/{user.uid}")
    if USE_MOCK_DATA:
        if user.uid in MOCK_USERS:
            MOCK_USERS[user.uid] = user
            return user
        else:
            return None
    else:
        url = API_ENDPOINT + f"/users/{user.uid}"
        params = {
            'id': user.uid,
            'name': user.name,
            'thumb_img': user.thumb_img,
            'balance': user.balance,
            'email': user.email,
            'phone': user.phone
        }
        response = requests.put(url, params=params, headers=REQUEST_HEADERS)
        if response == 200:
            return user
        else:
            print(f"\tReceived response {response.status_code}")
            print(f"\t{response.content}")
            return None
