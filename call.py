import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

call = client.calls.create(
    to=os.getenv("YOUR_PHONE_NUMBER"),
    from_=os.getenv("TWILIO_PHONE_NUMBER"),
    url="https://ai-callbot.onrender.com/voice"  # Replace with your actual Render URL
)

print("Call started. SID:", call.sid)
