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
    # Limpieza de seguridad por si hay espacios
    GOOGLE_API_KEY = raw_key.strip().replace('"', '').replace("'", "")
    AZURE_KEY = st.secrets["AZURE_KEY"]
    AZURE_REGION = st.secrets["AZURE_REGION"]
except:
    st.error("❌ ERROR: Faltan las claves en Secrets.")
    st.stop()

# --- 3. AUTO-DESCUBRIMIENTO DE MODELOS (LA SOLUCIÓN FINAL) 🕵️‍♂️ ---
def get_valid_model():
    """
    Pregunta a Google qué modelos tiene disponibles la llave y elige uno válido.
    """
    if "final_model_id" in st.session_state:
        return st.session_state.final_model_id

    st.info("🔍 Analizando tu cuenta de Google para encontrar un modelo válido...")
    
    # 1. Pedimos la lista ("El Menú")
    try:
        url_list = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
        response = requests.get(url_list)
        
        if response.status_code != 200:
            st.error(f"❌ Error al listar modelos: {response.text}")
            st.stop()
            
        data = response.json()
        available_models = []
        
        # Filtramos solo los que sirven para chatear (generateContent)
        if 'models' in data:
            for m in data['models']:
                if 'generateContent' in m['supportedGenerationMethods']:
                    available_models.append(m['name']) # ej: "models/gemini-pro"
        
        if not available_models:
            st.error("❌ Tu llave es válida pero no tiene acceso a NINGÚN modelo. ¿Has activado la API en Google Cloud?")
            st.stop()
            
        # 2. Probamos cuál funciona (Priorizamos Flash y Pro)
        # Reordenamos la lista para probar los mejores primero
        priority_order = [
            "models/gemini-1.5-flash", 
            "models/gemini-1.5-flash-001",
            "models/gemini-1.5-flash-002",
            "models/gemini-1.5-flash-8b",
            "models/gemini-pro",
            "models/gemini-1.0-pro"
        ]
        
        # Ordenamos la lista disponible según nuestra prioridad
        sorted_models = sorted(available_models, key=lambda x: priority_order.index(x) if x in priority_order else 999)

        for model_name in sorted_models:
            # Prueba de fuego: Intentar generar un "Hola"
            test_url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"
            test_data = {"contents": [{"parts": [{"text": "Hi"}]}]}
            try:
                r = requests.post(test_url, headers={"Content-Type": "application/json"}, data=json.dumps(test_data))
                if r.status_code == 200:
                    st.session_state.final_model_id = model_name
                    st.success(f"✅ ¡MODELO ENCONTRADO! Usando: **{model_name}**")
                    return model_name
            except:
                continue
        
        st.error("❌ Se encontraron modelos, pero todos fallaron al probarlos (posible error 429 de cuota).")
        st.write("Modelos vistos:", available_models)
        st.stop()

    except Exception as e:
        st.error(f"Error de conexión fatal: {e}")
        st.stop()

# EJECUTAMOS EL AUTO-DESCUBRIMIENTO
ACTIVE_MODEL = get_valid_model()

# --- 4. FUNCIÓN PARA LLAMAR AL MODELO ELEGIDO ---
def query_gemini(prompt_text):
    url = f"https://generativelanguage.googleapis.com/v1beta/{ACTIVE_MODEL}:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 150}
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"Error ({response.status_code}): {response.text}"
    except Exception as e:
        return f"Error Red: {str(e)}"

# --- 5. FUNCIONES AUDIO (Con arreglo de pausas) ---
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
        # 3000ms de espera para que no corte frases largas
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "3000")
        
        audio_config = speechsdk.audio.AudioConfig(filename=file_path)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        return recognizer.recognize_once()
    except: return None

# --- 6. CEREBRO IA ---
def get_chat_response(history, user_input):
    prompt = f"Act as a British English tutor. Keep replies short (max 2 sentences). History: {history}. User: {user_input}"
    return query_gemini(prompt)

# --- 7. INTERFAZ ---
st.title("🇬🇧 British AI Tutor")
st.caption(f"🤖 Conectado a: {ACTIVE_MODEL}")

with st.sidebar:
    st.divider()
    if st.button("🔄 Reiniciar"):
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready."}]
        st.session_state.last_processed_audio = b""
        st.session_state.manual_reset_counter += 1
        # Forzamos re-escanear si se reinicia
        if "final_model_id" in st.session_state: del st.session_state.final_model_id
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
            st.session_state.messages.append({"role": "user", "content": user_text})
            
            historial = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
            bot_reply = get_chat_response(historial, user_text)
            
            st.session_state.messages.append({"role": "assistant", "content": bot_reply})
            generar_audio_resp(bot_reply)
            st.rerun()
        else:
            st.warning("No se entendió el audio.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])