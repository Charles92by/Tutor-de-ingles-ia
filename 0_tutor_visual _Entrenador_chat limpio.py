import streamlit as st
import azure.cognitiveservices.speech as speechsdk
import google.generativeai as genai
from audio_recorder_streamlit import audio_recorder
import os

# --- 1. CONFIGURACIÓN INICIAL Y ESTADO ---
st.set_page_config(page_title="British AI Tutor", page_icon="🇬🇧")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready to chat."}]
if "last_spoken_audio" not in st.session_state:
    st.session_state.last_spoken_audio = ""
if "recorder_key" not in st.session_state:
    st.session_state.recorder_key = 0

# --- 2. GESTIÓN DE CLAVES ---
try:
    AZURE_KEY = st.secrets["AZURE_KEY"]
    AZURE_REGION = st.secrets["AZURE_REGION"]
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ Faltan las claves en 'Secrets'.")
    st.stop()

# --- 3. CONFIGURACIÓN GEMINI (VUELTA AL 2.5) ---
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    # VOLVEMOS AL MODELO QUE SABEMOS QUE TE FUNCIONA
    model = genai.GenerativeModel('models/gemini-2.5-flash')
except Exception as e:
    st.error(f"Error conectando con Gemini: {e}")

# --- 4. FUNCIONES DE AUDIO ---

def generar_audio_resp(text):
    """Genera audio y lo reproduce"""
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_synthesis_voice_name = "en-GB-RyanNeural"
        audio_config = speechsdk.audio.AudioOutputConfig(filename="output_ghost.wav")
        
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        result = synthesizer.speak_text_async(text).get()
        
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            st.audio(result.audio_data, format="audio/wav")
            
    except Exception as e:
        st.error(f"Error audio: {e}")

def process_audio_file(file_path, reference_text=None):
    """Procesa el audio grabado"""
    try:
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
    except Exception as e:
        st.error(f"Error Azure: {e}")
        return None

# --- 5. CEREBRO IA ---
def get_chat_response(history, user_input):
    prompt = f"""
    Eres un tutor de inglés británico.
    Historial: {history}
    Usuario: "{user_input}"
    Instrucciones:
    1. Corrige errores gramaticales graves brevemente.
    2. Responde para seguir la charla.
    3. SOLO texto plano.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"❌ Error Gemini: {e}")
        return "I can't think right now."

def get_pronunciation_tips(text, errors):
    prompt = f"Usuario dijo: '{text}'. Falló en: {', '.join(errors)}. Dame consejo breve (texto plano)."
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"❌ Error Gemini: {e}")
        return "Check pronunciation."

# --- 6. INTERFAZ GRÁFICA ---

st.title("🇬🇧 British AI Tutor")

with st.sidebar:
    st.header("Configuración")
    modo = st.radio("Modo:", ["🎯 Entrenador", "💬 Conversación"])
    
    st.divider()
    if st.button("🔄 Reiniciar Todo"):
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready to chat."}]
        st.session_state.last_spoken_audio = ""
        st.session_state.recorder_key += 1
        st.rerun()

# === MODO 1: ENTRENADOR ===
if modo == "🎯 Entrenador":
    st.subheader("Entrenador de Lectura")
    frase = st.selectbox("Frase:", ["I would like a bottle of water please.", "The weather in London is unpredictable."])
    st.info(f"📖 Lee: **{frase}**")
    
    key_entrenador = f"trainer_{st.session_state.recorder_key}"
    audio_bytes_tr = audio_recorder(text="", recording_color="#e8b62c", neutral_color="#6aa36f", icon_size="2x", key=key_entrenador)
    
    if audio_bytes_tr:
        with open("temp_reading.wav", "wb") as f:
            f.write(audio_bytes_tr)
        
        with st.spinner("Analizando..."):
            res = process_audio_file("temp_reading.wav", reference_text=frase)
            
        if res and res.reason == speechsdk.ResultReason.RecognizedSpeech:
            assess_res = speechsdk.PronunciationAssessmentResult(res)
            score = assess_res.accuracy_score
            st.metric("Nota", f"{score}/100")
            
            errores = [w.word for w in assess_res.words if w.accuracy_score < 80 and w.error_type != "None"]
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

# === MODO 2: CONVERSACIÓN ===
else:
    st.subheader("Chat Británico")
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    st.write("---")
    st.write("👇 **Pulsa para hablar:**")
    
    key_chat = f"chat_{st.session_state.recorder_key}"
    chat_audio = audio_recorder(text="", recording_color="#ff4b4b", neutral_color="#6aa36f", icon_size="2x", key=key_chat)
    
    if chat_audio:
        with open("temp_chat.wav", "wb") as f:
            f.write(chat_audio)
            
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