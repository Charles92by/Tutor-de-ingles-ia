import streamlit as st
import azure.cognitiveservices.speech as speechsdk
import google.generativeai as genai
from audio_recorder_streamlit import audio_recorder
import os

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="British AI Tutor", page_icon="🇬🇧")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready to chat."}]
if "last_spoken_audio" not in st.session_state:
    st.session_state.last_spoken_audio = ""
if "recorder_key" not in st.session_state:
    st.session_state.recorder_key = 0

# --- 2. CLAVES ---
try:
    AZURE_KEY = st.secrets["AZURE_KEY"]
    AZURE_REGION = st.secrets["AZURE_REGION"]
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ ERROR CRÍTICO: No se encuentran las claves en Secrets.")
    st.stop()

# --- 3. CONEXIÓN GEMINI "AUTO-REPARABLE" 🛠️ ---
# Esta sección prueba modelos uno por uno hasta encontrar el que funciona en la nube
active_model = None
connection_status = st.sidebar.empty()

possible_models = [
    'models/gemini-2.5-flash',  # El más nuevo (tu favorito)
    'gemini-2.5-flash',         # Variación de nombre
    'models/gemini-1.5-flash',  # El estándar actual
    'gemini-1.5-flash',         # Variación estándar
    'gemini-pro'                # El clásico (si todo falla)
]

genai.configure(api_key=GOOGLE_API_KEY)

# Probamos conectar
for model_name in possible_models:
    try:
        temp_model = genai.GenerativeModel(model_name)
        # Hacemos una prueba silenciosa para ver si responde
        temp_model.generate_content("Test") 
        active_model = temp_model
        connection_status.success(f"✅ Conectado a: {model_name}")
        break # Si funciona, dejamos de buscar
    except:
        continue # Si falla, probamos el siguiente

if not active_model:
    st.error("❌ ERROR FATAL: Ningún modelo de Gemini respondió. Revisa tu API KEY o actualiza requirements.txt.")
    st.stop()

# --- 4. FUNCIONES AUDIO ---
def generar_audio_resp(text):
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_synthesis_voice_name = "en-GB-RyanNeural"
        audio_config = speechsdk.audio.AudioOutputConfig(filename="output_ghost.wav")
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        result = synthesizer.speak_text_async(text).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            st.audio(result.audio_data, format="audio/wav")
    except Exception as e:
        st.error(f"Error Audio: {e}")

def process_audio_file(file_path, reference_text=None):
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_recognition_language = "en-GB"
        audio_config = speechsdk.audio.AudioConfig(filename=file_path)
        
        if reference_text:
            pronunciation_config = speechsdk.PronunciationAssessmentConfig(
                reference_text=reference_text,
                grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
                granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme
            )
            recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
            pronunciation_config.apply_to(recognizer)
            return recognizer.recognize_once()
        else:
            recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
            return recognizer.recognize_once()
    except Exception as e:
        st.error(f"Error Azure: {e}")
        return None

# --- 5. CEREBRO IA ---
def get_chat_response(history, user_input):
    prompt = f"""
    You are a British English tutor.
    Chat History: {history}
    User says: "{user_input}"
    Task:
    1. Briefly correct major grammar mistakes.
    2. Reply to continue conversation.
    3. PLAIN TEXT ONLY. NO JSON.
    """
    try:
        # Usamos el modelo activo que encontramos antes
        response = active_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error IA: {e}"

def get_pronunciation_tips(text, errors):
    prompt = f"User said: '{text}'. Errors: {', '.join(errors)}. Give brief pronunciation tips (IPA)."
    try:
        response = active_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return "Check pronunciation."

# --- 6. INTERFAZ ---
st.title("🇬🇧 British AI Tutor")

with st.sidebar:
    st.divider()
    modo = st.radio("Modo:", ["🎯 Entrenador", "💬 Conversación"])
    st.divider()
    if st.button("🔄 Reiniciar"):
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready to chat."}]
        st.session_state.last_spoken_audio = ""
        st.session_state.recorder_key += 1
        st.rerun()

if modo == "🎯 Entrenador":
    st.subheader("Entrenador de Lectura")
    frase = st.selectbox("Frase:", ["I would like a bottle of water please.", "The weather in London is unpredictable."])
    st.info(f"📖 Lee: **{frase}**")
    
    key_tr = f"tr_{st.session_state.recorder_key}"
    audio_tr = audio_recorder(text="", recording_color="#e8b62c", neutral_color="#6aa36f", icon_size="2x", key=key_tr)
    
    if audio_tr:
        with open("temp_read.wav", "wb") as f: f.write(audio_tr)
        with st.spinner("Analizando..."):
            res = process_audio_file("temp_read.wav", reference_text=frase)
            
        if res and res.reason == speechsdk.ResultReason.RecognizedSpeech:
            assess = speechsdk.PronunciationAssessmentResult(res)
            st.metric("Nota", f"{assess.accuracy_score}/100")
            errores = [w.word for w in assess.words if w.accuracy_score < 80 and w.error_type != "None"]
            
            if errores:
                st.write(f"⚠️ Errores: {', '.join(errores)}")
                feedback = get_pronunciation_tips(frase, errores)
                st.info(feedback)
                generar_audio_resp(feedback)
            else:
                st.success("Perfect!")
                generar_audio_resp("Excellent pronunciation!")
        
        st.session_state.recorder_key += 1
        st.rerun()

else:
    st.subheader("Chat Británico")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            
    st.write("---")
    st.write("👇 **Pulsa para hablar:**")
    key_chat = f"ch_{st.session_state.recorder_key}"
    audio_ch = audio_recorder(text="", recording_color="#ff4b4b", neutral_color="#6aa36f", icon_size="2x", key=key_chat)
    
    if audio_ch:
        with open("temp_chat.wav", "wb") as f: f.write(audio_ch)
        with st.spinner("Escuchando..."):
            res = process_audio_file("temp_chat.wav")
            
        if res and res.reason == speechsdk.ResultReason.RecognizedSpeech:
            user_text = res.text
            st.session_state.messages.append({"role": "user", "content": user_text})
            
            historial = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
            bot_reply = get_chat_response(historial, user_text)
            st.session_state.messages.append({"role": "assistant", "content": bot_reply})
            
            st.session_state.recorder_key += 1
            st.rerun()

    if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
        last_msg = st.session_state.messages[-1]["content"]
        if st.session_state.last_spoken_audio != last_msg:
            st.session_state.last_spoken_audio = last_msg
            generar_audio_resp(last_msg)