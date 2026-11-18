# Validación: ¿cuánto se equivoca la IA en el Perú?

Generado por `ai/validar.py`. Modelo: `gemini-3.5-flash-lite`. Fuente: ENAHO 2024 (INEI).

## Método

- Se sortearon **200 hogares** de `data/perfiles.parquet` con probabilidad proporcional a `factor07`
  (semilla 2026), así la muestra representa a los hogares del Perú.
- Para cada hogar, el LLM recibió solo su ficha (lugar, área, tamaño, edad/sexo/educación del jefe(a),
  gasto per cápita, quintil y pobreza) y respondió Sí/No a 5 preguntas. **Nunca vio la respuesta real.**
- Se compara el % de "Sí" sintético con el % real **en los mismos hogares**. Error = |sintético − real|,
  en puntos porcentuales (pp). Accuracy = % de hogares donde la IA acierta.
- La pregunta de gas excluye a los hogares que no cocinan.

## Resultados por pregunta (nacional)

| Pregunta | Variable | n | % real ENAHO (3,000 perfiles, ponderado) | % real muestra | % sintético | Error (pp) | Accuracy |
|---|---|---|---|---|---|---|---|
| ¿En tu hogar alguien tiene teléfono celular? | `p1142` | 200 | 94.1% | 92.5% | 93.5% | **1.0** | 93% |
| ¿Tu hogar tiene internet fijo (wifi o cable)? | `p114b1` | 200 | 20.4% | 17.5% | 53.0% | **35.5** | 60% |
| ¿Tu hogar tiene TV por cable o satelital? | `p1143` | 200 | 24.7% | 24.0% | 49.0% | **25.0** | 60% |
| ¿El agua de tu hogar viene principalmente de la red pública (caño dentro de la casa o del edificio)? | `p110` | 200 | 84.0% | 86.5% | 71.0% | **15.5** | 66% |
| ¿En tu hogar cocinan principalmente con gas (balón o gas natural)? | `p113a` | 196 | 69.5% | 70.4% | 79.1% | **8.7** | 80% |

**Error medio nacional: 17.1 pp** · accuracy media a nivel de hogar: 72%.

## Error por área

| Área | n hogares | Error medio (pp) | Accuracy |
|---|---|---|---|
| Rural | 54 | **19.6** | 72% |
| Urbano | 146 | **21.7** | 72% |

## Error por dominio geográfico

| Dominio | n hogares | Error medio (pp) | Accuracy |
|---|---|---|---|
| Costa centro | 13 | **29.4** | 71% |
| Lima Metropolitana | 35 | **23.4** | 75% |
| Sierra norte | 18 | **22.4** | 73% |
| Sierra sur | 36 | **22.2** | 73% |
| Sierra centro | 29 | **15.9** | 76% |
| Costa norte | 35 | **13.7** | 66% |
| Costa sur | 3 | **13.3** | 87% |
| Selva | 31 | **13.0** | 67% |

## Departamentos con mayor error (con al menos 8 hogares en la muestra)

| Departamento | n hogares | Error medio (pp) | Accuracy |
|---|---|---|---|
| Lima | 36 | **25.6** | 73% |
| Puno | 8 | **25.0** | 70% |
| Cusco | 18 | **24.4** | 73% |
| Lambayeque | 12 | **21.7** | 65% |
| La Libertad | 12 | **20.0** | 70% |
| Junín | 15 | **18.7** | 71% |
| San Martín | 10 | **18.0** | 66% |
| Cajamarca | 18 | **17.8** | 71% |

## Conclusiones

- En promedio, el % sintético se aleja **17.1 pp** del real a nivel nacional.
- La pregunta más difícil para la IA fue **"¿Tu hogar tiene internet fijo (wifi o cable)?"** (35.5 pp: real 18%
  vs sintético 53%); la más fácil, **"¿En tu hogar alguien tiene teléfono celular?"** (1.0 pp).
- Por área: urbano 21.7 pp vs rural 19.6 pp.
- Entre los dominios con 10+ hogares, el de mayor error es **Costa centro**
  (29.4 pp) y el de menor error, **Selva**
  (13.0 pp).
- Sesgo: la IA tiende a **sobreestimar** los servicios que dependen de ingresos e infraestructura
  (internet fijo, TV cable) y a subestimar el agua de red pública. Imagina un Perú con más internet y menos agua.

## Limitaciones

- 200 hogares: a nivel de departamento hay pocos casos (muchos con menos de 10), así que ese error es ruidoso.
  El mapa de la app muestra el n de cada departamento.
- Son preguntas de **tenencia de servicios**, que la ficha del hogar ayuda a predecir. Preguntas de opinión,
  intención de compra o precios pueden tener errores distintos; este número es una referencia, no una garantía.
- Un solo modelo (`gemini-3.5-flash-lite`) y una sola corrida (temperatura 1.0).

Costo de la validación (según `data/registro_tokens.csv`): 40 llamadas, 93,307 tokens
de entrada y 46,493 de salida ≈ S/ 0.49 a precio pagado (S/ 0 en el plan gratuito).
