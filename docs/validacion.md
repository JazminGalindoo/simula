# Validación: ¿cuánto se equivoca la IA en el Perú?

Generado por `ai/validar.py`. Modelo: `gemini-3.5-flash-lite`. Fuente: ENAHO 2024 (INEI).

## Método

- Se sortearon **400 hogares** de `data/perfiles.parquet` con probabilidad proporcional a `factor07`
  (semilla 2026), así la muestra representa a los hogares del Perú.
- Para cada hogar, el LLM recibió solo su ficha (lugar, área, tamaño, edad/sexo/educación del jefe(a),
  gasto per cápita, quintil y pobreza) y respondió Sí/No a 5 preguntas. **Nunca vio la respuesta real.**
- Se compara el % de "Sí" sintético con el % real **en los mismos hogares**. Error = |sintético − real|,
  en puntos porcentuales (pp). Accuracy = % de hogares donde la IA acierta.
- La pregunta de gas excluye a los hogares que no cocinan.

## Resultados por pregunta (nacional)

| Pregunta | Variable | n | % real ENAHO (3,000 perfiles, ponderado) | % real muestra | % sintético | Error (pp) | Accuracy |
|---|---|---|---|---|---|---|---|
| ¿En tu hogar alguien tiene teléfono celular? | `p1142` | 400 | 94.1% | 92.2% | 93.8% | **1.5** | 93% |
| ¿Tu hogar tiene internet fijo (wifi o cable)? | `p114b1` | 400 | 20.4% | 19.5% | 50.5% | **31.0** | 64% |
| ¿Tu hogar tiene TV por cable o satelital? | `p1143` | 400 | 24.7% | 23.0% | 48.0% | **25.0** | 61% |
| ¿El agua de tu hogar viene principalmente de la red pública (caño dentro de la casa o del edificio)? | `p110` | 400 | 84.0% | 83.5% | 68.5% | **15.0** | 67% |
| ¿En tu hogar cocinan principalmente con gas (balón o gas natural)? | `p113a` | 391 | 69.5% | 67.0% | 77.7% | **10.7** | 79% |

**Error medio nacional: 16.6 pp** · accuracy media a nivel de hogar: 73%.

## Error por área

| Área | n hogares | Error medio (pp) | Accuracy |
|---|---|---|---|
| Rural | 122 | **15.7** | 73% |
| Urbano | 278 | **22.1** | 73% |

## Error por dominio geográfico

| Dominio | n hogares | Error medio (pp) | Accuracy |
|---|---|---|---|
| Costa centro | 29 | **26.9** | 69% |
| Sierra norte | 35 | **20.7** | 72% |
| Costa sur | 9 | **20.0** | 80% |
| Lima Metropolitana | 60 | **18.7** | 77% |
| Sierra sur | 62 | **17.7** | 73% |
| Sierra centro | 70 | **17.5** | 77% |
| Costa norte | 61 | **16.1** | 67% |
| Selva | 74 | **16.0** | 69% |

## Departamentos con mayor error (con al menos 10 hogares en la muestra)

| Departamento | n hogares | Error medio (pp) | Accuracy |
|---|---|---|---|
| Cusco | 28 | **24.3** | 74% |
| Huancavelica | 10 | **24.0** | 68% |
| Piura | 18 | **21.5** | 61% |
| Lima | 64 | **20.7** | 75% |
| Arequipa | 14 | **20.0** | 71% |
| Ayacucho | 14 | **20.0** | 77% |
| Áncash | 17 | **20.0** | 73% |
| Junín | 34 | **19.5** | 71% |

## Conclusiones

- En promedio, el % sintético se aleja **16.6 pp** del real a nivel nacional.
- La pregunta más difícil para la IA fue **"¿Tu hogar tiene internet fijo (wifi o cable)?"** (31.0 pp: real 20%
  vs sintético 50%); la más fácil, **"¿En tu hogar alguien tiene teléfono celular?"** (1.5 pp).
- Por área: urbano 22.1 pp vs rural 15.7 pp.
- Entre los dominios con 10+ hogares, el de mayor error es **Costa centro**
  (26.9 pp) y el de menor error, **Selva**
  (16.0 pp).
- Sesgo (diferencias de más de 5 pp): la IA **sobreestima** internet fijo, TV cable y cocina a gas y **subestima** agua de red pública.

## Limitaciones

- 400 hogares: 9 de los 25 departamentos tienen menos de 10 casos, así que su error es ruidoso.
  El mapa de la app muestra el n de cada departamento.
- Son preguntas de **tenencia de servicios**, que la ficha del hogar ayuda a predecir. Preguntas de opinión,
  intención de compra o precios pueden tener errores distintos; este número es una referencia, no una garantía.
- Un solo modelo (`gemini-3.5-flash-lite`) y una sola corrida (temperatura 1.0).

Costo de la validación (tokens reales de cada llamada): 80 llamadas, 187,067 tokens
de entrada y 93,112 de salida ≈ S/ 0.98 a precio pagado (S/ 0 en el plan gratuito).
