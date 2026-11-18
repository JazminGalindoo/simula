# Simula

> Hacemos el piloto de tu encuesta con encuestados sintéticos que responden como hogares peruanos reales, y te decimos cuánto se equivoca la IA porque la medimos contra la ENAHO.

🚧 **En construcción.** Proyecto final del curso Data Science con Python (Universidad del Pacífico, 2026-II).

**Founder:** Jazmín Galindo

## Estructura

```
app/streamlit_app.py      # la app (Streamlit)
ai/                       # prompts, simulador y validación contra la ENAHO
data/                     # archivos pequeños derivados, sin identificadores
docs/                     # capturas, arquitectura, research y validación
notebooks/                # exploración de la ENAHO 2024
scripts/                  # preparación de perfiles de hogares
```

## Cómo correrlo en local

```bash
python -m venv .venv
.venv\Scripts\activate         # en Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # y pega tu GEMINI_API_KEY
streamlit run app/streamlit_app.py
```

Sin clave de Gemini la app igual abre: muestra la validación y el ejemplo precargado.

## Licencia

MIT
