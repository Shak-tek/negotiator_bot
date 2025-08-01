from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import random
import logging
import re
import json  # Import json module for parsing JSON responses

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Store conversation history and attempts
conversation_history = [] 
negotiation_attempts = 0  
negotiation_closed = False  # Track if the negotiation has ended
LAST_NEGOTIATED_PRICE = 1500  

MODEL = "llama3.2"

# Constants
MAX_ATTEMPTS = 5  
MIN_PRICE = 1200 
ACTUAL_PRICE = 1500
CURRENCY = "£"
COMPANY_NAME = "Elite Wheels"
OLLAMA_API_URL = 'http://localhost:11434/api/chat'  # Adjust if necessary

def get_ollama_response(user_message):
    global negotiation_attempts, LAST_NEGOTIATED_PRICE, negotiation_closed, conversation_history

    if negotiation_closed:
        return {
            'response': "The negotiation has ended. No more offers can be made.",
            'last_negotiated_price': LAST_NEGOTIATED_PRICE,
            'show_buttons': False
        }

    logging.info(f"last negotiated price: {LAST_NEGOTIATED_PRICE}")
    conversation_history.append({"role": "user", "content": user_message})
    user_offer = extract_price_from_message(user_message, 'user')

    # Classify user's intent before generating assistant's response
    user_intent = classify_user_intent(user_message)
    logging.info(f"User intent: {user_intent}")

    # Handle user's acceptance or rejection before calling the assistant's response
    if user_intent == "acceptance":
        negotiation_closed = True
        bot_message = finalize_negotiation(LAST_NEGOTIATED_PRICE, close_offer=True)
        logging.info(f"Finalized negotiation with price: {LAST_NEGOTIATED_PRICE}")
        return {
            'response': generate_natural_response(bot_message),
            'last_negotiated_price': LAST_NEGOTIATED_PRICE,
            'show_buttons': False
        }
    elif user_intent == "rejection":
        negotiation_closed = True
        bot_message = "Sorry that we couldn't reach an agreement. Better luck next time!"
        return {
            'response': generate_natural_response(bot_message),
            'last_negotiated_price': LAST_NEGOTIATED_PRICE,
            'show_buttons': False
        }

    negotiator_price = LAST_NEGOTIATED_PRICE if LAST_NEGOTIATED_PRICE is not None else ACTUAL_PRICE

    # Check if the user's offer is acceptable
    if user_offer is not None and negotiator_price is not None:
        if abs(user_offer - negotiator_price) <= (0.02 * negotiator_price):
            LAST_NEGOTIATED_PRICE = user_offer
            negotiation_closed = True
            bot_message = finalize_negotiation(LAST_NEGOTIATED_PRICE, close_offer=True)
            logging.info(f"User's offer accepted: {LAST_NEGOTIATED_PRICE}")
            return {
                'response': generate_natural_response(bot_message),
                'last_negotiated_price': LAST_NEGOTIATED_PRICE,
                'show_buttons': False
            }

    if negotiation_attempts >= MAX_ATTEMPTS:
        negotiation_closed = True  # Close the negotiation
        bot_message = generate_natural_response(
            f"We've reached the maximum negotiation attempts. Our final price is {negotiator_price} {CURRENCY}."
        )
        return {
            'response': bot_message,
            'last_negotiated_price': negotiator_price,
            'show_buttons': True
        }

    # Proceed to generate assistant's response
    try:
        payload = {
            "model": MODEL,
            "stream": False,
            "messages": conversation_history
        }
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        bot_response = response.json()

        bot_message = bot_response['message']['content'].strip()
        logging.info(f"Bot's message: {bot_message}")
        logging.info(f"Bot's response: {bot_response}")
        bot_price = extract_price_from_message(bot_message, 'assistant')
        logging.info(f"Price extracted from bot response: {bot_price}")

        conversation_history.append({"role": "assistant", "content": bot_message})

        # Classify assistant's intent
        assistant_intent = classify_assistant_intent(bot_message)
        logging.info(f"Assistant intent: {assistant_intent}")

        # Update LAST_NEGOTIATED_PRICE if bot provided a new price
        if bot_price is not None:
            LAST_NEGOTIATED_PRICE = bot_price
            logging.info(f"Updated LAST_NEGOTIATED_PRICE to {LAST_NEGOTIATED_PRICE}")
            
        if user_offer is not None:
            if abs(user_offer - negotiator_price) <= (0.02 * negotiator_price):
                LAST_NEGOTIATED_PRICE = user_offer
                negotiation_closed = True
                bot_message = finalize_negotiation(LAST_NEGOTIATED_PRICE, close_offer=True)
                logging.info(f"User's offer accepted: {LAST_NEGOTIATED_PRICE}")
                return {
                    'response': generate_natural_response(bot_message),
                    'last_negotiated_price': LAST_NEGOTIATED_PRICE,
                    'show_buttons': False
                }

        # Handle assistant's acceptance
        if assistant_intent == "acceptance":
            negotiation_closed = True
            bot_message = finalize_negotiation(LAST_NEGOTIATED_PRICE, close_offer=True)
            logging.info(f"Finalized negotiation with price: {LAST_NEGOTIATED_PRICE}")
            return {
                'response': generate_natural_response(bot_message),
                'last_negotiated_price': LAST_NEGOTIATED_PRICE,
                'show_buttons': False
            }

        negotiation_attempts += 1
        return {
            'response': bot_message,
            'last_negotiated_price': LAST_NEGOTIATED_PRICE,
            'show_buttons': False
        }
    except Exception as e:
        logging.error(f"Error connecting to Ollama API: {e}")
        return {
            'response': "Sorry, something went wrong!",
            'last_negotiated_price': LAST_NEGOTIATED_PRICE,
            'show_buttons': False
        }

def extract_price_from_message(message, speaker):
    """
    Extract the most relevant price from the message using the Ollama API.
    """
    logging.info(f"Extracting price from message from {speaker}: {message}")

    if speaker == 'user':
        system_prompt = (
            "You are an assistant that extracts the latest price offered or suggested by the user in a negotiation message. "
            "Given the user's message, identify the latest price offered or suggested by the user. "
            "Respond with only the numerical value of that price. "
            "Do not include any additional text, currency symbols, or other numbers. If there is no price mentioned, respond with 'No price found'."
        )
    elif speaker == 'assistant':
        system_prompt = (
            "You are an assistant that extracts the latest price offered or suggested by the assistant in a negotiation message. "
            "Given the assistant's message, identify the latest price offered or suggested by the assistant. "
            "Respond with only the numerical value of that price. "
            "Do not include any additional text, currency symbols, or other numbers. If there is no price mentioned, respond with 'No price found'."
        )
    else:
        logging.error("Invalid speaker specified.")
        return None

    payload = {
        "model": MODEL,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {"role": "user", "content": message}
        ]
    }

    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        response_data = response.json()
        logging.info(f"Ollama API response in extract_price_from_message: {response_data}")

        extracted_text = response_data.get('message', {}).get('content', '').strip()
        logging.info(f"Extracted text: {extracted_text}")

        # Check if the assistant indicates no price was found
        if 'no price found' in extracted_text.lower():
            logging.info("No price found in the message.")
            return None

        # Remove any non-numeric characters
        extracted_text = extracted_text.replace(',', '').strip()

        # Attempt to convert the extracted text to a float
        try:
            price = float(extracted_text)
            logging.info(f"Extracted price: {price}")
            return price
        except ValueError:
            # If multiple numbers are present, extract them and choose the most relevant one
            numbers = re.findall(r'\d+(?:\.\d+)?', extracted_text)
            logging.info(f"Numbers found in extracted text: {numbers}")
            if numbers:
                # Assuming the last number is the most relevant price
                price = float(numbers[-1])
                logging.info(f"Selected price: {price}")
                return price
            else:
                logging.error("No valid numbers found in the extracted text.")
                return None

    except Exception as e:
        logging.error(f"Error extracting price using Ollama API: {e}", exc_info=True)
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

def classify_user_intent(user_message):
    """
    Classify the user's intent based on their latest message.
    """
    logging.info(f"Classifying user intent based on user message.")

    conversation = [
        {
            "role": "system",
            "content": (
                "You are an assistant that classifies the user's intent in a price negotiation. "
                "Given the user's latest message, classify the intent as 'acceptance', 'rejection', or 'negotiation'. "
                "Only respond with the intent.\n\n"
                "Guidelines:\n"
                "- If the user agrees to the price or says phrases like 'Yes', 'sure', 'Deal', classify as 'acceptance'.\n"
                "- If the user declines or says phrases like 'No', 'Not interested', 'I don't think so', classify as 'rejection'.\n"
                "- If the user makes a counteroffer (gives a price) or continues negotiating, classify as 'negotiation'.\n"
                "- If the intent is unclear, classify as 'unknown'."
            )
        },
        {"role": "user", "content": user_message}
    ]

    payload = {
        "model": MODEL,
        "stream": False,
        "messages": conversation
    }

    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        bot_response = response.json()

        # Extract the intent from the response
        response_content = bot_response.get('message', {}).get('content', '').strip().lower()
        logging.info(f'User intent is {response_content}')
        # Map the response to predefined intents
        if "acceptance" in response_content:
            return "acceptance"
        elif "rejection" in response_content:
            return "rejection"
        elif "negotiation" in response_content:
            return "negotiation"
        else:
            return "unknown"
    except Exception as e:
        logging.error(f"Error classifying user intent with Ollama API: {e}")
        return "unknown"

def classify_assistant_intent(bot_message):
    """
    Classify the assistant's intent based on their latest message.
    """
    logging.info(f"Classifying assistant intent based on assistant message.")

    conversation = [
        {
            "role": "system",
            "content": (
                "You are an assistant that classifies the assistant's intent in a price negotiation. "
                "Given the assistant's latest message, classify the intent as 'acceptance', 'rejection', or 'negotiation'. "
                "Only respond with the intent.\n\n"
                "Guidelines:\n"
                "- If the assistant accepts the user's offer or says phrases like 'Deal', 'Agreed', 'ok', 'alright', 'We have a deal', classify as 'acceptance'.\n"
                "- If the assistant declines the negotiation or says phrases like 'We cannot offer a better price', 'Sorry, that's our final offer', classify as 'rejection'.\n"
                "- If the assistant makes a counteroffer, suggests a new price, continues negotiating, or asks the user what it thinks then classify as 'negotiation'.\n"
                "- If the intent is unclear, classify as 'unknown'."
            )
        },
        {"role": "user", "content": bot_message}
    ]

    payload = {
        "model": MODEL,
        "stream": False,
        "messages": conversation
    }

    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        bot_response = response.json()

        # Extract the intent from the response
        response_content = bot_response.get('message', {}).get('content', '').strip().lower()
        logging.info(f'Assistant intent is {response_content}')
        # Map the response to predefined intents
        if "acceptance" in response_content:
            return "acceptance"
        elif "rejection" in response_content:
            return "rejection"
        elif "negotiation" in response_content:
            return "negotiation"
        else:
            return "unknown"
    except Exception as e:
        logging.error(f"Error classifying assistant intent with Ollama API: {e}")
        return "unknown"

def initialize_ollama_response(user_message):
    global negotiation_attempts, LAST_NEGOTIATED_PRICE, negotiation_closed
    conversation_history.clear()
    negotiation_attempts = 0
    negotiation_closed = False  # Reset negotiation closed flag
    first_discounted_price = generate_random_discount(ACTUAL_PRICE)
    LAST_NEGOTIATED_PRICE = first_discounted_price  # **Set LAST_NEGOTIATED_PRICE to assistant's first offer**
    conversation_history.append({
        "role": "system",
        "content": (
            f"You are a friendly and suave British price negotiator working for {COMPANY_NAME}. "
            f"You are selling a set of 4 wheels for {ACTUAL_PRICE} {CURRENCY}. "
            f"Start by always offering a price of {first_discounted_price} {CURRENCY} first. "
            f"You should negotiate down to no less than {MIN_PRICE} {CURRENCY} after multiple attempts. "
            f"If the user's offer is less than 50% of {ACTUAL_PRICE} {CURRENCY} tell them that we won't have a deal with this kind of offer so please try to do better. "
            "The user can offer up to 5 times. If the user's offer is within 10% of your price, immediately accept. "
            "Go a bit lower the next time you offer a price. Don't mention the price that the user offered. "
            "Never go below the price that the user offered. "
            "Always offer the price in the format '£<price>' or '<price> GBP' and don't mention the discount amount. "
            "If the user accepts your price, just accept it."
        )
    })
    return get_ollama_response(user_message)
 
def generate_random_code():
    """Generates a random 6-digit discount code."""
    return ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))

def reset_conversation():
    """Reset the conversation history and negotiation attempts after a conversation ends."""
    global conversation_history, negotiation_attempts, LAST_NEGOTIATED_PRICE
    conversation_history.clear()
    negotiation_attempts = 0
    LAST_NEGOTIATED_PRICE = None  # **Reset LAST_NEGOTIATED_PRICE to None**

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
    return round(discounted_price, 2)  # **Ensure the price is rounded to two decimal places**
  
def generate_natural_response(prompt):
    """
    Send a prompt to the Ollama API and return a natural-sounding response.
    """
    payload = {
        "model": MODEL,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": f"Output the following sentence as something a human would say without adding sentences that might change the meaning: {prompt}"
            }
        ]
    }
    
    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()  # Raise an error for bad responses

        # Extract the content from the response
        response_data = response.json()
        natural_response = response_data.get('message', {}).get('content', '').strip()
        logging.info(f"Ollama API response in generate_natural_response: {response_data}")
        return natural_response

    except requests.exceptions.RequestException as e:
        logging.error(f"Error connecting to Ollama API: {e}")
        return "Sorry, I couldn't process your request."

if __name__ == '__main__':
    app.run(debug=True)
