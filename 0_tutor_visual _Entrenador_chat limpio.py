import streamlit as st
import azure.cognitiveservices.speech as speechsdk
import google.generativeai as genai
from audio_recorder_streamlit import audio_recorder
import os

# --- 1. GESTIÓN DE CLAVES SEGURAS ---
try:
    AZURE_KEY = st.secrets["AZURE_KEY"]
    AZURE_REGION = st.secrets["AZURE_REGION"]
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ No se encontraron las claves. Configura los 'Secrets' en Streamlit Cloud.")
    st.stop()

# --- 2. CONFIGURACIÓN GEMINI ---
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('models/gemini-2.5-flash')
except Exception as e:
    st.warning(f"Error conectando con Gemini: {e}")

st.set_page_config(page_title="British AI Tutor", page_icon="🇬🇧")

# --- 3. FUNCIONES DE AUDIO (CORREGIDAS PARA LA NUBE) ---

def generar_audio_resp(text):
    """
    Genera audio con Azure y lo reproduce en el navegador.
    """
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_synthesis_voice_name = "en-GB-RyanNeural"
        
        # EL TRUCO: Enviamos a un archivo "fantasma" para no buscar altavoces
        audio_config = speechsdk.audio.AudioOutputConfig(filename="output_ghost.wav")
        
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        
        # Sintetizar
        result = synthesizer.speak_text_async(text).get()
        
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            # Reproducir los bytes de memoria directamente en el navegador
            st.audio(result.audio_data, format="audio/wav")
            
    except Exception as e:
        st.error(f"Error generando audio: {e}")

def process_audio_file(file_path, reference_text=None):
    """Procesa el archivo de audio grabado"""
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
    speech_config.speech_recognition_language = "en-GB"
    
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
        # MODO CHAT
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        return recognizer.recognize_once()

# --- 4. CEREBRO IA (GEMINI) ---

def get_chat_response(history, user_input):
    prompt = f"""
    Eres un tutor de inglés británico charlando amigablemente. 
    Historial: {history}
    Usuario dice: "{user_input}"
    
    Instrucciones:
    1. Si hay errores gramaticales graves, corrígelos brevemente.
    2. Responde a la pregunta.
    3. IMPORTANTE: Responde SOLO texto plano. NO uses JSON.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "I am having trouble thinking right now."

def get_pronunciation_tips(text, errors):
    prompt = f"""
    Usuario dijo: '{text}'. 
    Falló en: {', '.join(errors)}. 
    Dame un consejo breve sobre pronunciación (IPA y lengua) en texto plano.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "Check your pronunciation."

# --- 5. INTERFAZ GRÁFICA ---

st.title("🇬🇧 British AI Tutor")
st.markdown("Tu entrenador de acento personal.")

with st.sidebar:
    st.header("Modo de Estudio")
    modo = st.radio("Selecciona:", ["🎯 Entrenador de Pronunciación", "💬 Conversación Libre"])

# === MODO 1: ENTRENADOR ===
if modo == "🎯 Entrenador de Pronunciación":
    st.subheader("Entrenador de Lectura")
    frase = st.selectbox("Elige frase:", [
        "I would like a bottle of water please.",
        "The weather in London is unpredictable.",
        "Can you tell me the way to the station?",
        "It's better to be safe than sorry."
    ])
    st.info(f"📖 Lee en voz alta: **{frase}**")
    
    st.write("👇 Pulsa el micro para grabar:")
    audio_bytes = audio_recorder(text="", recording_color="#e8b62c", neutral_color="#6aa36f", icon_size="2x", key="recorder_trainer")
    
    if audio_bytes:
        with open("temp_reading.wav", "wb") as f:
            f.write(audio_bytes)
        
        with st.spinner("Analizando..."):
            res = process_audio_file("temp_reading.wav", reference_text=frase)
            
        if res and res.reason == speechsdk.ResultReason.RecognizedSpeech:
            assess_res = speechsdk.PronunciationAssessmentResult(res)
            score = assess_res.accuracy_score
            st.metric("Puntuación", f"{score}/100")
            
            if score < 70: st.warning("Sigue practicando.")
            else: st.success("¡Excelente!")
            
            errores = [w.word for w in assess_res.words if w.accuracy_score < 80 and w.error_type != "None"]
            if errores:
                st.write(f"⚠️ Errores: {', '.join(errores)}")
                feedback = get_pronunciation_tips(frase, errores)
                st.info(feedback)
                generar_audio_resp(feedback) # <--- AQUÍ USAMOS EL NUEVO NOMBRE
        else:
             st.error("No te escuché bien.")

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
    
    chat_audio = audio_recorder(text="", recording_color="#ff4b4b", neutral_color="#6aa36f", icon_size="2x", key="recorder_chat")
    
    if chat_audio:
        with open("temp_chat.wav", "wb") as f:
            f.write(chat_audio)
            
        with st.spinner("Escuchando..."):
            res = process_audio_file("temp_chat.wav")
            
        if res and res.reason == speechsdk.ResultReason.RecognizedSpeech:
            user_text = res.text
            
            last_user_msg = st.session_state.messages[-1]["content"] if st.session_state.messages else ""
            
            if user_text != last_user_msg:
                st.session_state.messages.append({"role": "user", "content": user_text})
                
                historial = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                bot_reply = get_chat_response(historial, user_text)
                
                st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                st.rerun()

    # Reproducir audio del último mensaje (Lógica final)
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
        last_msg = st.session_state.messages[-1]["content"]
        
        # Solo habla si el mensaje es nuevo (no ha sido hablado antes)
        if "last_spoken_audio" not in st.session_state or st.session_state["last_spoken_audio"] != last_msg:
            generar_audio_resp(last_msg) # <--- AQUÍ USAMOS EL NUEVO NOMBRE
            st.session_state["last_spoken_audio"] = last_msg