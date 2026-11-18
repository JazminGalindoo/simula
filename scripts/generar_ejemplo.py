"""
Genera data/ejemplo_precargado.json: una simulación REAL guardada, para que la app pueda
mostrar resultados aunque la API de Gemini falle durante el demo.

Incluye: revisión de la pregunta B, y la prueba A/B con los mismos 100 hogares de todo el Perú.
Uso:  python -m scripts.generar_ejemplo
"""

import json

from ai.simulador import MODELO, RAIZ, cargar_perfiles, muestrear, revisar_pregunta, simular

EJEMPLO = {
    "pregunta_a": "¿Pagarías S/ 20 al mes por tener internet fijo (wifi) en tu casa?",
    "pregunta_b": "¿Estaría dispuesto a contratar un plan de banda ancha fija FTTH de 20 soles mensuales?",
    "opciones": ["Sí", "No", "No sé"],
    "segmento": "Todo el Perú",
    "n": 100,
    "semilla": 7,
}


def main():
    perfiles = cargar_perfiles()
    hogares = muestrear(perfiles, EJEMPLO["n"], EJEMPLO["segmento"], semilla=EJEMPLO["semilla"])

    revision, _ = revisar_pregunta(EJEMPLO["pregunta_b"], EJEMPLO["opciones"], usar_cache=False)
    tabla_a, uso_a = simular(EJEMPLO["pregunta_a"], EJEMPLO["opciones"], hogares, tarea="ejemplo", usar_cache=False)
    tabla_b, uso_b = simular(EJEMPLO["pregunta_b"], EJEMPLO["opciones"], hogares, tarea="ejemplo", usar_cache=False)

    salida = {**EJEMPLO, "modelo": MODELO,
              "revision": revision.model_dump(),
              "respuestas_a": tabla_a.to_dict(orient="records"),
              "respuestas_b": tabla_b.to_dict(orient="records"),
              "uso_a": uso_a, "uso_b": uso_b}
    archivo = RAIZ / "data" / "ejemplo_precargado.json"
    archivo.write_text(json.dumps(salida, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    for nombre, t in [("A", tabla_a), ("B", tabla_b)]:
        print(nombre, t["respuesta"].value_counts(normalize=True).mul(100).round(1).to_dict())
    print("Guardado en", archivo.relative_to(RAIZ))


if __name__ == "__main__":
    main()
