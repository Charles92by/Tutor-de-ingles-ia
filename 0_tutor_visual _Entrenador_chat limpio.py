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

# --- 2. CLAVES ---
try:
    raw_key = st.secrets["GOOGLE_API_KEY"]
    GOOGLE_API_KEY = raw_key.strip().replace('"', '').replace("'", "")
    AZURE_KEY = st.secrets["AZURE_KEY"]
    AZURE_REGION = st.secrets["AZURE_REGION"]
except:
    st.error("❌ ERROR: Faltan las claves en Secrets.")
    st.stop()

# --- 3. AUTO-DESCUBRIMIENTO DE MODELOS 🕵️‍♂️ ---
def get_valid_model():
    if "final_model_id" in st.session_state:
        return st.session_state.final_model_id

    st.info("🔍 Buscando el mejor modelo para tu cuenta...")
    
    try:
        # 1. Obtenemos lista de modelos
        url_list = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
        response = requests.get(url_list)
        data = response.json()
        available_models = []
        
        if 'models' in data:
            for m in data['models']:
                if 'generateContent' in m['supportedGenerationMethods']:
                    available_models.append(m['name'])
        
        # 2. Prioridad de prueba (Flash suele ser el más rápido y libre)
        priority_order = [
            "models/gemini-1.5-flash", 
            "models/gemini-1.5-flash-001",
            "models/gemini-1.5-flash-8b",
            "models/gemini-pro",
            "models/gemini-1.0-pro"
        ]
        
        sorted_models = sorted(available_models, key=lambda x: priority_order.index(x) if x in priority_order else 999)

        for model_name in sorted_models:
            test_url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"
            test_data = {"contents": [{"parts": [{"text": "Hi"}]}]}
            try:
                r = requests.post(test_url, headers={"Content-Type": "application/json"}, data=json.dumps(test_data))
                if r.status_code == 200:
                    st.session_state.final_model_id = model_name
                    st.success(f"✅ Conectado a: **{model_name}**")
                    return model_name
            except: continue
        
        st.error("❌ No se encontraron modelos disponibles.")
        st.stop()

    except Exception as e:
        st.error(f"Error de conexión: {e}")
        st.stop()

ACTIVE_MODEL = get_valid_model()

# --- 4. CEREBRO IA (MEJORADO Y ESTABILIZADO) 🧠 ---
def query_gemini(prompt_text):
    url = f"https://generativelanguage.googleapis.com/v1beta/{ACTIVE_MODEL}:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    # AQUÍ ESTÁ EL CAMBIO IMPORTANTE:
    # 1. maxOutputTokens: 400 (antes 150) -> Para que no se corte.
    # 2. temperature: 0.3 (antes 0.7) -> Para que sea más centrado y no diga tonterías.
    data = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 400
        },
        # Filtros de seguridad desactivados para evitar bloqueos tontos
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"Error ({response.status_code}): {response.text}"
    except Exception as e:
        return f"Error Red: {str(e)}"

# --- 5. AUDIO (PACIENCIA 3s) ---
def generar_audio_resp(text):
    if "Error" in text: return
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_synthesis_voice_name = "en-GB-RyanNeural"
        audio_config = speechsdk.audio.AudioOutputConfig(filename="output_ghost.wav")
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        result = synthesizer.speak_text_async(text).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            st.audio(result.audio_data, format="audio/wav")
    except: pass

def process_audio_file(file_path):
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_recognition_language = "en-GB"
        # 3 segundos de espera antes de cortar
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "3000")
        
        audio_config = speechsdk.audio.AudioConfig(filename=file_path)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        return recognizer.recognize_once()
    except: return None

# --- 6. PROMPT INGENIERÍA ---
def get_chat_response(history_list, user_input):
    # Formateamos el historial para que la IA entienda quién es quién
    formatted_history = ""
    for msg in history_list:
        role = "Tutor" if msg['role'] == "assistant" else "Student"
        formatted_history += f"{role}: {msg['content']}\n"

    prompt = f"""
    Act as a friendly, patient British English tutor.
    
    CONVERSATION HISTORY:
    {formatted_history}
    
    CURRENT INPUT (Student): "{user_input}"
    
    INSTRUCTIONS:
    1. If the Student's input is incomplete or weird (due to audio errors), guess what they meant or ask for clarification politely.
    2. Correct any grammar mistakes gently in your response.
    3. Respond naturally to continue the conversation.
    4. Keep your response complete but concise (2-3 sentences max).
    5. Do not cut off your sentences.
    """
    return query_gemini(prompt)

# --- 7. INTERFAZ ---
st.title("🇬🇧 British AI Tutor")

with st.sidebar:
    st.divider()
    if st.button("🔄 Reiniciar"):
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready to chat."}]
        st.session_state.last_processed_audio = b""
        st.session_state.manual_reset_counter += 1
        # No borramos el modelo para no perder tiempo re-escaneando
        st.rerun()

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
            # Feedback visual de lo que entendió
            st.toast(f"🗣️ Oído: {user_text}") 
            
            st.session_state.messages.append({"role": "user", "content": user_text})
            
            # Pasamos la lista completa de mensajes
            bot_reply = get_chat_response(st.session_state.messages, user_text)
            
            st.session_state.messages.append({"role": "assistant", "content": bot_reply})
            generar_audio_resp(bot_reply)
            st.rerun()
        else:
            st.warning("😓 No te he entendido bien. Inténtalo de nuevo.")

# Mostrar chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])