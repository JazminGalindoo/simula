# Imagen de Simula para Render (también sirve para cualquier hosting con Docker).
FROM python:3.12-slim

# Usuario sin privilegios
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR $HOME/app

# Primero las librerías (se cachean entre despliegues), luego el código y los datos
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY --chown=user . .

# Render indica el puerto en la variable PORT; en local usamos 8501.
# GEMINI_API_KEY y GEMINI_MODEL llegan como variables de entorno del servicio (nunca en la imagen).
EXPOSE 8501
CMD streamlit run app/streamlit_app.py --server.port=${PORT:-8501} --server.address=0.0.0.0
