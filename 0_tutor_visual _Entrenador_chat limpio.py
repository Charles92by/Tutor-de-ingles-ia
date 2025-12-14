import streamlit as st
import azure.cognitiveservices.speech as speechsdk
import google.generativeai as genai
from audio_recorder_streamlit import audio_recorder # Nueva librería para grabar en web
import os

# --- CLAVES SEGURAS (Desde Streamlit Secrets) ---
# Si da error en local, asegúrate de tener .streamlit/secrets.toml
try:
    AZURE_KEY = st.secrets["AZURE_KEY"]
    AZURE_REGION = st.secrets["AZURE_REGION"]
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ No se encontraron las claves secretas. Configúralas en Streamlit Cloud.")
    st.stop()

# Configuración de Gemini
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('models/gemini-2.5-flash')
except:
    st.warning("Error conectando con Gemini.")

st.set_page_config(page_title="British AI Tutor", page_icon="🇬🇧")

# --- FUNCIONES DE AUDIO (ADAPTADAS A LA NUBE) ---

def play_audio_response(text):
    """Genera audio con Azure y lo reproduce en el navegador"""
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
    speech_config.speech_synthesis_voice_name = "en-GB-RyanNeural"
    
    # IMPORTANTE: Configuramos salida nula para que no busque altavoces en el servidor
    audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=False)
    
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
    
    # Sintetizar a memoria
    result = synthesizer.speak_text_async(text).get()
    
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        # Reproducir en el navegador del usuario
        st.audio(result.audio_data, format="audio/wav")

def process_audio_file(file_path, reference_text=None):
    """Procesa un archivo de audio WAV con Azure"""
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
    speech_config.speech_recognition_language = "en-GB"
    
    # Leemos desde ARCHIVO, no desde micrófono
    audio_config = speechsdk.audio.AudioConfig(filename=file_path)
    
    if reference_text:
        # MODO EVALUACIÓN
        pronunciation_config = speechsdk.PronunciationAssessmentConfig(
            reference_text=reference_text,
            grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
            granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme
        )
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        pronunciation_config.apply_to(recognizer)
        return recognizer.recognize_once()
    else:
        # MODO CONVERSACIÓN (Solo transcripción)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        return recognizer.recognize_once()

# --- FUNCIONES DE GEMINI ---
def get_chat_response(history, user_input):
    prompt = f"""
    Eres un amigo británico charlando. 
    Historial: {history}
    Usuario: "{user_input}"
    Instrucciones:
    1. Si hay error gramatical grave, corrígelo amablemente.
    2. Responde para seguir la charla.
    3. IMPORTANTE: Responde SOLO texto plano. NO uses JSON ni llaves.
    """
    response = model.generate_content(prompt)
    return response.text

def get_pronunciation_tips(text, errors):
    prompt = f"Usuario dijo: '{text}'. Falló en: {errors}. Dame tips breves de pronunciación (IPA y posición lengua) en texto plano."
    response = model.generate_content(prompt)
    return response.text

# --- INTERFAZ ---
st.title("🇬🇧 British AI Tutor (Cloud Version)")

with st.sidebar:
    st.header("Modo de Estudio")
    modo = st.radio("Selecciona:", ["🎯 Entrenador de Pronunciación", "💬 Conversación Libre"])

# === MODO 1: ENTRENADOR ===
if modo == "🎯 Entrenador de Pronunciación":
    st.subheader("Modo Lectura")
    frase = st.selectbox("Elige frase:", ["I would like a bottle of water please.", "The weather in London is unpredictable."])
    st.info(f"Lee: **{frase}**")
    
    st.write("👇 Pulsa el micrófono para grabar:")
    # GRABADOR WEB
    audio_bytes = audio_recorder(text="", recording_color="#e8b62c", neutral_color="#6aa36f", icon_size="2x")
    
    if audio_bytes:
        # Guardar audio temporal
        with open("temp_reading.wav", "wb") as f:
            f.write(audio_bytes)
        
        with st.spinner("Analizando en la nube..."):
            res = process_audio_file("temp_reading.wav", reference_text=frase)
            
        if res and res.reason == speechsdk.ResultReason.RecognizedSpeech:
            assess_res = speechsdk.PronunciationAssessmentResult(res)
            score = assess_res.accuracy_score
            st.metric("Precisión", f"{score}/100")
            
            if score < 70: st.warning("Mejorable.")
            else: st.success("¡Good job!")
            
            errores = [w.word for w in assess_res.words if w.accuracy_score < 80 and w.error_type != "None"]
            if errores:
                st.write(f"⚠️ Errores: {', '.join(errores)}")
                feedback = get_pronunciation_tips(frase, errores)
                st.info(feedback)
                play_audio_response(feedback) # Audio en navegador
        elif res:
             st.error("No se entendió el audio.")

# === MODO 2: CONVERSACIÓN ===
else:
    st.subheader("Chat Británico")
    
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready to chat."}]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    st.divider()
    st.write("👇 Graba tu respuesta:")
    
    # GRABADOR WEB PARA CHAT
    # Usamos una key diferente para que no se mezcle con el otro grabador
    chat_audio = audio_recorder(text="", recording_color="#ff4b4b", neutral_color="#6aa36f", key="chat_recorder")
    
    if chat_audio:
        with open("temp_chat.wav", "wb") as f:
            f.write(chat_audio)
            
        with st.spinner("Escuchando..."):
            res = process_audio_file("temp_chat.wav")
            
        if res and res.reason == speechsdk.ResultReason.RecognizedSpeech:
            user_text = res.text
            
            # Evitar bucle si es el mismo audio de antes
            if st.session_state.messages[-1]["content"] != user_text:
                st.session_state.messages.append({"role": "user", "content": user_text})
                
                # Obtener respuesta IA
                historial = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                bot_reply = get_chat_response(historial, user_text)
                
                st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                st.rerun()

    # Reproducir el último mensaje del bot si es nuevo
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
        # Pequeño truco para que no lo repita infinitamente al recargar
        if "last_spoken" not in st.session_state or st.session_state["last_spoken"] != st.session_state.messages[-1]["content"]:
            play_audio_response(st.session_state.messages[-1]["content"])
            st.session_state["last_spoken"] = st.session_state.messages[-1]["content"]
