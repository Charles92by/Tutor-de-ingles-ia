import streamlit as st
import azure.cognitiveservices.speech as speechsdk
import requests
import json
from audio_recorder_streamlit import audio_recorder

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="British AI Tutor", page_icon="🇬🇧")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready to chat."}]
if "last_processed_audio" not in st.session_state:
    st.session_state.last_processed_audio = b""
if "manual_reset_counter" not in st.session_state:
    st.session_state.manual_reset_counter = 0

# --- 2. GESTIÓN DE CLAVES A PRUEBA DE FALLOS 🛡️ ---
try:
    # 1. Recuperamos las claves
    raw_google_key = st.secrets["GOOGLE_API_KEY"]
    AZURE_KEY = st.secrets["AZURE_KEY"]
    AZURE_REGION = st.secrets["AZURE_REGION"]

    # 2. LIMPIEZA AUTOMÁTICA DE LA CLAVE GOOGLE
    # Quitamos espacios, saltos de línea y comillas extra que se hayan colado
    GOOGLE_API_KEY = raw_google_key.strip().replace('"', '').replace("'", "")
    
except Exception as e:
    st.error(f"❌ ERROR EN SECRETS: {e}")
    st.stop()

# --- 3. CONEXIÓN MANUAL AL MODELO 1.5 FLASH 🚀 ---
def query_gemini_direct(prompt_text):
    # Usamos la URL v1beta estándar
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GOOGLE_API_KEY}"
    
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
            # AQUÍ VEREMOS EL ERROR REAL SI FALLA
            error_msg = response.text
            if "API_KEY_INVALID" in error_msg:
                return "❌ CLAVE INVÁLIDA: Revisa haber copiado bien la clave AIza..."
            elif "PERMISSION_DENIED" in error_msg:
                return "❌ PERMISO DENEGADO: Tu clave es nueva pero no tiene acceso. ¿Activaste la API?"
            else:
                return f"❌ Error Google ({response.status_code}): {error_msg}"
                
    except Exception as e:
        return f"Error Conexión: {str(e)}"

# --- 4. FUNCIONES AUDIO (Azure) ---
def generar_audio_resp(text):
    if "❌" in text: return # No leer errores
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_synthesis_voice_name = "en-GB-RyanNeural"
        audio_config = speechsdk.audio.AudioOutputConfig(filename="output_ghost.wav")
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        synthesizer.speak_text_async(text).get()
    except: pass

def process_audio_file(file_path):
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_recognition_language = "en-GB"
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "3000")
        audio_config = speechsdk.audio.AudioConfig(filename=file_path)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        return recognizer.recognize_once()
    except: return None

# --- 5. LÓGICA CHAT ---
def get_chat_response(history, user_input):
    prompt = f"Act as a British English tutor. Keep it short. History: {history}. User: {user_input}"
    return query_gemini_direct(prompt)

# --- 6. PRUEBA DE CONEXIÓN AL INICIAR ---
# Esto ejecutará una prueba nada más cargar la página para ver si la clave funciona
if "connection_tested" not in st.session_state:
    test_response = query_gemini_direct("Hello")
    if "❌" in test_response:
        st.error(test_response) # Muestra el error en grande
    else:
        st.sidebar.success("✅ Conexión con Google: OK")
    st.session_state.connection_tested = True

# --- 7. INTERFAZ ---
st.title("🇬🇧 British AI Tutor")

with st.sidebar:
    st.divider()
    if st.button("🔄 Reiniciar"):
        st.session_state.messages = [{"role": "assistant", "content": "Hello! Ready."}]
        st.session_state.last_processed_audio = b""
        st.session_state.manual_reset_counter += 1
        st.rerun()

stable_key = f"recorder_chat_{st.session_state.manual_reset_counter}"

# MODO CHAT DIRECTO
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
            
            # Generar respuesta
            historial = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
            bot_reply = get_chat_response(historial, user_text)
            
            st.session_state.messages.append({"role": "assistant", "content": bot_reply})
            generar_audio_resp(bot_reply)
            st.rerun()
        else:
            st.warning("No se entendió el audio.")

# Mostrar mensajes
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])