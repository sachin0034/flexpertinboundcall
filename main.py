from flask import Flask, request, jsonify
import logging
import os
import json
import pandas as pd
from dotenv import load_dotenv
import re
import requests

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Load environment variables from .env file
load_dotenv()

# API keys and IDs
auth_token = os.getenv('AUTH_TOKEN')
phone_number_id = os.getenv('PHONE_NUMBER_ID')
openApi = os.getenv('OPENAI_API_KEY')

# Load the dataset.jsonl file
def load_dataset(file_path):
    data = []
    with open(file_path, 'r') as f:
        for line in f:
            data.append(json.loads(line))
    return data

dataset = load_dataset('dataset.jsonl')

# Load customer data
def load_customer_data():
    file_path = 'CallerDataReal.csv'  # Update with the correct path
    logging.debug(f"Loading customer data from {file_path}")
    return pd.read_csv(file_path)

customer_data = load_customer_data()

# Improved normalize phone number function
def normalize_phone_number(phone_number):
    normalized = re.sub(r'\D', '', str(phone_number))
    if normalized.startswith('91') and len(normalized) > 10:
        normalized = normalized[2:]
    if len(normalized) == 10:
        logging.debug(f"Normalized phone number: {normalized}")
        return normalized
    else:
        logging.warning(f"Invalid phone number format: {phone_number}")
        return None

# Updated function to fetch customer data by phone number
def get_customer_data_by_phone(phone_number, customer_data):
    if customer_data is not None:
        normalized_phone_number = normalize_phone_number(phone_number)
        if normalized_phone_number:
            logging.debug(f"Searching for customer data with phone number: {normalized_phone_number}")
            customer = customer_data[customer_data['Customer Number'].astype(str).apply(normalize_phone_number) == normalized_phone_number]
            if not customer.empty:
                logging.debug(f"Customer data found: {customer.iloc[0].to_dict()}")
                return customer.iloc[0].to_dict()
    
    # If no match found or invalid number, return data for 9999999999
    logging.debug("No customer data found. Returning data for 9999999999.")
    default_customer = customer_data[customer_data['Customer Number'].astype(str) == '9999999999']
    if not default_customer.empty:
        return default_customer.iloc[0].to_dict()
    else:
        logging.error("Default customer (9999999999) not found in the data.")
        return None

def search_answer(question, dataset, user_data=None):
    logging.debug(f"Searching answer for question: {question}")
    
    # Check for predefined bot response
    if "who built you" in question.lower() or "who made you" in question.lower():
        return "I was built by Skyovi."

    # Search in user data
    if user_data:
        logging.debug("Searching answer with user data")
        for key, value in user_data.items():
            if key.lower() in question.lower():
                return f"Your {key} is {value}."

    # Search in dataset
    logging.debug("Searching answer in dataset.jsonl")
    for entry in dataset:
        if entry['messages'][0]['content'].lower() in question.lower():
            return entry['messages'][1]['content']

    # If no match found
    return "I cannot provide information regarding that. Please rephrase your question or ask something else."

def handle_call(phone_number, customer_data, question, is_inbound=False):
    logging.debug(f"Handling {'inbound' if is_inbound else 'outbound'} call with phone number: {phone_number} and question: {question}")

    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Content-Type': 'application/json',
    }

    system_prompt = """
    You are the customer support at A B & C. Follow these steps:
    1. For outbound calls, ask the caller for their phone number at the start of the call.
    2. For inbound calls, use the provided phone number to retrieve customer details.
    3. Accept the phone number as provided by the user, without adding any country code.
    4. Use the provided phone number to retrieve customer details from our records.
    5. If a match is found, use the respective information to assist the caller.
    6. If no match is found, use the default customer data (for number 9999999999) to assist the caller.
    7. Answer questions using the customer's data when available, or use general knowledge if necessary.
    8. If the user corrects you, acknowledge the correction and update your understanding.
    9. Do not prepend '1' to phone numbers unless explicitly stated by the user.
    10. If asked who built you, reply that Skyovi built you.
    """

    data = {
        'assistant': {
            "firstMessage": "Hello, this is jennie, customer support from A B & C. How can we help you?" if is_inbound else "Hello, this is jennie, customer support from A B & C. How can we help you?",
            "model": {
                "provider": "openai",
                "model": "gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "assistant",
                        "content": "Hello! Welcome to AB&C customer support. How may I assist you today?" if is_inbound else "Hello! Welcome to AB&C customer support. To assist you better, could you please provide your 10-digit phone number?"
                    }
                ]
            },
            "voice": "jennifer-playht"
        },
        'phoneNumberId': phone_number_id,
        'customer': {
            'number': phone_number,
        },
    }

    # Fetch customer data
    user_data = get_customer_data_by_phone(phone_number, customer_data)

    if user_data:
        greeting_message = f"Hello {user_data.get('Customer Name', 'Customer')}, thank you for calling. How may I assist you today?"
        if user_data['Customer Number'] == '9999999999':
            data['assistant']['model']['messages'].append({
                "role": "system",
                "content": f"Using default customer information: {json.dumps(user_data)}. The user's actual number was not found in our records."
            })
            data['assistant']['model']['messages'].append({
                "role": "assistant",
                "content": greeting_message
            })
        else:
            data['assistant']['model']['messages'].append({
                "role": "system",
                "content": f"Customer information found: {json.dumps(user_data)}. Use this information to answer the user's questions."
            })
            data['assistant']['model']['messages'].append({
                "role": "assistant",
                "content": greeting_message
            })
    else:
        data['assistant']['model']['messages'].append({
            "role": "system",
            "content": "No customer information found, including the default. Proceed with general assistance."
        })
        data['assistant']['model']['messages'].append({
            "role": "assistant",
            "content": "Thank you for calling. I'm having trouble accessing customer information at the moment, but I'll do my best to assist you. How may I help you today?"
        })

    # Add the user's question
    data['assistant']['model']['messages'].append({
        "role": "user",
        "content": question
    })

    # Search for an answer
    answer = search_answer(question, dataset, user_data)
    if answer:
        data['assistant']['model']['messages'].append({
            "role": "assistant",
            "content": answer
        })
    else:
        data['assistant']['model']['messages'].append({
            "role": "assistant",
            "content": "I cannot provide information regarding that. Please rephrase your question or ask something else."
        })

    try:
        json_data = json.dumps(data)
        logging.info(f"Request data: {json_data}")
        response = requests.post('https://api.vapi.ai/call/phone', headers=headers, data=json_data)
        response.raise_for_status()
        logging.info("Call handled successfully")
        return 'Call handled successfully.', response.json()
    except requests.RequestException as e:
        logging.error(f"Error handling call: {e.response.text}")
        return 'Failed to handle call', e.response.text

@app.route('/vapi/call-handler', methods=['POST'])
def vapi_call_handler():
    data = request.get_json()
    phone_number = data.get('From')  # Extract phone number from Twilio request
    question = data.get('Body', '')  # Extract question from Twilio request, if available
    logging.debug(f"Incoming call from {phone_number} with question: {question}")
    message, response = handle_call(phone_number, customer_data, question, is_inbound=True)
    return jsonify({'message': message, 'response': response})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
