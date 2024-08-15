from dotenv import load_dotenv
import pandas as pd
import requests
import requests
import numpy as np
import re
import os

# Load environment variables from .env file
load_dotenv()

# Access the environment variables
miro_access_token = os.getenv("MIRO_ACCESS_TOKEN")
miro_board_id =    os.getenv("MIRO_BOARD_ID")

headers = {
    "Authorization": f"Bearer {miro_access_token}",
    "Content-Type": "application/json",
}

# Define the Miro API base URL
BASE_URL = "https://api.miro.com/v2"


# Function to get items from the board using cursor pagination and save to a DataFrame
def get_items(board_id, limit=50):
    """
    Retrieves items from a Miro board using cursor pagination and saves them into a pandas DataFrame.

    Args:
        board_id (str): The ID of the Miro board to retrieve items from.
        limit (int, optional): The maximum number of results per request. Defaults to 50.

    Returns:
        pandas.DataFrame: A DataFrame containing the retrieved items. Each row represents an item and the columns
        are: 'id', 'type', 'content', 'shape', 'fillColor', 'width', 'height', 'x', 'y', 'createdAt', 'modifiedAt',
        'createdBy', 'modifiedBy'.
    """
    items = []
    url = f"{BASE_URL}/boards/{board_id}/items"

    params = {
        "limit": limit,  # Set the maximum number of results per request
    }

    while True:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        if "data" not in data:
            raise ValueError("No data found in the response")

        items.extend(data["data"])

        if cursor := data.get("cursor"):
            # Update the params to include the cursor for the next request
            params["cursor"] = cursor

        else:
            break

    # Process the items to save them into a DataFrame
    item_list = []
    for item in items:
        item_data = {
            "id": item.get("id"),
            "type": item.get("type"),
            "content": item.get("data", {}).get("content", ""),
            "shape": item.get("data", {}).get("shape", ""),
            "fillColor": item.get("style", {}).get("fillColor", ""),
            "width": item.get("geometry", {}).get("width"),
            "height": item.get("geometry", {}).get("height"),
            "x": item.get("position", {}).get("x"),
            "y": item.get("position", {}).get("y"),
            "createdAt": item.get("createdAt"),
            "modifiedAt": item.get("modifiedAt"),
            "createdBy": item.get("createdBy", {}).get("id"),
            "modifiedBy": item.get("modifiedBy", {}).get("id"),
        }
        item_list.append(item_data)

    return pd.DataFrame(item_list)


def create_miro_element(
    element_type="card",
    board_id=miro_board_id,
    title="Titel",
    description=None,
    fillColor="red",
    shape="rectangle",
    width=300,
    height=300,
    x=0,
    y=0,
):
    """
    Creates a new Miro element (card, sticky note, or shape) at a specified position on a board.

    Parameters:
        element_type (str): The type of element to create (card, sticky_note, or shape).
        board_id (str): The ID of the board where the element will be created.
        title (str): The title of the element.
        description (str): The description of the element (only applicable for cards).
        fillColor (str): The fill color of the element.
        shape (str): The shape of the element (only applicable for shapes).
        width (int): The width of the element.
        height (int): The height of the element.
        x (int): The x-coordinate of the element's position.
        y (int): The y-coordinate of the element's position.

    Returns:
        Optional[Dict[str, object]]: The JSON response from the API if the request was successful, None otherwise.
    """

    if element_type == "card":
        height = adjust_card_height(title, height)
    width = max(width, 256)
    existing_items = get_items(board_id)
    if not existing_items.empty:
        x, y = find_free_position(x, y, width, height, existing_items)

    url, payload = build_payload(
        element_type,
        board_id,
        title,
        description,
        fillColor,
        shape,
        width,
        height,
        x,
        y,
    )
    return send_request(url, payload, element_type, x, y) if url else None


def adjust_card_height(title, height):
    """
    Adjusts the card height based on the title length and line breaks.

    Args:
        title (str): The title of the card.
        height (int): The initial height of the card.

    Returns:
        int: The adjusted height of the card.
    """

    title_length = len(title.replace("<br>", ""))
    extra_height = ((title_length - 1) // 13) * 25 if title_length > 13 else 0
    line_breaks_height = title.count("<br>") * 20
    return height + extra_height + line_breaks_height


def find_free_position(
    x,
    y,
    width,
    height,
    existing_items,
    initial_step=50,
    max_attempts=10000,
    increase_step_interval=100,
):
    """
    Finds a free position for an element on a board using a spiral search algorithm.

    Parameters:
        x (int): The initial x-coordinate of the element.
        y (int): The initial y-coordinate of the element.
        width (int): The width of the element.
        height (int): The height of the element.
        existing_items (list): A list of existing items on the board.
        initial_step (int, optional): The initial step size for the spiral search. Defaults to 50.
        max_attempts (int, optional): The maximum number of attempts to find a free position. Defaults to 10000.
        increase_step_interval (int, optional): The interval at which to increase the step size. Defaults to 100.

    Returns:
        tuple: A tuple containing the x and y coordinates of the free position.
    """

    step = initial_step
    attempts = 0
    directions = [(step, 0), (0, step), (-step, 0), (0, -step)]
    direction_index = 0
    steps_in_current_leg = 1
    steps_taken = 0
    leg_increase_triggered = False

    while is_collision(x, y, width, height, existing_items) and attempts < max_attempts:
        dx, dy = directions[direction_index]
        x += dx
        y += dy
        steps_taken += 1
        attempts += 1
        if attempts % increase_step_interval == 0:
            step += initial_step
            directions = [(step, 0), (0, step), (-step, 0), (0, -step)]

        if steps_taken == steps_in_current_leg:
            direction_index = (direction_index + 1) % 4
            steps_taken = 0
            if leg_increase_triggered:
                steps_in_current_leg += 1
            leg_increase_triggered = not leg_increase_triggered

    if attempts == max_attempts:
        print("Unable to find a free spot for the new item.")

    return x, y


def build_payload(
    element_type, board_id, title, description, fillColor, shape, width, height, x, y
):
    """
    Builds the URL and payload based on the element type.

    Parameters:
        element_type (str): The type of element to create (card, sticky_note, or shape).
        board_id (str): The ID of the board where the element will be created.
        title (str): The title of the element.
        description (str): The description of the element (only applicable for cards).
        fillColor (str): The fill color of the element.
        shape (str): The shape of the element (only applicable for shapes).
        width (int): The width of the element.
        height (int): The height of the element.
        x (int): The x-coordinate of the element's position.
        y (int): The y-coordinate of the element's position.

    Returns:
        tuple: A tuple containing the URL and payload for the API request.
    """

    if element_type == "card":
        fillColor = validate_hex_color(fillColor)
        url = f"https://api.miro.com/v2/boards/{board_id}/cards"
        payload = {
            "data": {"title": title, "description": description},
            "style": {"cardTheme": fillColor},
            "position": {"x": x, "y": y},
            "geometry": {"height": height, "width": width, "rotation": 0},
        }
    elif element_type == "sticky_note":
        fillColor = validate_sticky_note_color(fillColor)
        url = f"https://api.miro.com/v2/boards/{board_id}/sticky_notes"
        payload = {
            "data": {"content": title},
            "style": {"fillColor": fillColor},
            "position": {"x": x, "y": y},
            "geometry": {"height": height},
        }
    elif element_type == "shape":
        fillColor = validate_hex_color(fillColor)
        url = f"https://api.miro.com/v2/boards/{board_id}/shapes"
        payload = {
            "data": {"content": title, "shape": shape},
            "style": {
                "borderColor": "#000000",
                "borderOpacity": "1.0",
                "borderStyle": "normal",
                "borderWidth": "2",
                "color": "#1a1a1a",
                "fillColor": fillColor,
                "fillOpacity": "1.0",
                "fontFamily": "arial",
                "fontSize": "14",
                "textAlign": "left",
                "textAlignVertical": "top",
            },
            "position": {"x": x, "y": y},
            "geometry": {"height": height, "width": width, "rotation": 0},
        }
    else:
        print("Invalid element type. Please choose 'card', 'sticky_note', or 'shape'.")
        return None, None

    return url, payload


def validate_sticky_note_color(fillColor):
    """
    Validates the color for sticky notes.

    Args:
        fillColor (str): The color to be validated.

    Returns:
        str: The validated color. If the input color is not in the allowed colors list, it defaults to 'yellow'.
    """
    allowed_colors = [
        "gray",
        "light_yellow",
        "yellow",
        "orange",
        "light_green",
        "green",
        "dark_green",
        "cyan",
        "light_pink",
        "pink",
        "violet",
        "red",
        "light_blue",
        "blue",
        "dark_blue",
        "black",
    ]
    if fillColor not in allowed_colors:
        print(f"Invalid color '{fillColor}' for sticky notes. Defaulting to 'yellow'.")
        return "yellow"
    return fillColor


def validate_hex_color(color: str) -> str:
    """
    Validates a given color string as a hexadecimal color code.
    
    Args:
        color (str): The color string to be validated.
    
    Returns:
        str: The validated hexadecimal color code. If the input color is invalid, returns "#00C1D4" as default.
    """

    hex_pattern = re.compile(r"^#?([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$")
    if not hex_pattern.match(color):
        return "#00C1D4"
    if not color.startswith("#"):
        color = f"#{color}"
    return color


from typing import Optional, Dict

def send_request(url, payload, element_type, x, y):
    """Sends the API request to create the Miro element.

    Args:
        url (str): The API endpoint URL.
        payload (Dict[str, object]): The JSON payload for the request.
        element_type (str): The type of the element being created (e.g. "card", "sticky_note", "shape").
        x (float): The x-coordinate of the element's center.
        y (float): The y-coordinate of the element's center.

    Returns:
        Optional[Dict[str, object]]: The JSON response from the API if the request was successful, None otherwise.
    """
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 201:
        print(
            f"{element_type.capitalize()} created successfully at position ({x}, {y})!"
        )
        return response.json()
    else:
        print(f"Failed to create {element_type}: {response.status_code}")
        print(response.text)
        return None


def is_collision(new_x, new_y, new_width, new_height, existing_items):
    """
    Checks if a new item will collide with existing items, considering a 10% clear area around the new item.

    Parameters:
        new_x (float): The x-coordinate of the new item's center.
        new_y (float): The y-coordinate of the new item's center.
        new_width (float): The width of the new item.
        new_height (float): The height of the new item.
        existing_items (dict): A dictionary containing the existing items' coordinates and dimensions.

    Returns:
        bool: True if a collision is detected, False otherwise.
    """

    # Calculate the clear area (10% of width and height)
    clear_x = new_width * 0.1
    clear_y = new_height * 0.1

    # Convert the center coordinates to top-left coordinates and expand the new shape by 10%
    expanded_new_x = new_x - new_width / 2 - clear_x
    expanded_new_y = new_y - new_height / 2 - clear_y
    expanded_new_width = new_width + 2 * clear_x
    expanded_new_height = new_height + 2 * clear_y

    # Convert existing items to NumPy arrays for efficient vectorized operations
    existing_x = existing_items["x"].values
    existing_y = existing_items["y"].values
    existing_width = existing_items["width"].values
    existing_height = existing_items["height"].values

    # Calculate existing items' top-left coordinates
    existing_top_left_x = existing_x - existing_width / 2
    existing_top_left_y = existing_y - existing_height / 2

    # Check for collisions using vectorized comparisons
    collision_x = (expanded_new_x + expanded_new_width >= existing_top_left_x) & (
        expanded_new_x <= existing_top_left_x + existing_width
    )
    collision_y = (expanded_new_y + expanded_new_height >= existing_top_left_y) & (
        expanded_new_y <= existing_top_left_y + existing_height
    )

    return np.any(collision_x & collision_y)
