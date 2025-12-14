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

# --- 3. CONFIGURACIÓN GEMINI (INTENTO DE CONEXIÓN ROBUSTA) ---
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    
    # CAMBIO: Usamos 'gemini-1.5-flash' sin el prefijo 'models/' que a veces da error en la nube
    # Si este falla, probaremos 'gemini-pro'
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"❌ Error al configurar Gemini: {e}")

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
            # Modo Evaluación
            pronunciation_config = speechsdk.PronunciationAssessmentConfig(
                reference_text=reference_text,
                grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
                granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme
            )
            recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
            pronunciation_config.apply_to(recognizer)
            return recognizer.recognize_once()
        else:
            # Modo Chat
            recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
            return recognizer.recognize_once()
    except Exception as e:
        st.error(f"Error Azure: {e}")
        return None

# --- 5. CEREBRO IA (CON DETECTOR DE ERRORES) ---
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
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        # AQUÍ ESTÁ EL CAMBIO: Te mostrará el error real en pantalla
        st.error(f"⚠️ ERROR GEMINI DETALLADO: {e}") 
        return "System Error (Check logs above)"

def get_pronunciation_tips(text, errors):
    prompt = f"User said: '{text}'. Errors: {', '.join(errors)}. Give brief pronunciation tips (IPA)."
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"⚠️ ERROR GEMINI DETALLADO: {e}")
        return "Check pronunciation."

# --- 6. INTERFAZ ---
st.title("🇬🇧 British AI Tutor")

with st.sidebar:
    st.header("Configuración")
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