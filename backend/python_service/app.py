from flask import Flask, request, jsonify
from flask_cors import CORS
import speech_recognition as sr
from pydub import AudioSegment
import os
import tempfile
import datetime
from pymongo import MongoClient

app = Flask(__name__)
CORS(app)

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['audio_converter']
transcriptions = db['transcriptions']

def convert_audio_to_text(audio_file_path):
    recognizer = sr.Recognizer()
    
    # Adjust recognition settings
    recognizer.energy_threshold = 300  # Increase sensitivity
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.8
    
    # Convert audio to wav if it's mp3
    if audio_file_path.endswith('.mp3'):
        audio = AudioSegment.from_mp3(audio_file_path)
        wav_path = audio_file_path.rsplit('.', 1)[0] + '.wav'
        audio.export(wav_path, format="wav")
        audio_file_path = wav_path

    try:
        with sr.AudioFile(audio_file_path) as source:
            print(f"Processing audio file: {audio_file_path}")
            print(f"Audio duration: {source.DURATION} seconds")
            print(f"Audio sample rate: {source.SAMPLE_RATE} Hz")
            
            # Adjust for ambient noise
            recognizer.adjust_for_ambient_noise(source)
            
            # Record audio data
            print("Recording audio data...")
            audio_data = recognizer.record(source)
            
            print("Recognizing speech...")
            text = recognizer.recognize_google(audio_data, 
                                            language="en-US",
                                            show_all=True)
            print(f"Recognition result: {text}")
            
            if isinstance(text, dict):
                return text.get('alternative', [{'transcript': 'Could not understand audio'}])[0]['transcript']
            elif isinstance(text, list):
                return text[0]['transcript'] if text else "Could not understand audio"
            else:
                return str(text)
                
    except sr.UnknownValueError as e:
        print(f"Speech recognition error: {str(e)}")
        return "Could not understand audio"
    except sr.RequestError as e:
        print(f"Speech recognition service error: {str(e)}")
        return f"Error with the speech recognition service; {str(e)}"
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return f"Error processing audio: {str(e)}"

@app.route('/convert', methods=['POST'])
def convert_audio():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith(('.wav', '.mp3')):
        return jsonify({'error': 'Invalid file format. Only WAV and MP3 files are supported'}), 400

    try:
        # Create temporary file
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, file.filename)
        file.save(temp_path)
        
        # Convert audio to text
        text = convert_audio_to_text(temp_path)
        
        # Save to MongoDB
        result = transcriptions.insert_one({
            'filename': file.filename,
            'text': text,
            'timestamp': datetime.datetime.utcnow()
        })
        
        # Clean up
        os.remove(temp_path)
        os.rmdir(temp_dir)
        
        return jsonify({
            'text': text,
            'id': str(result.inserted_id)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/history', methods=['GET'])
def get_history():
    try:
        history = list(transcriptions.find().sort('timestamp', -1).limit(10))
        # Convert ObjectId to string for JSON serialization
        for item in history:
            item['_id'] = str(item['_id'])
        return jsonify(history)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
