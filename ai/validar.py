"""
Validación de Simula: ¿cuánto se equivoca la IA respondiendo como hogares peruanos?

1. Sortea 400 hogares de data/perfiles.parquet con probabilidad proporcional a factor07
   (así la muestra representa a los hogares del Perú y cada hogar "pesa" lo mismo).
2. Para cada una de las 5 preguntas de la ENAHO, el LLM responde Sí/No como cada hogar,
   SIN ver la respuesta real (las columnas real_* no entran en la ficha del hogar).
3. Compara contra la respuesta real de esos mismos hogares:
   - % real vs % sintético y error absoluto en puntos porcentuales (pp)
   - por pregunta, a nivel nacional, por dominio, por área y por departamento
   - accuracy a nivel de hogar (% de hogares donde la IA acierta)
4. Guarda data/validacion_resultados.csv, data/validacion_por_segmento.csv,
   data/validacion_respuestas.csv y docs/validacion.md.

Se puede volver a correr sin gastar: las llamadas quedan en caché (.cache/).
Uso:  python -m ai.validar
"""

import pandas as pd

from ai.prompts import PREGUNTAS_VALIDACION
from ai.simulador import MODELO, RAIZ, cargar_perfiles, muestrear, simular

N_HOGARES = 400
SEMILLA = 2026
NOMBRES = {"celular": "celular", "internet_fijo": "internet fijo", "tv_cable": "TV cable",
           "agua_red": "agua de red pública", "gas": "cocina a gas"}


def pct_ponderado(df, columna):
    d = df[df[columna].notna()]
    return 100 * (d[columna] * d["factor07"]).sum() / d["factor07"].sum()


def enumerar(nombres):
    """['a', 'b', 'c'] → 'a, b y c'."""
    nombres = list(nombres)
    if not nombres:
        return "ninguna pregunta"
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


def resumir(grupo):
    """% real, % sintético y error para un grupo de respuestas (de una pregunta)."""
    real = 100 * grupo["real"].mean()
    sintetico = 100 * grupo["sintetico"].mean()
    return pd.Series({"n": len(grupo), "pct_real": real, "pct_sintetico": sintetico,
                      "error_pp": abs(sintetico - real),
                      "accuracy": 100 * (grupo["real"] == grupo["sintetico"]).mean()})


def main():
    perfiles = cargar_perfiles()
    # Muestra proporcional a factor07 → dentro de ella, un promedio simple ya está "ponderado".
    hogares = muestrear(perfiles, N_HOGARES, semilla=SEMILLA)

    # ---------- 1. El LLM responde las 5 preguntas ----------
    filas, usos = [], []
    for p in PREGUNTAS_VALIDACION:
        base = hogares[hogares[p["columna"]].notna()]  # gas: excluye hogares que no cocinan
        print(f"Simulando '{p['clave']}' con {len(base)} hogares…")
        tabla, uso = simular(p["pregunta"], ["Sí", "No"], base, permitir_no_entiendo=False,
                             tarea=f"validacion{N_HOGARES}_{p['clave']}")
        usos.append(uso)
        tabla["pregunta"] = p["clave"]
        tabla["texto_pregunta"] = p["pregunta"]
        tabla["real"] = tabla[p["columna"]].astype(int)
        tabla["sintetico"] = (tabla["respuesta"] == "Sí").astype(int)
        filas.append(tabla)

    respuestas = pd.concat(filas, ignore_index=True)
    columnas_perfil = ["id_perfil", "departamento_cod", "departamento", "dominio", "area",
                       "quintil_gasto", "pobreza"]
    respuestas = respuestas[columnas_perfil + ["pregunta", "texto_pregunta", "real", "sintetico",
                                               "justificacion"]]

    # ---------- 2. Resultados por pregunta (nivel nacional) ----------
    resultados = respuestas.groupby("pregunta", sort=False).apply(resumir, include_groups=False).reset_index()
    # Referencia: % real en los 3,000 perfiles ponderados por factor07 (≈ toda la ENAHO)
    resultados["pct_real_enaho"] = [pct_ponderado(perfiles, p["columna"]) for p in PREGUNTAS_VALIDACION]
    resultados["texto_pregunta"] = [p["pregunta"] for p in PREGUNTAS_VALIDACION]
    resultados["variable_enaho"] = [p["variable_enaho"] for p in PREGUNTAS_VALIDACION]
    # Costo real por pregunta (tokens de cada llamada; la caché guarda el costo original)
    for k in ("llamadas", "tokens_entrada", "tokens_salida", "costo_soles"):
        resultados[k] = [u[k] for u in usos]

    # ---------- 3. Error por segmento: nacional, área, dominio y departamento ----------
    cortes = {"Nacional": None, "Área": "area", "Dominio": "dominio", "Departamento": "departamento"}
    partes = []
    for tipo, col in cortes.items():
        claves = ["pregunta"] if col is None else [col, "pregunta"]
        t = respuestas.groupby(claves, sort=False).apply(resumir, include_groups=False).reset_index()
        t["segmento"] = "Todo el Perú" if col is None else t[col]
        t["tipo"] = tipo
        if col == "departamento":
            t = t.merge(respuestas[["departamento", "departamento_cod"]].drop_duplicates(), on="departamento")
        partes.append(t.drop(columns=[col] if col else []))
    por_segmento = pd.concat(partes, ignore_index=True)
    # Fila "promedio" por segmento: el margen de error empírico que usa la app
    promedio = (por_segmento.groupby(["tipo", "segmento"], sort=False)
                .agg(n=("n", "max"), error_pp=("error_pp", "mean"), accuracy=("accuracy", "mean"),
                     departamento_cod=("departamento_cod", "first"))
                .reset_index())
    promedio["pregunta"] = "promedio"
    por_segmento = pd.concat([por_segmento, promedio], ignore_index=True)
    por_segmento = por_segmento[["tipo", "segmento", "departamento_cod", "pregunta", "n",
                                 "pct_real", "pct_sintetico", "error_pp", "accuracy"]]

    # ---------- 4. Guardar ----------
    datos = RAIZ / "data"
    redondear = lambda d: d.round(2)
    redondear(resultados).assign(costo_soles=resultados["costo_soles"].round(4)).to_csv(datos / "validacion_resultados.csv", index=False)
    redondear(por_segmento).to_csv(datos / "validacion_por_segmento.csv", index=False)
    respuestas.to_csv(datos / "validacion_respuestas.csv", index=False)
    costo = {"llamadas": int(resultados["llamadas"].sum()), "tokens_entrada": int(resultados["tokens_entrada"].sum()),
             "tokens_salida": int(resultados["tokens_salida"].sum()), "costo_soles": resultados["costo_soles"].sum()}
    escribir_reporte(resultados, por_segmento, costo)

    print("\n", resultados[["pregunta", "pct_real", "pct_sintetico", "error_pp", "accuracy"]].round(1).to_string())
    print("\nCosto total:", costo, "| llamadas que salieron de caché:", sum(u["desde_cache"] for u in usos))


def escribir_reporte(resultados, por_segmento, uso):
    """docs/validacion.md con tablas y conclusiones calculadas a partir de los números."""
    prom = por_segmento[por_segmento["pregunta"] == "promedio"]
    nac = prom[prom["tipo"] == "Nacional"].iloc[0]
    area = prom[prom["tipo"] == "Área"].set_index("segmento")
    dom = prom[prom["tipo"] == "Dominio"].sort_values("error_pp", ascending=False)
    dom_confiable = dom[dom["n"] >= 10]  # para las conclusiones, solo dominios con 10+ hogares
    deps = prom[(prom["tipo"] == "Departamento") & (prom["n"] >= 10)].sort_values("error_pp", ascending=False)
    pocos = int((prom[prom["tipo"] == "Departamento"]["n"] < 10).sum())
    # Sesgo: preguntas donde la IA se pasa (o se queda corta) por más de 5 pp
    dif = resultados.assign(dif=resultados["pct_sintetico"] - resultados["pct_real"],
                            nombre=resultados["pregunta"].map(NOMBRES))
    sobre, sub = enumerar(dif[dif["dif"] > 5]["nombre"]), enumerar(dif[dif["dif"] < -5]["nombre"])
    peor, mejor = resultados.loc[resultados["error_pp"].idxmax()], resultados.loc[resultados["error_pp"].idxmin()]

    tabla_preg = "\n".join(
        f"| {r.texto_pregunta} | `{r.variable_enaho}` | {r.n:.0f} | {r.pct_real_enaho:.1f}% | {r.pct_real:.1f}% | "
        f"{r.pct_sintetico:.1f}% | **{r.error_pp:.1f}** | {r.accuracy:.0f}% |"
        for r in resultados.itertuples())
    tabla_seg = lambda t: "\n".join(
        f"| {r.segmento} | {r.n:.0f} | **{r.error_pp:.1f}** | {r.accuracy:.0f}% |" for r in t.itertuples())

    texto = f"""# Validación: ¿cuánto se equivoca la IA en el Perú?

Generado por `ai/validar.py`. Modelo: `{MODELO}`. Fuente: ENAHO 2024 (INEI).

## Método

- Se sortearon **{N_HOGARES} hogares** de `data/perfiles.parquet` con probabilidad proporcional a `factor07`
  (semilla {SEMILLA}), así la muestra representa a los hogares del Perú.
- Para cada hogar, el LLM recibió solo su ficha (lugar, área, tamaño, edad/sexo/educación del jefe(a),
  gasto per cápita, quintil y pobreza) y respondió Sí/No a 5 preguntas. **Nunca vio la respuesta real.**
- Se compara el % de "Sí" sintético con el % real **en los mismos hogares**. Error = |sintético − real|,
  en puntos porcentuales (pp). Accuracy = % de hogares donde la IA acierta.
- La pregunta de gas excluye a los hogares que no cocinan.

## Resultados por pregunta (nacional)

| Pregunta | Variable | n | % real ENAHO (3,000 perfiles, ponderado) | % real muestra | % sintético | Error (pp) | Accuracy |
|---|---|---|---|---|---|---|---|
{tabla_preg}

**Error medio nacional: {nac.error_pp:.1f} pp** · accuracy media a nivel de hogar: {nac.accuracy:.0f}%.

## Error por área

| Área | n hogares | Error medio (pp) | Accuracy |
|---|---|---|---|
{tabla_seg(area.reset_index())}

## Error por dominio geográfico

| Dominio | n hogares | Error medio (pp) | Accuracy |
|---|---|---|---|
{tabla_seg(dom)}

## Departamentos con mayor error (con al menos 10 hogares en la muestra)

| Departamento | n hogares | Error medio (pp) | Accuracy |
|---|---|---|---|
{tabla_seg(deps.head(8))}

## Conclusiones

- En promedio, el % sintético se aleja **{nac.error_pp:.1f} pp** del real a nivel nacional.
- La pregunta más difícil para la IA fue **"{peor.texto_pregunta}"** ({peor.error_pp:.1f} pp: real {peor.pct_real:.0f}%
  vs sintético {peor.pct_sintetico:.0f}%); la más fácil, **"{mejor.texto_pregunta}"** ({mejor.error_pp:.1f} pp).
- Por área: urbano {area.loc['Urbano', 'error_pp']:.1f} pp vs rural {area.loc['Rural', 'error_pp']:.1f} pp.
- Entre los dominios con 10+ hogares, el de mayor error es **{dom_confiable.iloc[0].segmento}**
  ({dom_confiable.iloc[0].error_pp:.1f} pp) y el de menor error, **{dom_confiable.iloc[-1].segmento}**
  ({dom_confiable.iloc[-1].error_pp:.1f} pp).
- Sesgo (diferencias de más de 5 pp): la IA **sobreestima** {sobre} y **subestima** {sub}.

## Limitaciones

- {N_HOGARES} hogares: {pocos} de los 25 departamentos tienen menos de 10 casos, así que su error es ruidoso.
  El mapa de la app muestra el n de cada departamento.
- Son preguntas de **tenencia de servicios**, que la ficha del hogar ayuda a predecir. Preguntas de opinión,
  intención de compra o precios pueden tener errores distintos; este número es una referencia, no una garantía.
- Un solo modelo (`{MODELO}`) y una sola corrida (temperatura 1.0).

Costo de la validación (tokens reales de cada llamada): {uso['llamadas']} llamadas, {uso['tokens_entrada']:,} tokens
de entrada y {uso['tokens_salida']:,} de salida ≈ S/ {uso['costo_soles']:.2f} a precio pagado (S/ 0 en el plan gratuito).
"""
    (RAIZ / "docs" / "validacion.md").write_text(texto, encoding="utf-8")


if __name__ == "__main__":
    main()
