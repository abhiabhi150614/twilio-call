from flask import Flask, request, Response, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client
import google.generativeai as genai
import os
import urllib.parse
import time
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
twilio_client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])

# Enhanced conversation storage
conversations = {}
call_logs = {}

class ConversationManager:
    def __init__(self, call_sid, context=""):
        self.call_sid = call_sid
        self.context = context
        self.history = []
        self.start_time = time.time()
        self.response_count = 0
        self.user_inputs = []
        
    def add_exchange(self, user_input, ai_response):
        self.user_inputs.append(user_input)
        self.history.append(f"User: {user_input}")
        self.history.append(f"AI: {ai_response}")
        self.response_count += 1
        
        # Keep only last 8 exchanges for performance
        if len(self.history) > 16:
            self.history = self.history[-16:]
    
    def get_conversation_summary(self):
        return {
            'call_sid': self.call_sid,
            'duration': time.time() - self.start_time,
            'exchanges': self.response_count,
            'context': self.context[:100],
            'recent_topics': self.user_inputs[-3:] if self.user_inputs else []
        }

def get_conversation(call_sid, context=""):
    if call_sid not in conversations:
        conversations[call_sid] = ConversationManager(call_sid, context)
        print(f"🆕 New conversation started: {call_sid}")
    return conversations[call_sid]

def smart_ai_response(prompt, conversation_manager):
    """Enhanced AI response with proper context parsing"""
    
    prompt_clean = prompt.lower().strip()
    context = conversation_manager.context
    
    # Quick responses for common phrases
    quick_responses = {
        'hello': "Hi Abhishek! Ready to help with your learning!",
        'hi': "Hello! What can I help you study today?",
        'thanks': "You're welcome! Keep up the great work!",
        'bye': "Goodbye Abhishek! Happy studying!",
        'yes': "Great! What's next in your learning?",
        'no': "No problem! Anything else about your studies?"
    }
    
    if prompt_clean in quick_responses:
        return quick_responses[prompt_clean]
    
    # Parse context for learning information
    learning_info = {}
    if context:
        if "Today's Topic:" in context:
            topic_start = context.find("Today's Topic:") + len("Today's Topic:")
            topic_end = context.find("Progress:", topic_start)
            if topic_end == -1:
                topic_end = len(context)
            learning_info['topic'] = context[topic_start:topic_end].strip()
        
        if "Progress:" in context:
            progress_start = context.find("Progress:") + len("Progress:")
            progress_end = context.find("Be specific", progress_start)
            if progress_end == -1:
                progress_end = len(context)
            learning_info['progress'] = context[progress_start:progress_end].strip()
        
        if "Current Month:" in context:
            month_start = context.find("Current Month:") + len("Current Month:")
            month_end = context.find("Today's Topic:", month_start)
            if month_end == -1:
                month_end = len(context)
            learning_info['month'] = context[month_start:month_end].strip()
    
    # Handle specific learning questions
    if any(word in prompt_clean for word in ['today', 'topic', 'study']):
        if learning_info.get('topic'):
            return f"Today's topic: {learning_info['topic'][:50]}. Let's focus on this!"
        else:
            return "Focus on your current learning objectives. What specific area needs attention?"
    
    if any(word in prompt_clean for word in ['progress', 'how much', 'percentage']):
        if learning_info.get('progress'):
            return f"Your progress: {learning_info['progress']}. Keep going!"
        else:
            return "You're making steady progress. Every step counts!"
    
    if 'day 1' in prompt_clean and 'month' in prompt_clean:
        if learning_info.get('topic'):
            return f"Day 1 focus: {learning_info['topic'][:40]}. Start with the basics!"
        else:
            return "Day 1 is about building foundations. Start with core concepts!"
    
    # Try Gemini with enhanced prompt
    try:
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        enhanced_prompt = f"""
        CONTEXT: {context}
        
        USER QUESTION: "{prompt}"
        
        INSTRUCTIONS:
        - You are Abhishek's AI learning assistant
        - Reference his specific learning plan and current topic from the context
        - If asked about today's topic, mention the specific topic from context
        - If asked about progress, mention the specific percentage from context
        - Be encouraging and specific about his learning journey
        - Keep response under 25 words for voice call
        - Always reference his actual learning context, not generic advice
        
        RESPOND:
        """
        
        response = model.generate_content(
            enhanced_prompt,
            generation_config={'max_output_tokens': 50, 'temperature': 0.3}
        )
        
        if response.text and len(response.text.strip()) > 5:
            return response.text.strip()[:100]
            
    except Exception as e:
        print(f"❌ Gemini error: {e}")
    
    # Enhanced fallbacks based on context
    if learning_info.get('topic'):
        return f"Focus on {learning_info['topic'][:30]}. You've got this!"
    elif 'python' in context.lower():
        return "Work on Python fundamentals. Practice coding daily!"
    elif 'ai' in context.lower():
        return "Build your AI skills step by step. Start with basics!"
    else:
        return "Keep studying consistently. What specific help do you need?"

@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.form.get('CallSid')
    user_context = request.args.get('context', 'You are a helpful AI assistant for Abhishek.')
    
    # Decode URL-encoded context
    user_context = urllib.parse.unquote(user_context)
    
    # Initialize conversation
    conv = get_conversation(call_sid, user_context)
    
    # Log call start
    call_logs[call_sid] = {
        'start_time': time.time(),
        'status': 'started',
        'context': user_context
    }
    
    print(f"📞 Call started: {call_sid}")
    print(f"🎯 Context: {user_context}")
    
    resp = VoiceResponse()
    
    # Parse context for personalized greeting
    greeting = "Hi Abhishek! I'm ready to help with your learning!"
    if "Today's Topic:" in user_context:
        greeting = "Hi Abhishek! Ready to work on today's topic?"
    
    resp.say(greeting, voice="alice")
    
    gather = Gather(
        input='speech', 
        timeout=8, 
        action='/process_speech',
        speechTimeout=3,
        language='en-US'
    )
    resp.append(gather)
    resp.redirect('/voice')
    return Response(str(resp), mimetype='text/xml')

@app.route("/process_speech", methods=["POST"])
def process_speech():
    call_sid = request.form.get('CallSid')
    speech = request.form.get('SpeechResult', '').strip()
    confidence = request.form.get('Confidence', '0')
    
    print(f"🎤 User said: '{speech}' (confidence: {confidence})")
    
    resp = VoiceResponse()
    
    # Handle empty or unclear speech
    if not speech or len(speech) < 2:
        resp.say("I'm listening. What would you like to know about your learning?", voice="alice")
        gather = Gather(input='speech', timeout=6, action='/process_speech', speechTimeout=3)
        resp.append(gather)
        resp.redirect('/voice')
        return Response(str(resp), mimetype='text/xml')
    
    try:
        # Get conversation manager
        conv = get_conversation(call_sid)
        
        # Generate smart response with context
        ai_response = smart_ai_response(speech, conv)
        
        # Add to conversation history
        conv.add_exchange(speech, ai_response)
        
        # Update call log
        if call_sid in call_logs:
            call_logs[call_sid]['last_exchange'] = time.time()
            call_logs[call_sid]['total_exchanges'] = conv.response_count
        
        print(f"💬 Exchange #{conv.response_count}: User: '{speech}' -> AI: '{ai_response}'")
        
        # Build response
        resp.say(ai_response, voice="alice")
        
        # Check for conversation ending
        if any(word in speech.lower() for word in ['bye', 'goodbye', 'end call', 'hang up', 'stop']):
            resp.say("Keep up the great learning, Abhishek! Goodbye!", voice="alice")
            resp.hangup()
            
            # Log call end
            if call_sid in call_logs:
                call_logs[call_sid]['status'] = 'ended'
                call_logs[call_sid]['end_time'] = time.time()
            
            print(f"📴 Call ended: {call_sid}")
            return Response(str(resp), mimetype='text/xml')
        
        # Continue conversation
        timeout = 10 if conv.response_count < 3 else 8
        gather = Gather(
            input='speech', 
            timeout=timeout, 
            action='/process_speech',
            speechTimeout=3
        )
        resp.append(gather)
        resp.redirect('/voice')
        
    except Exception as e:
        print(f"❌ Process error: {e}")
        resp.say("Sorry, let me try again. What about your learning can I help with?", voice="alice")
        gather = Gather(input='speech', timeout=6, action='/process_speech', speechTimeout=3)
        resp.append(gather)
        resp.redirect('/voice')
    
    return Response(str(resp), mimetype='text/xml')

@app.route("/call_status/<call_sid>", methods=["GET"])
def get_call_status(call_sid):
    """Get detailed call status and conversation info"""
    try:
        # Get Twilio call info
        call = twilio_client.calls(call_sid).fetch()
        
        # Get conversation info
        conv_info = {}
        if call_sid in conversations:
            conv_info = conversations[call_sid].get_conversation_summary()
        
        # Get call log info
        log_info = call_logs.get(call_sid, {})
        
        return jsonify({
            'call_sid': call_sid,
            'twilio_status': call.status,
            'duration': call.duration,
            'conversation': conv_info,
            'log': log_info
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/active_calls", methods=["GET"])
def get_active_calls():
    """Get all active conversations"""
    active = []
    for call_sid, conv in conversations.items():
        if call_sid in call_logs and call_logs[call_sid].get('status') != 'ended':
            active.append(conv.get_conversation_summary())
    
    return jsonify({
        'active_calls': len(active),
        'conversations': active
    })

@app.route("/make_call", methods=["POST"])
def make_call_api():
    data = request.get_json()
    
    if not data or 'phone_number' not in data:
        return jsonify({'error': 'phone_number is required'}), 400
    
    phone_number = data['phone_number']
    context = data.get('context', 'You are Abhishek\'s helpful AI learning assistant.')
    
    try:
        encoded_context = urllib.parse.quote(context)
        webhook_url = f"{request.url_root}voice?context={encoded_context}"
        
        call = twilio_client.calls.create(
            to=phone_number,
            from_=os.environ["TWILIO_PHONE_NUMBER"],
            url=webhook_url
        )
        
        return jsonify({
            'success': True,
            'call_sid': call.sid,
            'message': f'Call initiated to {phone_number}',
            'webhook_url': webhook_url
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/")
def index():
    return """
    <h1>🤖 Enhanced Learning Call Bot</h1>
    <p>✅ Context-aware AI responses</p>
    <p>✅ Learning plan integration</p>
    <p>✅ Real-time conversation tracking</p>
    <p>✅ Enhanced error handling</p>
    <br>
    <h3>API Endpoints:</h3>
    <ul>
        <li><code>POST /make_call</code> - Initiate calls</li>
        <li><code>GET /call_status/&lt;call_sid&gt;</code> - Get call details</li>
        <li><code>GET /active_calls</code> - List active conversations</li>
    </ul>
    """

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
