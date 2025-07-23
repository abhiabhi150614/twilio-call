from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
import google.generativeai as genai
import os

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

def ask_gemini(prompt):
    model = genai.GenerativeModel("gemini-pro")
    response = model.generate_content(prompt)
    return response.text.strip()

@app.route("/voice", methods=["POST"])
def voice():
    resp = VoiceResponse()
    resp.say("Hello! Ask your question after the beep.", voice="alice")
    gather = Gather(input='speech', timeout=5, action='/process_speech')
    resp.append(gather)
    return Response(str(resp), mimetype='text/xml')

@app.route("/process_speech", methods=["POST"])
def process_speech():
    speech = request.form.get('SpeechResult')
    if not speech:
        answer = "Sorry, I didn't hear anything."
    else:
        answer = ask_gemini(speech)

    resp = VoiceResponse()
    resp.say(answer, voice="alice")
    return Response(str(resp), mimetype='text/xml')

@app.route("/")
def index():
    return "Callbot is running!"

if __name__ == "__main__":
    app.run(debug=True)
