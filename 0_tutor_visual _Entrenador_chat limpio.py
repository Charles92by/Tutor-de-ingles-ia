import streamlit as st
import azure.cognitiveservices.speech as speechsdk
import requests
import json
from audio_recorder_streamlit import audio_recorder
import os

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="British AI Tutor", page_icon="🇬🇧")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready to chat."}]
if "last_processed_audio" not in st.session_state:
    st.session_state.last_processed_audio = b""
if "manual_reset_counter" not in st.session_state:
    st.session_state.manual_reset_counter = 0
# NUEVO: Variable para guardar el audio entre recargas
if "audio_buffer" not in st.session_state:
    st.session_state.audio_buffer = None

# --- 2. CLAVES ---
try:
    raw_key = st.secrets["GOOGLE_API_KEY"]
    GOOGLE_API_KEY = raw_key.strip().replace('"', '').replace("'", "")
    AZURE_KEY = st.secrets["AZURE_KEY"]
    AZURE_REGION = st.secrets["AZURE_REGION"]
except:
    st.error("❌ ERROR: Faltan las claves en Secrets.")
    st.stop()

# --- 3. AUTO-DESCUBRIMIENTO (Ya sabemos que esto funciona) ---
def get_valid_model():
    if "final_model_id" in st.session_state: return st.session_state.final_model_id
    try:
        url_list = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
        response = requests.get(url_list)
        data = response.json()
        available_models = []
        if 'models' in data:
            for m in data['models']:
                if 'generateContent' in m['supportedGenerationMethods']:
                    available_models.append(m['name'])
        
        priority_order = ["models/gemini-1.5-flash", "models/gemini-1.5-flash-001", "models/gemini-pro"]
        sorted_models = sorted(available_models, key=lambda x: priority_order.index(x) if x in priority_order else 999)

        for model_name in sorted_models:
            test_url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"
            test_data = {"contents": [{"parts": [{"text": "Hi"}]}]}
            try:
                r = requests.post(test_url, headers={"Content-Type": "application/json"}, data=json.dumps(test_data))
                if r.status_code == 200:
                    st.session_state.final_model_id = model_name
                    return model_name
            except: continue
        st.error("❌ No hay modelos disponibles."); st.stop()
    except: st.error("Error conexión."); st.stop()

ACTIVE_MODEL = get_valid_model()

# --- 4. CEREBRO IA ---
def query_gemini(prompt_text):
    url = f"https://generativelanguage.googleapis.com/v1beta/{ACTIVE_MODEL}:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 400}
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else: return "I'm having trouble thinking right now."
    except: return "Connection error."

# --- 5. GENERAR AUDIO (SOLO BYTES) ---
def obtener_bytes_audio(text):
    if "Error" in text: return None
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_synthesis_voice_name = "en-GB-RyanNeural"
        # Usamos pull stream para obtener los bytes directamente
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
        result = synthesizer.speak_text_async(text).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return result.audio_data
    except: pass
    return None

def process_audio_file(file_path):
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_recognition_language = "en-GB"
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "3000")
        audio_config = speechsdk.audio.AudioConfig(filename=file_path)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        return recognizer.recognize_once()
    except: return None

# --- 6. PROMPT ---
def get_chat_response(history_list, user_input):
    formatted_history = ""
    for msg in history_list:
        role = "Tutor" if msg['role'] == "assistant" else "Student"
        formatted_history += f"{role}: {msg['content']}\n"

    prompt = f"""
    Act as a friendly, patient British English tutor.
    HISTORY: {formatted_history}
    INPUT: "{user_input}"
    INSTRUCTIONS:
    1. If input is unclear, guess context gently.
    2. Correct grammar mistakes in your reply.
    3. Respond naturally (2-3 sentences).
    """
    return query_gemini(prompt)

# --- 7. INTERFAZ ---
st.title("🇬🇧 British AI Tutor")

with st.sidebar:
    st.divider()
    if st.button("🔄 Reiniciar"):
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready."}]
        st.session_state.last_processed_audio = b""
        st.session_state.audio_buffer = None # Borramos audio pendiente
        st.session_state.manual_reset_counter += 1
        st.rerun()

# --- PANTALLA DE CHAT ---
# Mostramos el historial PRIMERO
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# --- REPRODUCTOR DE AUDIO PERSISTENTE 🔊 ---
# Este bloque se ejecuta DESPUÉS del rerun, por lo que el audio se queda fijo.
if st.session_state.audio_buffer:
    st.write("---")
    st.write("🔊 **Escucha la respuesta:**")
    # Autoplay=True para que suene solo en cuanto cargue la página
    st.audio(st.session_state.audio_buffer, format="audio/wav", autoplay=True)

# --- GRABADORA ---
st.write("---")
stable_key = f"recorder_main_{st.session_state.manual_reset_counter}"
st.write("👇 **Pulsa para hablar:**")
chat_audio = audio_recorder(text="", recording_color="#ff4b4b", neutral_color="#6aa36f", icon_size="2x", key=stable_key)

if chat_audio and chat_audio != st.session_state.last_processed_audio:
    st.session_state.last_processed_audio = chat_audio
    with open("temp.wav", "wb") as f: f.write(chat_audio)
    
    with st.spinner("Procesando..."):
        res = process_audio_file("temp.wav")
        
        if res and res.reason == speechsdk.ResultReason.RecognizedSpeech:
            user_text = res.text
            st.session_state.messages.append({"role": "user", "content": user_text})
            
            # Generamos respuesta de texto
            bot_reply = get_chat_response(st.session_state.messages, user_text)
            st.session_state.messages.append({"role": "assistant", "content": bot_reply})
            
            # Generamos audio y lo GUARDAMOS en la memoria (no lo reproducimos aún)
            audio_bytes = obtener_bytes_audio(bot_reply)
            st.session_state.audio_buffer = audio_bytes
            
            # Recargamos la página para mostrar el nuevo mensaje y el audio
            st.rerun()
        else:
            st.warning("😓 No te he entendido bien. Inténtalo de nuevo.")