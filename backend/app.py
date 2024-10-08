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
        bot_message = "Sorry that we couldn't reach an agreement. Better luck next time!"
        return {
            'response': bot_message,
            'last_negotiated_price': LAST_NEGOTIATED_PRICE,
            'show_buttons': False
        }

    negotiator_price = LAST_NEGOTIATED_PRICE if LAST_NEGOTIATED_PRICE is not None else ACTUAL_PRICE

    if user_offer is not None and negotiator_price is not None:
        if abs(user_offer - negotiator_price) <= (0.02 * negotiator_price):
            return {
                'response': f"Congratulations! Your offer of {user_offer} {CURRENCY} is very close to our price of {negotiator_price} {CURRENCY}.",
                'last_negotiated_price': negotiator_price,
                'show_buttons': True
            }

    # Check if negotiation attempts have exceeded MAX_ATTEMPTS
    if negotiation_attempts >= MAX_ATTEMPTS:
        return {
            'response': f"We've reached the maximum negotiation attempts. Our final price is {negotiator_price} {CURRENCY}.",
            'last_negotiated_price': negotiator_price,
            'show_buttons': True
        }

    # Otherwise, continue with normal negotiation
    try:
        # Call Ollama API
        payload = {
            "model": "llama3.2",  # Ensure this is the correct model
            "stream": False,
            "messages": conversation_history
        }
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        bot_response = response.json()
        bot_message = bot_response['message'].strip()

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
    return bot_message

def classify_intent(user_message=None, bot_message=None):
    """
    Classify the intent based on user and bot messages.
    """
    # Simple classification logic
    if "accept" in user_message.lower():
        return "acceptance"
    elif "no" in user_message.lower() or "reject" in user_message.lower():
        return "rejection"
    return "negotiation"

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
    bot_response = get_ollama_response(user_message)  # Adjust to initialize with Ollama
    return jsonify(bot_response)

if __name__ == '__main__':
    app.run(debug=True)
