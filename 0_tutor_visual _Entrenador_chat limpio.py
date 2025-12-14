import streamlit as st
import azure.cognitiveservices.speech as speechsdk
import google.generativeai as genai

# --- CLAVES ---
AZURE_KEY = st.secrets["AZURE_KEY"]
AZURE_REGION = st.secrets["AZURE_REGION"]
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]

# Configuración
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('models/gemini-2.5-flash')
except:
    pass

st.set_page_config(page_title="British AI Tutor", page_icon="🇬🇧")

# --- FUNCIONES DE AZURE ---
def text_to_speech(text):
    """El bot habla"""
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
    speech_config.speech_synthesis_voice_name = "en-GB-RyanNeural"
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
    synthesizer.speak_text_async(text)

def recognize_speech_free():
    """Escucha libre (Sin texto de referencia)"""
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
    speech_config.speech_recognition_language = "en-GB"
    audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    
    result = recognizer.recognize_once()
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        return result.text
    return None

def assess_pronunciation_fixed(reference_text):
    """Evaluación estricta de lectura"""
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
    speech_config.speech_recognition_language = "en-GB"
    audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
    
    pronunciation_config = speechsdk.PronunciationAssessmentConfig(
        reference_text=reference_text,
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme
    )
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    pronunciation_config.apply_to(recognizer)
    result = recognizer.recognize_once()
    
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        return speechsdk.PronunciationAssessmentResult(result)
    return None

# --- FUNCIONES DE GEMINI ---
def get_chat_response(history, user_input):
    """Cerebro conversacional"""
    prompt = f"""
    Eres un amigo británico charlando. 
    Historial de chat: {history}
    Usuario dice: "{user_input}"
    
    Tus instrucciones:
    1. Si el usuario cometió un error gramatical grave, corrígelo amablemente primero.
    2. Luego responde a la pregunta o comentario para seguir la charla.
    3. IMPORTANTE: Responde SOLO con texto plano. NO uses llaves {{}} ni formato JSON.
    4. Sé natural y breve.
    """
    response = model.generate_content(prompt)
    return response.text

def get_pronunciation_tips(text, errors):
    """Cerebro fonético"""
    prompt = f"Usuario dijo: '{text}'. Falló en: {errors}. Dame tips breves de pronunciación (IPA y posición lengua)."
    response = model.generate_content(prompt)
    return response.text

# --- INTERFAZ ---
st.title("🇬🇧 British AI Tutor")

with st.sidebar:
    st.header("Modo de Estudio")
    modo = st.radio("Selecciona:", ["🎯 Entrenador de Pronunciación", "💬 Conversación Libre"])

# === MODO 1: ENTRENADOR (El que ya tenías) ===
if modo == "🎯 Entrenador de Pronunciación":
    st.subheader("Modo Lectura: Perfecciona tus fonemas")
    frase = st.selectbox("Elige frase:", ["I would like a bottle of water please.", "The weather in London is unpredictable."])
    st.info(f"Lee: **{frase}**")
    
    if st.button("🎙️ Grabar Lectura"):
        with st.spinner("Escuchando..."):
            res = assess_pronunciation_fixed(frase)
            
        if res:
            score = res.accuracy_score
            st.metric("Precisión", f"{score}/100")
            if score < 70: st.warning("Intenta mejorar la articulación.")
            else: st.success("¡Muy bien!")
            
            # Errores
            errores = [w.word for w in res.words if w.accuracy_score < 80 and w.error_type != "None"]
            if errores:
                st.write(f"⚠️ Fallos en: {', '.join(errores)}")
                feedback = get_pronunciation_tips(frase, errores)
                st.info(feedback)
                text_to_speech(feedback)

# === MODO 2: CONVERSACIÓN (LO NUEVO) ===
else:
    st.subheader("Modo Conversación: Practica tu fluidez")
    st.markdown("Habla de lo que quieras. El bot te responderá.")

    # Inicializar historial de chat
    if "messages" not in st.session_state:
        st.session_state.messages = []
        # Mensaje inicial del bot
        st.session_state.messages.append({"role": "assistant", "content": "Hello! I'm ready to chat. How are you today?"})

    # Mostrar historial visual
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # Botón para hablar en el chat
    if st.button("🎙️ Hablar al Bot", type="primary"):
        with st.spinner("Escuchando..."):
            user_text = recognize_speech_free()
        
        if user_text:
            # 1. Guardar lo que dijiste
            st.session_state.messages.append({"role": "user", "content": user_text})
            st.rerun() # Recargar para mostrar tu mensaje
            
    # Lógica de respuesta (se ejecuta tras el rerun)
    if st.session_state.messages[-1]["role"] == "user":
        with st.spinner("El bot está pensando..."):
            # Historial para contexto
            historial_txt = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
            
            # Obtener respuesta de Gemini
            respuesta_bot = get_chat_response(historial_txt, st.session_state.messages[-1]["content"])
            
            # Guardar y mostrar
            st.session_state.messages.append({"role": "assistant", "content": respuesta_bot})
            
            # Hablar
            text_to_speech(respuesta_bot)
            st.rerun()