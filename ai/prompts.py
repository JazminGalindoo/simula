"""
Prompts de Simula. Todo el texto que le enviamos al LLM vive aquí, para poder leerlo y ajustarlo
sin tocar la lógica de ai/simulador.py.

- describir_hogar(): convierte una fila de data/perfiles.parquet en una ficha en lenguaje natural.
- prompt_encuestados(): pide al LLM responder como un lote de hogares (25 por llamada).
- prompt_revisor(): pide al LLM revisar una pregunta de encuesta antes de simular.
- PREGUNTAS_VALIDACION: las 5 preguntas que comparamos contra la ENAHO 2024.
"""

# Opción extra que pueden elegir los encuestados sintéticos en la pestaña "Prueba tu pregunta"
NO_ENTIENDO = "No entiendo la pregunta"

# Las 5 preguntas de validación. "columna" es la respuesta real en data/perfiles.parquet.
PREGUNTAS_VALIDACION = [
    {"clave": "celular", "columna": "real_celular", "variable_enaho": "p1142",
     "pregunta": "¿En tu hogar alguien tiene teléfono celular?"},
    {"clave": "internet_fijo", "columna": "real_internet_fijo", "variable_enaho": "p114b1",
     "pregunta": "¿Tu hogar tiene internet fijo (wifi o cable)?"},
    {"clave": "tv_cable", "columna": "real_tv_cable", "variable_enaho": "p1143",
     "pregunta": "¿Tu hogar tiene TV por cable o satelital?"},
    {"clave": "agua_red", "columna": "real_agua_red", "variable_enaho": "p110",
     "pregunta": "¿El agua de tu hogar viene principalmente de la red pública (caño dentro de la casa o del edificio)?"},
    {"clave": "gas", "columna": "real_gas", "variable_enaho": "p113a",
     "pregunta": "¿En tu hogar cocinan principalmente con gas (balón o gas natural)?"},
]


def describir_hogar(h) -> str:
    """Ficha corta del hogar. NO incluye ninguna columna real_* (el LLM no debe ver la respuesta)."""
    lugar = "Lima Metropolitana" if h["dominio"] == "Lima Metropolitana" else (
        f"{h['departamento']} ({h['dominio'].lower()}), zona {h['area'].lower()}")
    edad = f"{int(h['jefe_edad'])} años" if h["jefe_edad"] == h["jefe_edad"] else "edad sin dato"
    jefe = "jefa de hogar" if h["jefe_sexo"] == "Mujer" else "jefe de hogar"
    return (f"Vive en {lugar}. Hogar de {h['miembros']} persona(s). "
            f"{jefe.capitalize()}: {edad}, educación {h['jefe_educacion'].lower()}. "
            f"Gasto por persona: S/ {h['gasto_pc_mensual']:.0f} al mes "
            f"(quintil {h['quintil_gasto']} de 5, donde 1 es el 20% con menos gasto). "
            f"Situación: {h['pobreza'].lower()}.")


SISTEMA_ENCUESTADOS = """Eres un simulador de encuestados para estudios de mercado en el Perú.
Vas a recibir fichas de hogares REALES de la Encuesta Nacional de Hogares (ENAHO) del INEI.
Para cada hogar, responde la pregunta como lo haría la persona jefa de ese hogar:
- Ponte en su lugar: su región, si es urbano o rural, su gasto, su educación y su edad.
- Sé realista, no optimista: en el Perú hay mucha desigualdad entre Lima, el resto urbano y lo rural.
  No respondas lo que "debería" ser, sino lo que es más probable para ESE hogar.
- Cada hogar responde por separado; no todos tienen que responder lo mismo.
- La justificación va en primera persona, en español peruano sencillo, en una sola frase corta (máx. 20 palabras).
- Elige SOLO una de las opciones permitidas, copiada exactamente."""


def prompt_encuestados(fichas: dict, pregunta: str, opciones: list[str]) -> str:
    """fichas = {id_perfil: texto}. Devuelve el mensaje de usuario para un lote."""
    lista = "\n".join(f"- Hogar {i}: {texto}" for i, texto in fichas.items())
    extra = ""
    if NO_ENTIENDO in opciones:
        extra = (f'\nSi a esa persona la pregunta le parecería confusa, con palabras que no usa, '
                 f'o no sabría qué responder por cómo está escrita, elige "{NO_ENTIENDO}".')
    return (f"PREGUNTA: {pregunta}\n"
            f"OPCIONES PERMITIDAS: {' | '.join(opciones)}{extra}\n\n"
            f"HOGARES ({len(fichas)}):\n{lista}\n\n"
            f"Devuelve una respuesta por cada hogar, usando su número como id_perfil.")


SISTEMA_REVISOR = """Eres metodólogo/a de encuestas con experiencia en campo en el Perú (INEI, consultoras, tesis).
Revisas preguntas ANTES de que se apliquen y detectas los problemas típicos de cuestionarios:
- ambigua: se puede entender de más de una forma o no fija el periodo/unidad.
- doble: pregunta dos cosas a la vez.
- sesgada: induce la respuesta o usa palabras cargadas.
- opciones: opciones que se superponen, que faltan (p. ej. "No sé") o que no son exhaustivas.
- tecnica: palabras técnicas, en inglés o difíciles para hogares de bajos ingresos o rurales.
Solo reporta problemas reales; si la pregunta está bien, dilo y devuelve la lista vacía.
Propón una versión mejorada (pregunta y opciones) en español peruano claro y neutral.
Responde en español."""


def prompt_revisor(pregunta: str, opciones: list[str]) -> str:
    return f"PREGUNTA: {pregunta}\nOPCIONES: {' | '.join(opciones)}"
