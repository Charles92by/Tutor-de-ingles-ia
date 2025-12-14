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

# --- 3. AUTO-DESCUBRIMIENTO DE MODELO ---
def get_valid_model():
    if "final_model_id" in st.session_state: return st.session_state.final_model_id
    try:
        # Pedimos el menú a Google
        url_list = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
        response = requests.get(url_list)
        data = response.json()
        available_models = []
        if 'models' in data:
            for m in data['models']:
                if 'generateContent' in m['supportedGenerationMethods']:
                    available_models.append(m['name'])
        
        # Probamos en orden de preferencia
        priority = ["models/gemini-1.5-flash", "models/gemini-1.5-flash-001", "models/gemini-pro"]
        sorted_models = sorted(available_models, key=lambda x: priority.index(x) if x in priority else 999)

        for model in sorted_models:
            test_url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GOOGLE_API_KEY}"
            test_data = {"contents": [{"parts": [{"text": "Hi"}]}]}
            try:
                r = requests.post(test_url, headers={"Content-Type": "application/json"}, data=json.dumps(test_data))
                if r.status_code == 200:
                    st.session_state.final_model_id = model
                    return model
            except: continue
        st.error("❌ No hay modelos disponibles.")
        st.stop()
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
        else: return "I'm having trouble thinking."
    except: return "Connection error."

# --- 5. AUDIO FUNCTIONS ---
def obtener_bytes_audio(text):
    if "Error" in text: return None
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_synthesis_voice_name = "en-GB-RyanNeural"
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
        # 3 segundos de paciencia
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

# --- BARRA LATERAL (CONTROLES Y AUDIO) ---
with st.sidebar:
    st.divider()
    if st.button("🔄 Reiniciar"):
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready."}]
        st.session_state.last_processed_audio = b""
        st.session_state.audio_buffer = None
        st.session_state.manual_reset_counter += 1
        st.rerun()
    
    # --- REPRODUCTOR EN LA BARRA LATERAL (NO MOLESTA AL BOTÓN) ---
    st.divider()
    st.write("🔊 **Audio Respuesta:**")
    if st.session_state.audio_buffer:
        # Autoplay activado. Al estar en la sidebar, no rompe el layout principal.
        st.audio(st.session_state.audio_buffer, format="audio/wav", autoplay=True)
    else:
        st.caption("(Esperando respuesta...)")

# --- CHAT PRINCIPAL ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Separador visual
st.divider()

# --- ZONA DE GRABACIÓN (ESTABLE) ---
# Usamos un contenedor para asegurar que el botón tiene su espacio reservado
input_container = st.container()

with input_container:
    st.write("👇 **Pulsa para hablar:**")
    stable_key = f"recorder_main_{st.session_state.manual_reset_counter}"
    
    # El grabador se renderiza AQUÍ, sin interferencias del audio player
    chat_audio = audio_recorder(text="", recording_color="#ff4b4b", neutral_color="#6aa36f", icon_size="2x", key=stable_key)

    if chat_audio and chat_audio != st.session_state.last_processed_audio:
        st.session_state.last_processed_audio = chat_audio
        with open("temp.wav", "wb") as f: f.write(chat_audio)
        
        with st.spinner("Procesando..."):
            res = process_audio_file("temp.wav")
            
            if res and res.reason == speechsdk.ResultReason.RecognizedSpeech:
                user_text = res.text
                st.session_state.messages.append({"role": "user", "content": user_text})
                
                # Generamos texto
                bot_reply = get_chat_response(st.session_state.messages, user_text)
                st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                
                # Generamos audio y lo mandamos a la SIDEBAR
                audio_bytes = obtener_bytes_audio(bot_reply)
                st.session_state.audio_buffer = audio_bytes
                
                st.rerun()
            else:
                st.warning("😓 No te he entendido bien. Inténtalo de nuevo.")