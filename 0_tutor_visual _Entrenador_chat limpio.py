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
    AZURE_KEY = st.secrets["AZURE_KEY"]
    AZURE_REGION = st.secrets["AZURE_REGION"]
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ ERROR: Faltan las claves en Secrets.")
    st.stop()

# --- 3. ESCÁNER DE MODELOS (REST API) 🕵️‍♂️ ---
# Esta función prueba variantes específicas hasta encontrar una que Google acepte
def find_working_model():
    if "working_model_id" in st.session_state:
        return st.session_state.working_model_id
    
    # Lista de "puertas traseras" y versiones específicas
    candidates = [
        "gemini-1.5-flash",          # El ideal
        "gemini-1.5-flash-002",      # Versión específica moderna
        "gemini-1.5-flash-001",      # Versión específica anterior
        "gemini-1.5-flash-8b",       # Versión ligera (suele estar libre)
        "gemini-2.0-flash-exp",      # Experimental (de tu lista)
        "gemini-1.0-pro"             # El clásico real
    ]
    
    st.sidebar.text("🔍 Escaneando modelos...")
    
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": "Hi"}]}]}
    
    for model in candidates:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GOOGLE_API_KEY}"
            response = requests.post(url, headers=headers, data=json.dumps(data))
            
            # Si da 200 OK, hemos encontrado el ganador
            if response.status_code == 200:
                st.session_state.working_model_id = model
                st.sidebar.success(f"✅ Conectado: {model}")
                return model
            # Si da 429 es que ese está lleno, seguimos buscando
        except:
            continue
            
    st.error("❌ ERROR TOTAL: Ningún modelo gratuito disponible. Crea una API Key en un PROYECTO NUEVO.")
    st.stop()

# Ejecutamos el escáner una vez y guardamos el modelo
ACTIVE_MODEL_ID = find_working_model()

def query_gemini(prompt_text):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{ACTIVE_MODEL_ID}:generateContent?key={GOOGLE_API_KEY}"
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
            return f"Error Google ({response.status_code}): {response.text}"
    except Exception as e:
        return f"Error Conexión: {str(e)}"

# --- 4. FUNCIONES AUDIO (Con Paciencia 3s) ---
def generar_audio_resp(text):
    try:
        if "Error" in text: return
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_synthesis_voice_name = "en-GB-RyanNeural"
        audio_config = speechsdk.audio.AudioOutputConfig(filename="output_ghost.wav")
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        result = synthesizer.speak_text_async(text).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            st.audio(result.audio_data, format="audio/wav")
    except: pass

def process_audio_file(file_path, reference_text=None):
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_recognition_language = "en-GB"
        
        # 3 segundos de paciencia para frases largas
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "3000")
        
        audio_config = speechsdk.audio.AudioConfig(filename=file_path)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        
        if reference_text:
            pronunciation_config = speechsdk.PronunciationAssessmentConfig(
                reference_text=reference_text,
                grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
                granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme
            )
            pronunciation_config.apply_to(recognizer)
        
        return recognizer.recognize_once()
    except Exception as e:
        st.error(f"Error Azure: {e}")
        return None

# --- 5. CEREBRO IA ---
def get_chat_response(history, user_input):
    prompt = f"""
    You are a friendly British English tutor.
    Conversation History: {history}
    User just said: "{user_input}"
    
    Instructions:
    1. If transcription is slightly wrong, guess context.
    2. Correct grammar gently.
    3. Keep it short. PLAIN TEXT ONLY.
    """
    return query_gemini(prompt)

def get_pronunciation_tips(text, errors):
    prompt = f"User said: '{text}'. Errors: {', '.join(errors)}. Give 1 sentence with pronunciation tips (IPA)."
    return query_gemini(prompt)

# --- 6. INTERFAZ ---
st.title("🇬🇧 British AI Tutor")

with st.sidebar:
    st.divider()
    modo = st.radio("Modo:", ["🎯 Entrenador", "💬 Conversación"])
    st.divider()
    if st.button("🔄 Reiniciar Conversación"):
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready to chat."}]
        st.session_state.last_processed_audio = b""
        st.session_state.manual_reset_counter += 1
        # Borramos el modelo guardado para re-escanear si hace falta
        if "working_model_id" in st.session_state:
            del st.session_state.working_model_id
        st.rerun()

stable_key = f"recorder_{modo}_{st.session_state.manual_reset_counter}"

if modo == "🎯 Entrenador":
    st.subheader("Entrenador de Lectura")
    frase = st.selectbox("Frase:", ["I would like a bottle of water please.", "The weather in London is unpredictable."])
    st.info(f"📖 Lee: **{frase}**")
    
    audio_bytes = audio_recorder(text="", recording_color="#e8b62c", neutral_color="#6aa36f", icon_size="2x", key=stable_key)
    
    if audio_bytes and audio_bytes != st.session_state.last_processed_audio:
        st.session_state.last_processed_audio = audio_bytes
        st.audio(audio_bytes, format="audio/wav")
        with open("temp.wav", "wb") as f: f.write(audio_bytes)
        
        with st.spinner("Analizando..."):
            res = process_audio_file("temp.wav", reference_text=frase)
            
        if res and res.reason == speechsdk.ResultReason.RecognizedSpeech:
            assess = speechsdk.PronunciationAssessmentResult(res)
            score = assess.accuracy_score
            st.metric("Nota", f"{score}/100")
            errores = [w.word for w in assess.words if w.accuracy_score < 80 and w.error_type != "None"]
            
            if errores:
                st.write(f"⚠️ Errores: {', '.join(errores)}")
                feedback = get_pronunciation_tips(frase, errores)
                st.info(feedback)
                generar_audio_resp(feedback)
            else:
                st.success("Perfect!")
                generar_audio_resp("Excellent pronunciation!")
        else:
            st.warning("No se escuchó bien.")

else:
    st.subheader("Chat Británico")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            
    st.write("---")
    st.write("👇 **Pulsa para hablar:**")
    
    chat_audio = audio_recorder(text="", recording_color="#ff4b4b", neutral_color="#6aa36f", icon_size="2x", key=stable_key)
    
    if chat_audio and chat_audio != st.session_state.last_processed_audio:
        st.session_state.last_processed_audio = chat_audio
        st.caption("Procesando audio...")
        with open("temp.wav", "wb") as f: f.write(chat_audio)
        
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
            st.warning("No se entendió el mensaje.")