import pandas as pd
from flask import Flask, request, jsonify
import requests
import json

app = Flask(__name__)

# Load user data from JSON
with open('callerData.json') as f:
    user_data = json.load(f)['Sheet1']
    
# Create a dictionary for easy lookup
user_data_dict = {str(user['Customer Number']): user for user in user_data}

@app.route('/twilio/inbound_call', methods=['POST'])
def inbound_call():
    incoming_number = request.json['From']
    
    # Match with user data
    user_info = user_data_dict.get(incoming_number)
    
    response_payload = {
        "assistantId": "7dd3f644-e099-43fc-bcbb-3f95642e0f81",
        "assistantOverrides": {
            "variableValues": {}
        },
        "customer": {
            "number": incoming_number
        },
        "phoneNumberId": "your-phone-id"
    }

    if user_info:
        name = user_info['FirstName']
        response_payload["assistantOverrides"]["variableValues"]["name"] = name
        response_payload["assistantOverrides"]["variableValues"]["firstMessage"] = f"Hello {name}, how can we assist you today?"
        
        # Log and send request to Vapi
        response = requests.post('https://api.vapi.ai/call/phone', json=response_payload)
        return jsonify({"status": "success", "response": response.json()})

    else:
        # Handle case for no match
        response_payload["assistantOverrides"]["variableValues"]["firstMessage"] = "Hello! How can we assist you today?"
        
        # Log and send request to Vapi with default handling
        response = requests.post('https://api.vapi.ai/call/phone', json=response_payload)
        return jsonify({"status": "success", "response": response.json()})

if __name__ == '__main__':
    app.run(port=5000)
