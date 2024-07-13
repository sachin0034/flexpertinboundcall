from flask import Flask, request, Response
import pandas as pd
import json
from twilio.twiml.voice_response import VoiceResponse

app = Flask(__name__)

# Load the JSON data
file_path = 'callerData.json'
with open(file_path, 'r') as file:
    data = json.load(file)

# Convert the JSON data to a DataFrame
df = pd.json_normalize(data['Sheet1'])

# Function to remove country code from phone number
def normalize_phone_number(phone_number):
    return phone_number[-10:]

@app.route("/twilio-webhook", methods=['POST'])
def twilio_webhook():
    from_number = request.form.get('From')
    normalized_number = normalize_phone_number(from_number)
    user = df[df['Customer Number'].astype(str) == normalized_number]
    
    response = VoiceResponse()
    
    if not user.empty:
        first_name = user.iloc[0]['FirstName']
        last_name = user.iloc[0]['LastName']
        response.say(f"Hello {first_name} {last_name}, how can I help you today?")
    else:
        response.say("Hello, how can I help you today?")
    
    return Response(str(response), mimetype='text/xml')

@app.route("/vapi-answer", methods=['POST'])
def vapi_answer():
    from_number = request.args.get('from')
    normalized_number = normalize_phone_number(from_number)
    user = df[df['Customer Number'].astype(str) == normalized_number]
    
    response = VoiceResponse()
    
    if not user.empty:
        first_name = user.iloc[0]['FirstName']
        last_name = user.iloc[0]['LastName']
        response.say(f"Hello {first_name} {last_name}, how can I help you today?")
    else:
        response.say("Hello, how can I help you today?")
    
    return Response(str(response), mimetype='text/xml')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
