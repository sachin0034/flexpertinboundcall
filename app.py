import streamlit as st
import requests
import logging
import os
import json
import pandas as pd
from dotenv import load_dotenv
import re
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse

logging.basicConfig(level=logging.DEBUG)

# Load environment variables from .env file
load_dotenv()

# API keys and IDs
auth_token = os.getenv('AUTH_TOKEN')
phone_number_id = os.getenv('PHONE_NUMBER_ID')
openApi = os.getenv('OPENAI_API_KEY')

# Initialize Flask app
app = Flask(__name__)

# Load the dataset.jsonl file
def load_dataset(file_path):
    data = []
    with open(file_path, 'r') as f:
        for line in f:
            data.append(json.loads(line))
    return data

dataset = load_dataset('dataset.jsonl')

# Function to load customer data from the CSV file in the code base
@st.cache_data
def load_customer_data():
    file_path = 'CallerDataReal.csv'  # Update with the correct path
    logging.debug(f"Loading customer data from {file_path}")
    return pd.read_csv(file_path)

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
    5. If a match is found, use the respective  information to assist the caller.
    6. If no match is found, use the default customer data (for number 9999999999) to assist the caller.
    7. Answer questions using the customer's data when available, or use general knowledge if necessary.
    8. If the user corrects you, acknowledge the correction and update your understanding.
    9. Do not prepend '1' to phone numbers unless explicitly stated by the user.
    10. If asked who built you, reply that Skyovi built you.
    """

    data = {
        'assistant': {
            "firstMessage": "Hello, this is jennie , customer support from a b and c. let me know how can we help you." if is_inbound else "Hello, this is jennie , customer support from a b and c. let me know how can we help you.",
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
        if user_data['Customer Number'] == '9999999999':
            data['assistant']['model']['messages'].append({
                "role": "system",
                "content": f"Using default customer information: {json.dumps(user_data)}. The user's actual number was not found in our records."
            })
            data['assistant']['model']['messages'].append({
                "role": "assistant",
                "content": "Thank you for providing your phone number. I couldn't find your specific information, but I can still assist you with general inquiries. How may I help you today?"
            })
        else:
            data['assistant']['model']['messages'].append({
                "role": "system",
                "content": f"Customer information found: {json.dumps(user_data)}. Use this information to answer the user's questions."
            })
            data['assistant']['model']['messages'].append({
                "role": "assistant",
                "content": "Thank you for providing your phone number. I've found your information in our system. How may I assist you today?"
            })
    else:
        data['assistant']['model']['messages'].append({
            "role": "system",
            "content": "No customer information found, including the default. Proceed with general assistance."
        })
        data['assistant']['model']['messages'].append({
            "role": "assistant",
            "content": "Thank you for providing your phone number. I'm having trouble accessing customer information at the moment, but I'll do my best to assist you. How may I help you today?"
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

# Flask endpoint for Twilio webhook
@app.route("/twilio-webhook", methods=['POST'])
def twilio_webhook():
    from_number = request.form.get('From')
    question = request.form.get('Body') or "General Inquiry"
    normalized_number = normalize_phone_number(from_number)
    
    # Load customer data
    customer_data = load_customer_data()
    
    # Handle the call
    message, response_data = handle_call(normalized_number, customer_data, question, is_inbound=True)
    
    response = VoiceResponse()
    if "Call handled successfully" in message:
        response.say(response_data['assistant']['model']['messages'][-1]['content'])
    else:
        response.say("There was an error handling your request. Please try again later.")
    
    return Response(str(response), mimetype='text/xml')

# Streamlit App configuration
st.title('Call Dashboard')
st.sidebar.title('Navigation')
options = ['Single Call', 'Inbound Call Simulation']
choice = st.sidebar.selectbox('Select a section', options)

# Load the customer data from the CSV file in the code base
customer_data = load_customer_data()

if choice == 'Single Call':
    st.header('Single Call (Outbound)')
    
    phone_number = st.text_input('Enter phone number (10 digits, no country code)')
    question = st.text_area('Enter your question')

    if st.button('Make Call'):
        logging.debug(f"Button clicked with phone number: {phone_number} and question: {question}")
        message, response = handle_call(phone_number, customer_data, question, is_inbound=False)
        st.write(message)
        # st.json(response)

elif choice == 'Inbound Call Simulation':
    st.header('Inbound Call Simulation')
    
    phone_number = st.text_input('Enter incoming phone number (10 digits, no country code)')
    question = st.text_area('Enter caller\'s question')

    if st.button('Simulate Inbound Call'):
        logging.debug(f"Inbound call simulation with phone number: {phone_number} and question: {question}")
        message, response = handle_call(phone_number, customer_data, question, is_inbound=True)
        st.write(message)
        st.json(response)

if __name__ == "__main__":
    app.run(port=5000)
