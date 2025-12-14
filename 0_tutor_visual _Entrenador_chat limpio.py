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
    st.error("❌ ERROR: Faltan las claves en Secrets.")
    st.stop()

# --- 3. CONEXIÓN INTELIGENTE (VERSIÓN EUROPA) ---
if "working_model_name" not in st.session_state:
    st.sidebar.text("🔄 Conectando...")
    possible_models = [
        "models/gemini-flash-latest", # Prioridad Europa
        "gemini-1.5-flash",
        "models/gemini-1.5-flash",
        "gemini-pro"
    ]
    found_model = None
    for model_name in possible_models:
        try:
            genai.configure(api_key=GOOGLE_API_KEY)
            test_model = genai.GenerativeModel(model_name)
            test_model.generate_content("Hi")
            found_model = model_name
            break
        except:
            continue
    
    if found_model:
        st.session_state.working_model_name = found_model
        st.sidebar.success(f"✅ {found_model}")
    else:
        st.error("❌ Error de conexión con Google. Revisa tu API Key.")
        st.stop()

try:
    active_model = genai.GenerativeModel(st.session_state.working_model_name)
except:
    st.session_state.clear()
    st.rerun()

# --- 4. FUNCIONES AUDIO MEJORADAS 🎧 ---
def generar_audio_resp(text):
    try:
        if "ERROR" in text or "429" in text: return
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
        
        # --- MEJORA: AUMENTAR PACIENCIA DE AZURE ---
        # Le damos 3000ms (3 segundos) de silencio antes de cortar la frase.
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "3000")
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "5000")
        
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

# --- 5. CEREBRO IA (MÁS COMPRENSIVO) ---
def get_chat_response(history, user_input):
    prompt = f"""
    You are a friendly British English tutor.
    The user is learning, so their input might have phonetic errors or broken grammar.
    
    Current Conversation:
    {history}
    
    User just said (Transcribed audio): "{user_input}"
    
    Your Task:
    1. Try to guess the context even if the transcription is weird.
    2. If the user made a grammar mistake, correct it gently inside your reply.
    3. Reply naturally to keep the chat going.
    4. Keep it short and simple. PLAIN TEXT ONLY.
    """
    try:
        response = active_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"ERROR IA: {str(e)}"

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
        guardar_modelo = st.session_state.get("working_model_name", None)
        st.session_state.clear()
        if guardar_modelo: st.session_state.working_model_name = guardar_modelo
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm ready to chat."}]
        st.session_state.last_spoken_audio = ""
        st.session_state.recorder_key = 0
        st.rerun()

if modo == "🎯 Entrenador":
    st.subheader("Entrenador de Lectura")
    frase = st.selectbox("Frase:", ["I would like a bottle of water please.", "The weather in London is unpredictable."])
    st.info(f"📖 Lee: **{frase}**")
    
    key_tr = f"tr_{st.session_state.recorder_key}"
    audio_tr = audio_recorder(text="", recording_color="#e8b62c", neutral_color="#6aa36f", icon_size="2x", key=key_tr)
    
    if audio_tr:
        # Check de audio
        st.audio(audio_tr, format="audio/wav")
        
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
        else:
            st.warning("⚠️ No se entendió el audio. Intenta hablar más alto y claro.")
        
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
        # Reproducir lo que grabaste para verificar
        st.caption("🔊 Tu grabación:")
        st.audio(audio_ch, format="audio/wav")
        
        with open("temp_chat.wav", "wb") as f: f.write(audio_ch)
        with st.spinner("Escuchando..."):
            res = process_audio_file("temp_chat.wav")
            
        if res and res.reason == speechsdk.ResultReason.RecognizedSpeech:
            user_text = res.text
            st.success(f"🗣️ Oído: '{user_text}'") # Feedback visual de lo que entendió
            
            st.session_state.messages.append({"role": "user", "content": user_text})
            historial = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
            bot_reply = get_chat_response(historial, user_text)
            st.session_state.messages.append({"role": "assistant", "content": bot_reply})
            
            st.session_state.recorder_key += 1
            st.rerun()
        else:
            st.warning("😓 No pude entenderte. Inténtalo de nuevo.")
            st.session_state.recorder_key += 1
            st.rerun()

    if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
        last_msg = st.session_state.messages[-1]["content"]
        if st.session_state.last_spoken_audio != last_msg:
            st.session_state.last_spoken_audio = last_msg
            generar_audio_resp(last_msg)