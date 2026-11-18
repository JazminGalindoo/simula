"""
Motor de Simula: sortea hogares de la ENAHO y le pide a Gemini que responda como cada uno.

Funciones principales (las usa la app y ai/validar.py):
  - cargar_perfiles()                  → data/perfiles.parquet
  - muestrear(perfiles, n, segmento)   → N hogares sorteados ponderando por factor07
  - simular(pregunta, opciones, hogares) → respuestas + uso de tokens y costo
  - revisar_pregunta(pregunta, opciones) → problemas detectados y versión mejorada

Detalles:
  - Salida estructurada: Gemini devuelve JSON validado con Pydantic (no parseamos texto libre).
  - 25 hogares por llamada, para gastar pocas solicitudes del plan gratuito.
  - Reintentos con espera creciente si la API responde 429 (límite) o 5xx (servidor ocupado).
  - Caché en disco (.cache/): la misma consulta no se paga dos veces.
  - Cada llamada real se anota en data/registro_tokens.csv (tokens de entrada/salida y costo).
"""

import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field, create_model

from ai.prompts import (NO_ENTIENDO, SISTEMA_ENCUESTADOS, SISTEMA_REVISOR, describir_hogar,
                        prompt_encuestados, prompt_revisor)

RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env")

MODELO = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
POR_LLAMADA = 25          # encuestados por llamada
MAX_REINTENTOS = 6
CACHE = RAIZ / ".cache"
REGISTRO = RAIZ / "data" / "registro_tokens.csv"

# Precio pagado de gemini-3.5-flash-lite (USD por 1M tokens de texto, según ai.google.dev/pricing, nov-2026).
# En el plan gratuito pagamos S/ 0, pero mostramos el costo "si pagáramos" para el modelo de negocio.
# Los tokens de razonamiento ("thinking") se cobran como salida.
PRECIO_ENTRADA_USD = 0.30
PRECIO_SALIDA_USD = 2.50
TIPO_CAMBIO = 3.40        # soles por dólar (supuesto; actualizar con el del día)


# ---------------------------------------------------------------- datos

def cargar_perfiles() -> pd.DataFrame:
    return pd.read_parquet(RAIZ / "data" / "perfiles.parquet")


SEGMENTOS = {
    "Todo el Perú": lambda d: d,
    "Lima Metropolitana": lambda d: d[d["dominio"] == "Lima Metropolitana"],
    "Urbano": lambda d: d[d["area"] == "Urbano"],
    "Rural": lambda d: d[d["area"] == "Rural"],
}


def filtrar_segmento(perfiles: pd.DataFrame, segmento: str) -> pd.DataFrame:
    """Segmento = una clave de SEGMENTOS o el nombre de un dominio (p. ej. 'Sierra sur')."""
    if segmento in SEGMENTOS:
        return SEGMENTOS[segmento](perfiles)
    return perfiles[perfiles["dominio"] == segmento]


def muestrear(perfiles: pd.DataFrame, n: int, segmento: str = "Todo el Perú",
              semilla: int = 0) -> pd.DataFrame:
    """Sortea n hogares SIN reemplazo con probabilidad proporcional a factor07,
    así la muestra representa a los hogares del Perú (o del segmento)."""
    base = filtrar_segmento(perfiles, segmento)
    n = min(n, len(base))
    return base.sample(n=n, weights="factor07", random_state=semilla).reset_index(drop=True)


# ---------------------------------------------------------------- llamada a Gemini

_cliente = None


def cliente() -> genai.Client:
    """Crea el cliente una sola vez. La clave sale de .env o de los Secrets de Streamlit."""
    global _cliente
    if _cliente is None:
        clave = os.getenv("GEMINI_API_KEY")
        if not clave:
            raise RuntimeError("Falta GEMINI_API_KEY (en .env o en los Secrets de Streamlit).")
        # timeout en milisegundos: ninguna llamada espera más de 2 minutos
        _cliente = genai.Client(api_key=clave, http_options=types.HttpOptions(timeout=120_000))
    return _cliente


def costo_soles(tokens_entrada: int, tokens_salida: int) -> float:
    usd = (tokens_entrada * PRECIO_ENTRADA_USD + tokens_salida * PRECIO_SALIDA_USD) / 1_000_000
    return usd * TIPO_CAMBIO


def _anotar_tokens(tarea: str, entrada: int, salida: int, segundos: float):
    fila = pd.DataFrame([{
        "fecha": datetime.now().isoformat(timespec="seconds"), "modelo": MODELO, "tarea": tarea,
        "tokens_entrada": entrada, "tokens_salida": salida,
        "costo_soles": round(costo_soles(entrada, salida), 6), "segundos": round(segundos, 1)}])
    try:  # en Streamlit Cloud el disco puede ser de solo lectura: no es grave si falla
        fila.to_csv(REGISTRO, mode="a", header=not REGISTRO.exists(), index=False)
    except OSError:
        pass


def llamar_gemini(sistema: str, mensaje: str, esquema: type[BaseModel], tarea: str,
                  usar_cache: bool = True) -> tuple[BaseModel, dict]:
    """Una llamada con salida estructurada. Devuelve (objeto Pydantic, uso de tokens)."""
    llave = hashlib.sha256(f"{MODELO}|{sistema}|{mensaje}|{esquema.model_json_schema()}".encode()).hexdigest()
    archivo = CACHE / f"{llave}.json"
    if usar_cache and archivo.exists():
        guardado = json.loads(archivo.read_text(encoding="utf-8"))
        return esquema.model_validate(guardado["respuesta"]), {**guardado["uso"], "desde_cache": True}

    config = types.GenerateContentConfig(
        system_instruction=sistema,
        response_mime_type="application/json",
        response_schema=esquema,
        temperature=1.0,
    )
    for intento in range(MAX_REINTENTOS):
        inicio = time.time()
        try:
            r = cliente().models.generate_content(model=MODELO, contents=mensaje, config=config)
            break
        except errors.APIError as e:
            # 429 = límite de solicitudes; 500/503 = servidor ocupado → esperar y reintentar
            if e.code in (429, 500, 503) and intento < MAX_REINTENTOS - 1:
                espera = min(60, 5 * 2 ** intento)
                print(f"  Gemini respondió {e.code}; reintento {intento + 1} en {espera} s…")
                time.sleep(espera)
            else:
                raise
    segundos = time.time() - inicio

    u = r.usage_metadata
    entrada = u.prompt_token_count or 0
    salida = (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
    uso = {"tokens_entrada": entrada, "tokens_salida": salida,
           "costo_soles": costo_soles(entrada, salida), "segundos": segundos, "desde_cache": False}
    _anotar_tokens(tarea, entrada, salida, segundos)

    objeto = r.parsed if r.parsed is not None else esquema.model_validate_json(r.text)
    try:
        CACHE.mkdir(exist_ok=True)
        archivo.write_text(json.dumps({"respuesta": objeto.model_dump(), "uso": uso},
                                      ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return objeto, uso


# ---------------------------------------------------------------- encuestados sintéticos

def _esquema_lote(opciones: list[str]) -> type[BaseModel]:
    """Esquema Pydantic con las opciones como lista cerrada (enum): el LLM no puede inventar otra."""
    Opcion = Literal[tuple(opciones)]
    Respuesta = create_model(
        "Respuesta",
        id_perfil=(int, Field(description="Número del hogar")),
        respuesta=(Opcion, Field(description="Una de las opciones permitidas")),
        justificacion=(str, Field(description="Una frase corta en primera persona")),
    )
    return create_model("Lote", respuestas=(list[Respuesta], ...))


def simular(pregunta: str, opciones: list[str], hogares: pd.DataFrame,
            permitir_no_entiendo: bool = True, usar_cache: bool = True,
            tarea: str = "simulacion", al_avanzar=None) -> tuple[pd.DataFrame, dict]:
    """Hace que cada hogar responda la pregunta. Devuelve (tabla de respuestas, uso total).
    al_avanzar(hechos, total) es opcional: sirve para la barra de progreso de la app."""
    opciones = [o.strip() for o in opciones if o.strip()]
    if permitir_no_entiendo and NO_ENTIENDO not in opciones:
        opciones = opciones + [NO_ENTIENDO]
    esquema = _esquema_lote(opciones)

    filas, uso_total = [], {"tokens_entrada": 0, "tokens_salida": 0, "costo_soles": 0.0,
                            "llamadas": 0, "segundos": 0.0}
    for inicio in range(0, len(hogares), POR_LLAMADA):
        lote = hogares.iloc[inicio:inicio + POR_LLAMADA]
        fichas = {int(h["id_perfil"]): describir_hogar(h) for _, h in lote.iterrows()}
        resultado, uso = llamar_gemini(SISTEMA_ENCUESTADOS, prompt_encuestados(fichas, pregunta, opciones),
                                       esquema, tarea, usar_cache)
        for r in resultado.respuestas:
            if r.id_perfil in fichas:  # descartamos ids inventados
                filas.append({"id_perfil": r.id_perfil, "respuesta": r.respuesta,
                              "justificacion": r.justificacion})
        if not uso["desde_cache"]:
            uso_total["llamadas"] += 1
            for k in ("tokens_entrada", "tokens_salida", "costo_soles", "segundos"):
                uso_total[k] += uso[k]
        if al_avanzar:
            al_avanzar(min(inicio + POR_LLAMADA, len(hogares)), len(hogares))

    respuestas = pd.DataFrame(filas).drop_duplicates("id_perfil")
    tabla = hogares.merge(respuestas, on="id_perfil", how="inner")
    return tabla, uso_total


# ---------------------------------------------------------------- revisor de preguntas

class Problema(BaseModel):
    tipo: Literal["ambigua", "doble", "sesgada", "opciones", "tecnica"]
    explicacion: str = Field(description="Qué está mal, en una o dos frases")


class Revision(BaseModel):
    veredicto: Literal["Bien", "Mejorable", "Problemática"]
    problemas: list[Problema]
    pregunta_mejorada: str
    opciones_mejoradas: list[str]


def revisar_pregunta(pregunta: str, opciones: list[str], usar_cache: bool = True) -> tuple[Revision, dict]:
    return llamar_gemini(SISTEMA_REVISOR, prompt_revisor(pregunta, opciones), Revision,
                         "revisor", usar_cache)


# ---------------------------------------------------------------- prueba rápida

if __name__ == "__main__":
    # python -m ai.simulador  → simula 20 hogares de todo el Perú
    perfiles = cargar_perfiles()
    hogares = muestrear(perfiles, 20, semilla=1)
    tabla, uso = simular("¿Pagarías S/ 20 al mes por internet fijo en tu casa?",
                         ["Sí", "No", "No sé"], hogares)
    print(tabla[["departamento", "area", "quintil_gasto", "respuesta", "justificacion"]].to_string())
    print("\n% de respuestas:\n", tabla["respuesta"].value_counts(normalize=True).mul(100).round(1))
    print("\nUso:", {k: round(v, 4) if isinstance(v, float) else v for k, v in uso.items()})
