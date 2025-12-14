import streamlit as st
import google.generativeai as genai

st.title("🛠️ Diagnóstico de Reparación")

# 1. REVISAR SI LA CLAVE EXISTE
st.subheader("Paso 1: Verificando Clave Secreta")
try:
    mi_clave = st.secrets["GOOGLE_API_KEY"]
    # Mostramos solo las primeras 4 letras para ver si la lee bien
    st.success(f"✅ Clave detectada. Empieza por: '{mi_clave[:4]}...'")
    genai.configure(api_key=mi_clave)
except Exception as e:
    st.error(f"❌ ERROR: No se puede leer la clave 'GOOGLE_API_KEY' en Secrets. {e}")
    st.stop()

# 2. REVISAR VERSIÓN DE LA LIBRERÍA
st.subheader("Paso 2: Versión del Sistema")
try:
    version = genai.__version__
    st.info(f"Versión instalada de google-generativeai: {version}")
    if version < "0.8.3":
        st.warning("⚠️ ALERTA: La versión es antigua. Necesitas >=0.8.3")
    else:
        st.success("✅ Versión correcta.")
except:
    st.warning("No se pudo detectar la versión.")

# 3. LISTAR QUÉ MODELOS VE GOOGLE
st.subheader("Paso 3: Preguntando a Google '¿Qué modelos tienes?'")
try:
    st.write("Conectando con Google Cloud...")
    # Esto pide la lista oficial de modelos disponibles para TU clave
    modelos_disponibles = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            modelos_disponibles.append(m.name)
    
    if modelos_disponibles:
        st.success("✅ Conexión establecida. Modelos disponibles:")
        st.json(modelos_disponibles)
    else:
        st.error("❌ Conectó, pero la lista de modelos está vacía (¿Problema de permisos?).")

except Exception as e:
    st.error(f"❌ ERROR DE CONEXIÓN: {e}")

# 4. PRUEBA FINAL
st.subheader("Paso 4: Intento de generación")
try:
    # Probamos con el modelo más básico que exista en la lista
    modelo_a_usar = 'gemini-1.5-flash'
    st.write(f"Intentando generar con: {modelo_a_usar}...")
    model = genai.GenerativeModel(modelo_a_usar)
    response = model.generate_content("Hello, simply say 'OK'.")
    st.success(f"✅ ¡FUNCIONA! Respuesta: {response.text}")
except Exception as e:
    st.error(f"❌ Falló la generación: {e}")