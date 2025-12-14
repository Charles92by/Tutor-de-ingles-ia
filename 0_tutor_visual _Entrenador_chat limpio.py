import streamlit as st
import azure.cognitiveservices.speech as speechsdk
import google.generativeai as genai
from audio_recorder_streamlit import audio_recorder
import os

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="British AI Tutor", page_icon="🇬🇧")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready to chat."}]
if "last_processed_audio" not in st.session_state:
    st.session_state.last_processed_audio = b"" # Memoria para no repetir
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

# --- 3. CONEXIÓN GOOGLE (Memoria Caché) ---
if "working_model_name" not in st.session_state:
    possible_models = ["models/gemini-flash-latest", "gemini-1.5-flash", "gemini-pro"]
    found = None
    for m in possible_models:
        try:
            genai.configure(api_key=GOOGLE_API_KEY)
            genai.GenerativeModel(m).generate_content("Hi")
            found = m
            break
        except: continue
    
    if found: st.session_state.working_model_name = found
    else: st.error("❌ Error Google API."); st.stop()

active_model = genai.GenerativeModel(st.session_state.working_model_name)

# --- 4. FUNCIONES AUDIO ---
def generar_audio_resp(text):
    try:
        if "ERROR" in text: return
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
        # Configuración de paciencia (3 segundos de silencio)
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
    You are a British English tutor. User said: "{user_input}".
    History: {history}
    1. Contextualize if transcription is weird.
    2. Correct grammar gently.
    3. Reply naturally.
    """
    try: return active_model.generate_content(prompt).text
    except Exception as e: return f"Error IA: {e}"

def get_pronunciation_tips(text, errors):
    try: return active_model.generate_content(f"Tips for pronouncing: {errors} in British English.").text
    except: return "Check pronunciation."

# --- 6. INTERFAZ ---
st.title("🇬🇧 British AI Tutor")

with st.sidebar:
    st.divider()
    modo = st.radio("Modo:", ["🎯 Entrenador", "💬 Conversación"])
    st.divider()
    if st.button("🔄 Reiniciar Conversación"):
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready to chat."}]
        st.session_state.last_processed_audio = b""
        st.session_state.manual_reset_counter += 1 # Solo cambiamos la clave si el usuario quiere
        st.rerun()

# === LÓGICA DE GRABACIÓN ESTABLE ===
# Usamos una clave que SOLO cambia si tú pulsas "Reiniciar", no automáticamente.
stable_key = f"recorder_{modo}_{st.session_state.manual_reset_counter}"

if modo == "🎯 Entrenador":
    st.subheader("Entrenador de Lectura")
    frase = st.selectbox("Frase:", ["I would like a bottle of water please.", "The weather in London is unpredictable."])
    st.info(f"📖 Lee: **{frase}**")
    
    # 1. Grabador (ESTABLE)
    audio_bytes = audio_recorder(text="", recording_color="#e8b62c", neutral_color="#6aa36f", icon_size="2x", key=stable_key)
    
    # 2. Procesamiento (Solo si hay audio NUEVO)
    if audio_bytes and audio_bytes != st.session_state.last_processed_audio:
        st.session_state.last_processed_audio = audio_bytes # Marcamos como procesado
        
        st.audio(audio_bytes, format="audio/wav") # Feedback visual
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

else: # MODO CHAT
    st.subheader("Chat Británico")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            
    st.write("---")
    st.write("👇 **Pulsa para hablar:**")
    
    # 1. Grabador (ESTABLE)
    chat_audio = audio_recorder(text="", recording_color="#ff4b4b", neutral_color="#6aa36f", icon_size="2x", key=stable_key)
    
    # 2. Procesamiento (Solo si hay audio NUEVO)
    if chat_audio and chat_audio != st.session_state.last_processed_audio:
        st.session_state.last_processed_audio = chat_audio # Marcamos como procesado
        
        st.caption("Procesando audio...")
        with open("temp.wav", "wb") as f: f.write(chat_audio)
        
        res = process_audio_file("temp.wav")
        
        if res and res.reason == speechsdk.ResultReason.RecognizedSpeech:
            user_text = res.text
            st.session_state.messages.append({"role": "user", "content": user_text})
            
            # Generar respuesta
            historial = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
            bot_reply = get_chat_response(historial, user_text)
            st.session_state.messages.append({"role": "assistant", "content": bot_reply})
            
            # Hablar respuesta
            generar_audio_resp(bot_reply)
            
            st.rerun() # Recargamos para mostrar los mensajes nuevos
        else:
            st.warning("No se entendió el mensaje. Inténtalo de nuevo.")