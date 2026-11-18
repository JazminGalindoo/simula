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
| ¿En tu hogar alguien tiene teléfono celular? | `p1142` | 400 | 95.4% | 96.5% | 96.0% | **0.5** | 95% |
| ¿Tu hogar tiene internet fijo (wifi o cable)? | `p114b1` | 400 | 27.8% | 27.0% | 58.5% | **31.5** | 62% |
| ¿Tu hogar tiene TV por cable o satelital? | `p1143` | 400 | 30.0% | 30.2% | 55.2% | **25.0** | 60% |
| ¿El agua de tu hogar viene principalmente de la red pública (caño dentro de la casa o del edificio)? | `p110` | 400 | 87.3% | 87.8% | 77.5% | **10.2** | 78% |
| ¿En tu hogar cocinan principalmente con gas (balón o gas natural)? | `p113a` | 395 | 76.4% | 77.5% | 84.3% | **6.8** | 87% |

**Error medio nacional: 14.8 pp** · accuracy media a nivel de hogar: 76%.

## Error por área

| Área | n hogares | Error medio (pp) | Accuracy |
|---|---|---|---|
| Rural | 83 | **18.6** | 72% |
| Urbano | 317 | **18.1** | 77% |

## Error por dominio geográfico

| Dominio | n hogares | Error medio (pp) | Accuracy |
|---|---|---|---|
| Sierra norte | 23 | **18.3** | 75% |
| Costa norte | 55 | **18.2** | 73% |
| Sierra centro | 62 | **18.1** | 75% |
| Selva | 54 | **17.5** | 68% |
| Costa centro | 24 | **16.7** | 78% |
| Sierra sur | 53 | **15.8** | 75% |
| Costa sur | 9 | **13.3** | 82% |
| Lima Metropolitana | 120 | **12.7** | 81% |

## Departamentos con mayor error (con al menos 10 hogares en la muestra)

| Departamento | n hogares | Error medio (pp) | Accuracy |
|---|---|---|---|
| Ucayali | 11 | **30.9** | 62% |
| Cusco | 12 | **26.7** | 73% |
| San Martín | 12 | **26.7** | 73% |
| Lambayeque | 17 | **24.7** | 73% |
| Junín | 24 | **20.8** | 72% |
| Huánuco | 14 | **20.0** | 77% |
| Áncash | 17 | **20.0** | 78% |
| Cajamarca | 19 | **18.9** | 75% |

## Conclusiones

- En promedio, el % sintético se aleja **14.8 pp** del real a nivel nacional.
- La pregunta más difícil para la IA fue **"¿Tu hogar tiene internet fijo (wifi o cable)?"** (31.5 pp: real 27%
  vs sintético 58%); la más fácil, **"¿En tu hogar alguien tiene teléfono celular?"** (0.5 pp).
- Por área: urbano 18.1 pp vs rural 18.6 pp.
- Entre los dominios con 10+ hogares, el de mayor error es **Sierra norte**
  (18.3 pp) y el de menor error, **Lima Metropolitana**
  (12.7 pp).
- Sesgo (diferencias de más de 5 pp): la IA **sobreestima** internet fijo, TV cable y cocina a gas y **subestima** agua de red pública.

## Limitaciones

- 400 hogares: 10 de los 25 departamentos tienen menos de 10 casos, así que su error es ruidoso.
  El mapa de la app muestra el n de cada departamento.
- Son preguntas de **tenencia de servicios**, que la ficha del hogar ayuda a predecir. Preguntas de opinión,
  intención de compra o precios pueden tener errores distintos; este número es una referencia, no una garantía.
- Un solo modelo (`gemini-3.5-flash-lite`) y una sola corrida (temperatura 1.0).

Costo de la validación (tokens reales de cada llamada): 80 llamadas, 185,669 tokens
de entrada y 93,459 de salida ≈ S/ 0.98 a precio pagado (S/ 0 en el plan gratuito).
