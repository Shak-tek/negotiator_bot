from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import random
import logging
import re

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Store conversation history and attempts
conversation_history = [] 
negotiation_attempts = 0  
LAST_NEGOTIATED_PRICE = 1500  

MODEL= "llama3.2"

# Constants
MAX_ATTEMPTS = 5  
MIN_PRICE = 1200 
ACTUAL_PRICE = 1500
CURRENCY = "GBP"
OLLAMA_API_URL = 'http://localhost:11434/api/chat'  # Adjust if necessary

def get_ollama_response(user_message):
    global negotiation_attempts, LAST_NEGOTIATED_PRICE
    
    logging.info(f"last negotiated price: {LAST_NEGOTIATED_PRICE}")
    conversation_history.append({"role": "user", "content": user_message})
    user_offer = extract_price_from_message(user_message)

    if user_message == "Deal!":
        bot_message = finalize_negotiation(LAST_NEGOTIATED_PRICE, close_offer=True)
        return {
            'response': bot_message,
            'last_negotiated_price': LAST_NEGOTIATED_PRICE,
            'show_buttons': False
        }
    elif user_message == "No Deal!":
        bot_message = generate_natural_response("Sorry that we couldn't reach an agreement. Better luck next time!")
        return {
            'response': bot_message,
            'last_negotiated_price': LAST_NEGOTIATED_PRICE,
            'show_buttons': False
        }

    negotiator_price = LAST_NEGOTIATED_PRICE if LAST_NEGOTIATED_PRICE is not None else ACTUAL_PRICE

    if user_offer is not None and negotiator_price is not None:
        if abs(user_offer - negotiator_price) <= (0.02 * negotiator_price):
            return {
                'response': generate_natural_response(f"Congratulations! Your offer of {user_offer} {CURRENCY} is very close to our price of {negotiator_price} {CURRENCY}."),
                'last_negotiated_price': negotiator_price,
                'show_buttons': True
            }

    # Check if negotiation attempts have exceeded MAX_ATTEMPTS
    if negotiation_attempts >= MAX_ATTEMPTS:
        return {
            'response': generate_natural_response(f"We've reached the maximum negotiation attempts. Our final price is {negotiator_price} {CURRENCY}."),
            'last_negotiated_price': negotiator_price,
            'show_buttons': True
        }

    # Otherwise, continue with normal negotiation
    try:
        # Call Ollama API
        payload = {
            "model": MODEL,  # Ensure this is the correct model
            "stream": False,
            "messages": conversation_history
        }
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        bot_response = response.json()

        bot_message = bot_response['message']['content'].strip()
        bot_price = extract_price_from_message(bot_message)
        logging.info(f"Price extracted from bot response: {bot_price}")

        if bot_price is not None:
            LAST_NEGOTIATED_PRICE = bot_price
        conversation_history.append({"role": "assistant", "content": bot_message})

        bot_intent = classify_intent(user_message, bot_message)
        logging.info(f'user_message is {user_message}')
        logging.info(f'bot_message is {bot_message}')
        logging.info(f'bot intent is {bot_intent}')

        if bot_intent == "acceptance" and negotiation_attempts > 1:
            bot_message = finalize_negotiation(LAST_NEGOTIATED_PRICE, close_offer=True)
            return {'response': bot_message, 'show_buttons': False}

        negotiation_attempts += 1
        return {'response': bot_message, 'last_negotiated_price': LAST_NEGOTIATED_PRICE, 'show_buttons': False}
    except Exception as e:
        logging.error(f"Error connecting to Ollama API: {e}")
        return {'response': "Sorry, something went wrong!", 'last_negotiated_price': LAST_NEGOTIATED_PRICE, 'show_buttons': False}


def extract_price_from_message(message):
    """Extract the lowest price preceded by '£' or followed by 'GBP' from the user's message."""
    try:
        prices = re.findall(r'(?:£\s*(\d+\.?\d*)|(\d+\.?\d*)\s*GBP)', message)
        prices = [float(price) for price_pair in prices for price in price_pair if price]
        if prices:
            return min(prices)
    except Exception as e:
        logging.error(f"Error extracting price: {e}")
    
    return None

def finalize_negotiation(last_price, close_offer=False):
    """
    Finalizes the negotiation process.
    """
    if close_offer:
        discount_code = generate_random_code()
        bot_message = f"Deal closed! We've accepted your offer of {last_price} {CURRENCY}. Here's your discount code: {discount_code}. Thank you for negotiating with us!"
    else:
        bot_message = "No deal reached. Thank you for your time!"

    reset_conversation()
    return generate_natural_response(bot_message)

def classify_intent(user_message=None, bot_message=None):
    """
    Classify the intent based on both user and bot messages using the Llama model.
    """
    # Ensure both messages are provided
    if not user_message or not bot_message:
        return "unknown"

    # Add both user and bot messages to the payload for the Llama model to classify
    conversation_history = [
        {"role": "system", "content": f"Classify the user's intent in a price negotiation. Consider both the {user_message} and the {bot_message}. Determine if the user accepts, rejects, or is still negotiate. If the {user_message} contains a counter price then it should be considered a negotiation. If the user accepts the price then it's an acceptance. Only respond with a acceptance, rejection, negotiation and unclear."},
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": bot_message}
    ]

    payload = {
        "model": MODEL,  # Replace with the correct model name
        "stream": False,
        "messages": conversation_history
    }

    try:
        # Send the classification request to the Llama API
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()

        # Parse the response from the Llama model
        bot_response = response.json()

        # Extract the intent from the bot's response
        if 'message' in bot_response and 'content' in bot_response['message']:
            classified_intent = bot_response['message']['content'].strip().lower()

            # Map the response to predefined intents
            if "acceptance" in classified_intent:
                return "acceptance"
            elif "rejection" in classified_intent:
                return "rejection"
            elif "negotiation" in classified_intent:
                return "negotiation"
            else:
                return "unknown"

    except Exception as e:
        logging.error(f"Error classifying intent with Ollama API: {e}")
        return "unknown"

def initialize_ollama_response(user_message):
    global negotiation_attempts, LAST_NEGOTIATED_PRICE
    conversation_history.clear()
    negotiation_attempts = 0
    LAST_NEGOTIATED_PRICE = ACTUAL_PRICE  # Reset negotiator's offer
    first_discounted_price = generate_random_discount(ACTUAL_PRICE)
    conversation_history.append({
        "role": "system",
        "content": f"You are a smart and suave price negotiator who doesn't get detracted from his purpose. You are selling a set of 4 wheels for {ACTUAL_PRICE} {CURRENCY}. Start by always offering a price of {first_discounted_price} first. You should negotiate down to no less than {MIN_PRICE} {CURRENCY} after multiple attempts. The user can offer up to 5 times. If the user's offer is within 10% of the user's price, immediately accept. if the offer is more than the one you offered before, ask te user if they made a typo or something. Go a bit lower the next time you offer a price. Don't mention the price that the user offered and never go below what the user offered. Always offer price in {CURRENCY} and don't mention the discount amount. If the user accepts your price just accept it. Don't fall for low ballers who offer way too low of a price at start."
    })
    logging.info(f"Ollama Initialized: {LAST_NEGOTIATED_PRICE}")

    return get_ollama_response(user_message)
    
def generate_random_code():
    """Generates a random 6-digit discount code."""
    return ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))

def reset_conversation():
    """Reset the conversation history and negotiation attempts after a conversation ends."""
    global conversation_history, negotiation_attempts, LAST_NEGOTIATED_PRICE
    conversation_history.clear()
    negotiation_attempts = 0
    LAST_NEGOTIATED_PRICE = ACTUAL_PRICE  # Reset the negotiator's offer

@app.route('/chatbot', methods=['POST'])
def chatbot_response():
    data = request.get_json()
    user_message = data['message']
    bot_response = get_ollama_response(user_message)
    return jsonify(bot_response)

@app.route('/initialize', methods=['POST'])
def chatbot_initialize():
    data = request.get_json()
    user_message = data['message']
    bot_response = initialize_ollama_response(user_message)  # Adjust to initialize with Ollama
    return jsonify(bot_response)

def generate_random_discount(original_price):
    discount_percentage = random.uniform(2, 5)
    discount = round(discount_percentage, 0)
    discounted_price = original_price * (1 - discount / 100)
    return discounted_price
  
def generate_natural_response(prompt):
    """
    Send a prompt to the Ollama API and return a natural-sounding response.
    
    Args:
        prompt (str): The input message to be transformed.

    Returns:
        str: A natural-sounding response generated by the Ollama API.
    """
    payload = {
        "model": MODEL,  # Specify the model you are using
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": f"Output the following sentence as something natural sounding: {prompt}"
            }
        ]
    }
    
    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()  # Raise an error for bad responses

        # Extract the content from the response
        response_data = response.json()
        natural_response = response_data.get('message', {}).get('content', '')

        return natural_response

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Ollama API: {e}")
        return "Sorry, I couldn't process your request."


if __name__ == '__main__':
    app.run(debug=True)
