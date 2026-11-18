"""
Simula — app de Streamlit (punto de entrada para Streamlit Community Cloud).

Tres pestañas:
  1. ¿Cuánto se equivoca la IA en el Perú?  → resultados precalculados de ai/validar.py (sin llamar al LLM)
  2. Prueba tu pregunta                     → revisor + simulación en vivo (una pregunta o A/B)
  3. Cómo funciona                          → diagrama, modelo, costo real y limitaciones

Correr en local:  streamlit run app/streamlit_app.py
"""

import json
import os
import random
import sys
from pathlib import Path

import altair as alt
import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))  # para poder importar ai/

st.set_page_config(page_title="Simula", page_icon="📋", layout="wide")

# En Streamlit Cloud la clave viene de Secrets; en local, de .env (lo lee ai/simulador.py)
try:
    for clave in ("GEMINI_API_KEY", "GEMINI_MODEL"):
        if clave in st.secrets:
            os.environ[clave] = st.secrets[clave]
except Exception:  # no hay secrets.toml en local: no pasa nada
    pass

from ai.prompts import NO_ENTIENDO, PREGUNTAS_VALIDACION  # noqa: E402
from ai.simulador import (MODELO, POR_LLAMADA, PRECIO_ENTRADA_USD, PRECIO_SALIDA_USD,  # noqa: E402
                          TIPO_CAMBIO, cargar_perfiles, muestrear, revisar_pregunta, simular)

# ---------------------------------------------------------------- estilo

AZUL, NARANJA, GRIS = "#2a78d6", "#eb6834", "#8f8e89"      # Real / Sintético / "No entiendo"
CATEGORICOS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TINTA, TINTA_2 = "#0b0b0b", "#52514e"
NOMBRES_CORTOS = {"celular": "Celular", "internet_fijo": "Internet fijo", "tv_cable": "TV cable",
                  "agua_red": "Agua de red pública", "gas": "Cocina con gas"}

st.markdown("""
<style>
  .block-container {padding-top: 2rem; max-width: 1200px;}
  h1 {font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0;}
  .subtitulo {color: #52514e; font-size: 1.05rem; margin-top: .25rem; margin-bottom: 1.25rem;}
  .cita {font-size: 0.97rem; line-height: 1.45;}
  .cita-perfil {color: #52514e; font-size: 0.82rem;}
  [data-testid="stMetricValue"] {font-size: 1.7rem;}
</style>""", unsafe_allow_html=True)


def estilo(grafico):
    """Ejes y grilla discretos para todos los gráficos de Altair."""
    return (grafico.configure_axis(grid=False, domainColor="#d6d5d0", tickColor="#d6d5d0",
                                   labelColor=TINTA_2, titleColor=TINTA_2, labelFontSize=12)
            .configure_axisX(grid=True, gridColor="#ecebe7")
            .configure_view(stroke=None)
            .configure_legend(labelColor=TINTA, titleColor=TINTA_2, orient="top", labelFontSize=12))


def colores_opciones(opciones):
    """Color fijo por opción (en el orden escrito); 'No entiendo' siempre en gris."""
    rango, i = [], 0
    for o in opciones:
        if o == NO_ENTIENDO:
            rango.append(GRIS)
        else:
            rango.append(CATEGORICOS[i % len(CATEGORICOS)])
            i += 1
    return alt.Scale(domain=list(opciones), range=rango)


# ---------------------------------------------------------------- datos (con caché de Streamlit)

@st.cache_data
def datos_validacion():
    res = pd.read_csv(RAIZ / "data" / "validacion_resultados.csv")
    seg = pd.read_csv(RAIZ / "data" / "validacion_por_segmento.csv", dtype={"departamento_cod": str})
    return res, seg


@st.cache_data
def mapa_departamentos():
    return gpd.read_file(RAIZ / "data" / "peru_departamental.geojson")


@st.cache_data
def perfiles():
    return cargar_perfiles()


@st.cache_data
def registro_tokens():
    archivo = RAIZ / "data" / "registro_tokens.csv"
    return pd.read_csv(archivo) if archivo.exists() else pd.DataFrame()


@st.cache_data
def ejemplo():
    return json.loads((RAIZ / "data" / "ejemplo_precargado.json").read_text(encoding="utf-8"))


def margen_empirico(segmento):
    """Error medio (pp) medido en la validación para el segmento elegido, y su n."""
    _, seg = datos_validacion()
    prom = seg[seg["pregunta"] == "promedio"]
    if segmento == "Todo el Perú":
        fila = prom[prom["tipo"] == "Nacional"]
    elif segmento in ("Urbano", "Rural"):
        fila = prom[(prom["tipo"] == "Área") & (prom["segmento"] == segmento)]
    else:
        fila = prom[(prom["tipo"] == "Dominio") & (prom["segmento"] == segmento)]
    if fila.empty:
        return None, 0
    return float(fila["error_pp"].iloc[0]), int(fila["n"].iloc[0])


# ---------------------------------------------------------------- encabezado

st.title("Simula")
st.markdown('<p class="subtitulo">Pilotea tu encuesta con encuestados sintéticos que responden como hogares '
            'peruanos reales, y mira cuánto se equivoca la IA medida contra la ENAHO 2024.</p>',
            unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📊 ¿Cuánto se equivoca la IA en el Perú?", "🧪 Prueba tu pregunta",
                            "⚙️ Cómo funciona"])


# ================================================================ PESTAÑA 1
with tab1:
    res, seg = datos_validacion()
    prom = seg[seg["pregunta"] == "promedio"]
    nac = prom[prom["tipo"] == "Nacional"].iloc[0]
    area = prom[prom["tipo"] == "Área"].set_index("segmento")

    st.markdown(f"Le pedimos a la IA que responda como **{int(nac['n'])} hogares reales** de la ENAHO 2024 "
                "(sorteados según su peso `factor07`) **sin ver sus respuestas reales**, y comparamos.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Error medio nacional", f"{nac['error_pp']:.1f} pp", help="Promedio de |% sintético − % real| en las 5 preguntas")
    c2.metric("Error en zona urbana", f"{area.loc['Urbano', 'error_pp']:.1f} pp")
    c3.metric("Error en zona rural", f"{area.loc['Rural', 'error_pp']:.1f} pp")
    c4.metric("Acierto por hogar", f"{nac['accuracy']:.0f}%", help="% de respuestas individuales donde la IA acierta")

    st.subheader("Real vs. sintético, a nivel nacional")
    largo = pd.concat([
        res.assign(serie="Real (ENAHO)", pct=res["pct_real"]),
        res.assign(serie="Sintético (IA)", pct=res["pct_sintetico"]),
    ])
    largo["nombre"] = largo["pregunta"].map(NOMBRES_CORTOS)
    orden = res.sort_values("error_pp", ascending=False)["pregunta"].map(NOMBRES_CORTOS).tolist()
    base = alt.Chart(largo).encode(
        y=alt.Y("nombre:N", sort=orden, title=None),
        yOffset=alt.YOffset("serie:N", sort=["Real (ENAHO)", "Sintético (IA)"]),
        x=alt.X("pct:Q", title="% de hogares que responde «Sí»", scale=alt.Scale(domain=[0, 105])),
    )
    barras = base.mark_bar(cornerRadiusEnd=4, height=13).encode(
        color=alt.Color("serie:N", title=None,
                        scale=alt.Scale(domain=["Real (ENAHO)", "Sintético (IA)"], range=[AZUL, NARANJA])),
        tooltip=[alt.Tooltip("texto_pregunta:N", title="Pregunta"), alt.Tooltip("serie:N", title="Serie"),
                 alt.Tooltip("pct:Q", title="% Sí", format=".1f"),
                 alt.Tooltip("error_pp:Q", title="Error (pp)", format=".1f")])
    etiquetas = base.mark_text(align="left", dx=4, fontSize=11, color=TINTA_2).encode(text=alt.Text("pct:Q", format=".0f"))
    st.altair_chart(estilo((barras + etiquetas).properties(height=330)), width="stretch")
    peor = res.loc[res["error_pp"].idxmax()]
    st.caption(f"Ordenado de mayor a menor error. La IA acierta casi exacto en celular, pero en "
               f"**{NOMBRES_CORTOS[peor['pregunta']].lower()}** dice {peor['pct_sintetico']:.0f}% cuando la realidad "
               f"es {peor['pct_real']:.0f}%: imagina un Perú más conectado de lo que es.")

    col_mapa, col_dom = st.columns([1.15, 1])
    with col_mapa:
        st.subheader("Error por departamento")
        deps = prom[prom["tipo"] == "Departamento"][["departamento_cod", "segmento", "n", "error_pp", "accuracy"]]
        geo = mapa_departamentos().merge(deps, left_on="FIRST_IDDP", right_on="departamento_cod", how="left")
        geo["error_txt"] = geo["error_pp"].map(lambda v: f"{v:.1f} pp" if pd.notna(v) else "sin datos")
        geo["n_txt"] = geo["n"].map(lambda v: f"{int(v)} hogares" if pd.notna(v) else "0 hogares")
        # Sin mapa de fondo (tiles=None): más limpio y no depende de servicios externos durante el demo
        mapa = folium.Map(location=[-9.2, -75], zoom_start=5, tiles=None, control_scale=False)
        mapa.fit_bounds([[-18.4, -81.4], [-0.03, -68.6]])
        coro = folium.Choropleth(
            geo_data=geo.to_json(), data=geo, columns=["FIRST_IDDP", "error_pp"], key_on="feature.properties.FIRST_IDDP",
            fill_color="Oranges", fill_opacity=0.85, line_color="white", line_weight=1, nan_fill_color="#ecebe7",
            legend_name="Error medio de la IA (puntos porcentuales)").add_to(mapa)
        coro.geojson.add_child(folium.GeoJsonTooltip(fields=["NOMBDEP", "error_txt", "n_txt"],
                                                     aliases=["Departamento", "Error medio", "Muestra"]))
        st_folium(mapa, height=470, use_container_width=True, returned_objects=[])
        pocos = int((deps["n"] < 10).sum())
        st.caption(f"Pasa el cursor sobre un departamento. Con {int(nac['n'])} hogares, {pocos} departamentos tienen "
                   "menos de 10 casos: su error es orientativo.")
    with col_dom:
        st.subheader("Error por dominio")
        dom = prom[prom["tipo"] == "Dominio"].copy()
        dom["etiqueta"] = dom.apply(lambda r: f"{r['segmento']} (n={int(r['n'])})", axis=1)
        g = alt.Chart(dom).encode(
            y=alt.Y("etiqueta:N", sort="-x", title=None),
            x=alt.X("error_pp:Q", title="Error medio (pp)"))
        g = g.mark_bar(cornerRadiusEnd=4, height=16, color=TINTA_2).encode(
            tooltip=[alt.Tooltip("segmento:N", title="Dominio"), alt.Tooltip("n:Q", title="Hogares"),
                     alt.Tooltip("error_pp:Q", title="Error (pp)", format=".1f"),
                     alt.Tooltip("accuracy:Q", title="Acierto (%)", format=".0f")]) + \
            g.mark_text(align="left", dx=4, fontSize=11, color=TINTA_2).encode(text=alt.Text("error_pp:Q", format=".1f"))
        st.altair_chart(estilo(g.properties(height=330)), width="stretch")
        chicos = dom[dom["n"] < 20]["segmento"].tolist()
        st.caption("Promedio de las 5 preguntas." + (f" Con pocos hogares en la muestra: {', '.join(chicos)}." if chicos else ""))

    with st.expander("Ver la tabla completa por pregunta"):
        tabla = res[["texto_pregunta", "variable_enaho", "n", "pct_real_enaho", "pct_real", "pct_sintetico",
                     "error_pp", "accuracy"]].rename(columns={
            "texto_pregunta": "Pregunta", "variable_enaho": "Variable ENAHO", "pct_real_enaho": "% real ENAHO (ponderado)",
            "pct_real": "% real (muestra)", "pct_sintetico": "% sintético", "error_pp": "Error (pp)",
            "accuracy": "Acierto por hogar (%)"})
        st.dataframe(tabla, hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="%.1f") for c in tabla.columns[3:]})
        st.markdown("Método completo en `docs/validacion.md`.")


# ================================================================ PESTAÑA 2

def tabla_porcentajes(tabla, opciones, por=None):
    """% de cada respuesta (en el orden de las opciones), opcionalmente por segmento."""
    claves = [por, "respuesta"] if por else ["respuesta"]
    conteo = tabla.groupby(claves).size().rename("n").reset_index()
    total = conteo.groupby(por)["n"].transform("sum") if por else conteo["n"].sum()
    conteo["pct"] = 100 * conteo["n"] / total
    conteo["orden"] = conteo["respuesta"].map({o: i for i, o in enumerate(opciones)})
    return conteo


def grafico_distribucion(tabla, opciones, margen):
    d = tabla_porcentajes(tabla, opciones)
    d = d.set_index("respuesta").reindex(opciones).fillna({"n": 0, "pct": 0}).reset_index()
    d["bajo"] = (d["pct"] - (margen or 0)).clip(lower=0)
    d["alto"] = (d["pct"] + (margen or 0)).clip(upper=100)
    base = alt.Chart(d).encode(y=alt.Y("respuesta:N", sort=opciones, title=None))
    barras = base.mark_bar(cornerRadiusEnd=4, height=22).encode(
        x=alt.X("pct:Q", title="% de encuestados sintéticos", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("respuesta:N", scale=colores_opciones(opciones), legend=None),
        tooltip=[alt.Tooltip("respuesta:N", title="Respuesta"), alt.Tooltip("n:Q", title="Encuestados"),
                 alt.Tooltip("pct:Q", title="%", format=".1f")])
    capas = barras
    if margen:
        capas += base.mark_rule(color=TINTA, strokeWidth=1.5).encode(x="bajo:Q", x2="alto:Q")
    capas += base.mark_text(align="left", dx=6, dy=-10, fontSize=12, color=TINTA).encode(
        x="pct:Q", text=alt.Text("pct:Q", format=".0f"))
    return estilo(capas.properties(height=55 * len(opciones) + 30))


def grafico_cortes(tabla, opciones, por, orden_segmentos=None):
    d = tabla_porcentajes(tabla, opciones, por)
    g = alt.Chart(d).mark_bar(height=20).encode(
        y=alt.Y(f"{por}:N", sort=orden_segmentos, title=None),
        x=alt.X("pct:Q", stack="normalize", title="% de respuestas", axis=alt.Axis(format="%")),
        color=alt.Color("respuesta:N", scale=colores_opciones(opciones), title=None),
        order=alt.Order("orden:Q"),
        tooltip=[alt.Tooltip(f"{por}:N", title="Segmento"), alt.Tooltip("respuesta:N", title="Respuesta"),
                 alt.Tooltip("pct:Q", title="%", format=".1f"), alt.Tooltip("n:Q", title="Encuestados")])
    return estilo(g.properties(height=alt.Step(30)))  # altura por segmento, crece con la cantidad de filas


def mostrar_citas(tabla, opciones, k=4, semilla=0):
    """Hasta k citas, intentando que aparezcan respuestas distintas."""
    rnd = random.Random(semilla)
    elegidas = []
    for o in opciones:
        filas = tabla[tabla["respuesta"] == o]
        if len(filas):
            elegidas.append(filas.iloc[rnd.randrange(len(filas))])
    resto = tabla[~tabla["id_perfil"].isin([e["id_perfil"] for e in elegidas])]
    elegidas += [r for _, r in resto.sample(min(len(resto), max(0, k - len(elegidas))), random_state=semilla).iterrows()]
    cols = st.columns(2)
    for i, r in enumerate(elegidas[:k]):
        edad = f"{int(r['jefe_edad'])} años" if pd.notna(r["jefe_edad"]) else ""
        lugar = "Lima Metropolitana" if r["dominio"] == "Lima Metropolitana" else f"{r['departamento']}, {r['area'].lower()}"
        with cols[i % 2].container(border=True):
            st.markdown(f"**{r['respuesta']}** — <span class='cita'>“{r['justificacion']}”</span><br>"
                        f"<span class='cita-perfil'>{r['jefe_sexo']}, {edad} · {lugar} · quintil de gasto {r['quintil_gasto']} · "
                        f"{r['jefe_educacion'].lower()}</span>", unsafe_allow_html=True)


CORTES = {"Área": "area", "Dominio": "dominio", "Quintil de gasto": "quintil_gasto",
          "Pobreza": "pobreza", "Sexo del jefe(a)": "jefe_sexo"}


def csv_respuestas(tablas):
    """Respuestas para descargar: perfil + respuesta + justificación (sin las respuestas reales de la ENAHO)."""
    partes = []
    for version, t in tablas.items():
        t = t.drop(columns=[c for c in t.columns if c.startswith("real_")])
        partes.append(t.assign(version=version) if len(tablas) > 1 else t)
    return pd.concat(partes).to_csv(index=False).encode("utf-8-sig")


def mostrar_revision(rev, clave_pregunta, titulo=""):
    iconos = {"Bien": "✅", "Mejorable": "🟡", "Problemática": "🔴"}
    with st.container(border=True):
        st.markdown(f"**{titulo}Revisor de preguntas: {iconos.get(rev['veredicto'], '')} {rev['veredicto']}**")
        nombres = {"ambigua": "Ambigua", "doble": "Doble pregunta", "sesgada": "Sesgada / induce respuesta",
                   "opciones": "Opciones", "tecnica": "Palabras técnicas"}
        for p in rev["problemas"]:
            st.markdown(f"- **{nombres.get(p['tipo'], p['tipo'])}:** {p['explicacion']}")
        if not rev["problemas"]:
            st.markdown("No encontró problemas.")
        st.markdown(f"**Versión sugerida:** {rev['pregunta_mejorada']}  \n"
                    f"<span class='cita-perfil'>Opciones: {' · '.join(rev['opciones_mejoradas'])}</span>",
                    unsafe_allow_html=True)
        if clave_pregunta:
            def usar(r=rev, k=clave_pregunta):
                st.session_state[k] = r["pregunta_mejorada"]
                st.session_state["opciones"] = ", ".join(r["opciones_mejoradas"])
            st.button("Usar la versión sugerida", key=f"usar_{clave_pregunta}", on_click=usar)


def mostrar_resultado(r):
    """Dibuja el resultado guardado en session_state (en vivo o precargado)."""
    tablas, opciones = r["tablas"], r["opciones"]
    margen, n_val = margen_empirico(r["segmento"])
    if r["origen"] == "precargado":
        st.info("📦 Estás viendo el **ejemplo precargado** (una simulación real guardada). No usa la API.")
    for i, rev in enumerate(r.get("revisiones", [])):
        if rev:
            mostrar_revision(rev, None, titulo=f"Versión {'AB'[i]} · " if len(tablas) > 1 else "")

    uso = r["uso"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Encuestados sintéticos", f"{len(next(iter(tablas.values())))}", help=f"Segmento: {r['segmento']}")
    c2.metric("Margen de error empírico", f"± {margen:.0f} pp" if margen else "—",
              help=f"Error medio medido contra la ENAHO para «{r['segmento']}» (n={n_val} hogares en la validación). "
                   "Es cuánto se alejó la IA de la realidad en preguntas de tenencia de servicios.")
    c3.metric("Costo de esta simulación", f"S/ {uso['costo_soles']:.3f}",
              help=f"{uso['tokens_entrada']:,} tokens de entrada + {uso['tokens_salida']:,} de salida, "
                   f"{uso['llamadas']} llamadas a {MODELO}. Precio pagado; en el plan gratuito es S/ 0.")
    c4.metric("Tiempo", f"{uso['segundos']:.0f} s" if uso["segundos"] else "al instante (caché)")
    if margen and n_val < 20:
        st.caption(f"⚠️ El margen de «{r['segmento']}» se midió con solo {n_val} hogares: tómalo como referencia.")

    if len(tablas) == 1:
        tabla = next(iter(tablas.values()))
        st.markdown(f"#### {r['preguntas'][0]}")
        izq, der = st.columns([1.1, 1])
        with izq:
            st.altair_chart(grafico_distribucion(tabla, opciones, margen), width="stretch")
            if margen:
                st.caption(f"La línea negra marca ± {margen:.0f} pp: el rango en el que la IA suele equivocarse.")
        with der:
            por = st.selectbox("Cortar por", list(CORTES), key="corte_1")
            st.altair_chart(grafico_cortes(tabla, opciones, CORTES[por]), width="stretch")
        if NO_ENTIENDO in opciones:
            ne = tabla.assign(no_entiende=tabla["respuesta"] == NO_ENTIENDO).groupby("area")["no_entiende"].mean() * 100
            st.markdown(f"**«{NO_ENTIENDO}»:** {100 * (tabla['respuesta'] == NO_ENTIENDO).mean():.0f}% en total · "
                        + " · ".join(f"{a.lower()} {v:.0f}%" for a, v in ne.items()))
        st.markdown("##### Lo que dicen los encuestados sintéticos")
        mostrar_citas(tabla, opciones, semilla=r["semilla"])
    else:
        a, b = tablas["A"], tablas["B"]
        ne_a, ne_b = [100 * (t["respuesta"] == NO_ENTIENDO).mean() for t in (a, b)]
        cambio = a[["id_perfil", "respuesta"]].merge(b[["id_perfil", "respuesta"]], on="id_perfil", suffixes=("_a", "_b"))
        pct_cambio = 100 * (cambio["respuesta_a"] != cambio["respuesta_b"]).mean()
        m1, m2, m3 = st.columns(3)
        m1.metric("«No entiendo» en A", f"{ne_a:.0f}%")
        m2.metric("«No entiendo» en B", f"{ne_b:.0f}%", delta=f"{ne_b - ne_a:+.0f} pp vs A", delta_color="inverse")
        m3.metric("Hogares que cambian de respuesta", f"{pct_cambio:.0f}%", help="Mismos hogares en A y B")
        mejor = "A" if ne_a < ne_b else "B" if ne_b < ne_a else None
        if mejor:
            st.success(f"La **versión {mejor}** se entiende mejor: menos encuestados responden «{NO_ENTIENDO}».")

        # Comparación lado a lado por opción
        comp = pd.concat([tabla_porcentajes(a, opciones).assign(version="A"),
                          tabla_porcentajes(b, opciones).assign(version="B")])
        base = alt.Chart(comp).encode(
            y=alt.Y("respuesta:N", sort=opciones, title=None),
            yOffset=alt.YOffset("version:N"),
            x=alt.X("pct:Q", title="% de encuestados sintéticos", scale=alt.Scale(domain=[0, 105])))
        g = base.mark_bar(cornerRadiusEnd=4, height=14).encode(
            color=alt.Color("version:N", title=None, scale=alt.Scale(domain=["A", "B"], range=[AZUL, NARANJA]),
                            legend=alt.Legend(labelExpr="'Versión ' + datum.label")),
            tooltip=[alt.Tooltip("version:N", title="Versión"), alt.Tooltip("respuesta:N", title="Respuesta"),
                     alt.Tooltip("pct:Q", title="%", format=".1f"), alt.Tooltip("n:Q", title="Encuestados")]) + \
            base.mark_text(align="left", dx=4, fontSize=11, color=TINTA_2).encode(text=alt.Text("pct:Q", format=".0f"))
        st.markdown(f"**A:** {r['preguntas'][0]}  \n**B:** {r['preguntas'][1]}")
        st.altair_chart(estilo(g.properties(height=48 * len(opciones) + 40)), width="stretch")

        st.markdown(f"##### «{NO_ENTIENDO}» por segmento")
        por = st.selectbox("Cortar por", list(CORTES), key="corte_ab")
        col = CORTES[por]
        ne = pd.concat([t.assign(version=v, ne=(t["respuesta"] == NO_ENTIENDO) * 100.0) for v, t in tablas.items()])
        ne = ne.groupby([col, "version"])["ne"].agg(pct="mean", n="size").reset_index()
        g2 = alt.Chart(ne).encode(y=alt.Y(f"{col}:N", title=None), yOffset="version:N",
                                  x=alt.X("pct:Q", title=f"% «{NO_ENTIENDO}»"))
        g2 = g2.mark_bar(cornerRadiusEnd=4).encode(
            color=alt.Color("version:N", scale=alt.Scale(domain=["A", "B"], range=[AZUL, NARANJA]),
                            title=None, legend=alt.Legend(labelExpr="'Versión ' + datum.label")),
            tooltip=[alt.Tooltip(f"{col}:N", title="Segmento"), alt.Tooltip("version:N", title="Versión"),
                     alt.Tooltip("pct:Q", title="% no entiende", format=".1f"), alt.Tooltip("n:Q", title="Encuestados")])
        # Altura por barra (Step): con una altura fija, Streamlit la reparte con la leyenda y las barras se aplastan
        st.altair_chart(estilo(g2.properties(height=alt.Step(16))), width="stretch")

        st.markdown("##### Lo que dicen los encuestados sintéticos")
        ca, cb = st.columns(2)
        with ca:
            st.markdown("**Versión A**")
            mostrar_citas_simple(a, opciones, r["semilla"])
        with cb:
            st.markdown("**Versión B**")
            mostrar_citas_simple(b, opciones, r["semilla"])

    st.download_button("⬇️ Descargar respuestas (CSV)", csv_respuestas(tablas), file_name="simula_respuestas.csv",
                       mime="text/csv")


def mostrar_citas_simple(tabla, opciones, semilla):
    """Citas en una sola columna (para la vista A/B)."""
    rnd = random.Random(semilla)
    vistas = []
    for o in opciones:
        filas = tabla[tabla["respuesta"] == o]
        if len(filas):
            vistas.append(filas.iloc[rnd.randrange(len(filas))])
    for r in vistas[:4]:
        lugar = "Lima Metropolitana" if r["dominio"] == "Lima Metropolitana" else f"{r['departamento']}, {r['area'].lower()}"
        with st.container(border=True):
            st.markdown(f"**{r['respuesta']}** — <span class='cita'>“{r['justificacion']}”</span><br>"
                        f"<span class='cita-perfil'>{lugar} · quintil {r['quintil_gasto']} · "
                        f"{r['jefe_educacion'].lower()}</span>", unsafe_allow_html=True)


def cargar_ejemplo():
    e = ejemplo()
    uso = {k: e["uso_a"][k] + e["uso_b"][k] for k in ("tokens_entrada", "tokens_salida", "costo_soles", "llamadas", "segundos")}
    opciones = e["opciones"] + [NO_ENTIENDO]
    st.session_state["resultado"] = {
        "origen": "precargado", "segmento": e["segmento"], "semilla": e["semilla"], "opciones": opciones,
        "preguntas": [e["pregunta_a"], e["pregunta_b"]],
        "tablas": {"A": pd.DataFrame(e["respuestas_a"]), "B": pd.DataFrame(e["respuestas_b"])},
        "uso": uso, "revisiones": [None, e["revision"]]}


with tab2:
    # Valores iniciales de los campos (se guardan en session_state para que el revisor pueda cambiarlos)
    st.session_state.setdefault("pregunta_a", "¿Pagarías S/ 20 al mes por tener internet fijo (wifi) en tu casa?")
    st.session_state.setdefault("pregunta_b", "¿Estaría dispuesto a contratar un plan de banda ancha fija FTTH de 20 soles mensuales?")
    st.session_state.setdefault("opciones", "Sí, No, No sé")

    hay_clave = bool(os.getenv("GEMINI_API_KEY"))
    if not hay_clave:
        st.warning("No hay `GEMINI_API_KEY` configurada: puedes ver el ejemplo precargado, pero no simular en vivo.")

    modo = st.radio("Modo", ["Una pregunta", "Prueba A/B de redacción"], horizontal=True, label_visibility="collapsed")
    ab = modo != "Una pregunta"

    if ab:
        ca, cb = st.columns(2)
        ca.text_area("Versión A", key="pregunta_a", height=90)
        cb.text_area("Versión B", key="pregunta_b", height=90)
    else:
        st.text_area("Tu pregunta", key="pregunta_a", height=80)
    c1, c2, c3 = st.columns([1.4, 1.1, 1])
    c1.text_input("Opciones (separadas por comas)", key="opciones",
                  help=f"La app agrega «{NO_ENTIENDO}» automáticamente si dejas marcada la casilla.")
    otros = sorted(d for d in perfiles()["dominio"].unique() if d != "Lima Metropolitana")
    segmento = c2.selectbox("Segmento", ["Todo el Perú", "Lima Metropolitana", "Urbano", "Rural"] + otros)
    n = c3.slider("Encuestados (N)", 30, 100, 50, step=10)
    permitir = st.checkbox(f"Permitir que respondan «{NO_ENTIENDO}»", value=True)

    preguntas = [st.session_state["pregunta_a"].strip()] + ([st.session_state["pregunta_b"].strip()] if ab else [])
    opciones = [o.strip() for o in st.session_state["opciones"].split(",") if o.strip()]

    b1, b2, b3, _ = st.columns([1, 1, 1.2, 1.3])
    revisar = b1.button("🔍 Revisar pregunta", width="stretch", disabled=not hay_clave)
    lanzar = b2.button("▶ Simular", type="primary", width="stretch", disabled=not hay_clave)
    if b3.button("📦 Ver ejemplo precargado", width="stretch"):
        cargar_ejemplo()

    error_entrada = None
    if not all(preguntas):
        error_entrada = "Escribe la pregunta (y la versión B si estás en modo A/B)."
    elif not 2 <= len(opciones) <= 6:
        error_entrada = "Escribe entre 2 y 6 opciones, separadas por comas."

    if (revisar or lanzar) and error_entrada:
        st.error(error_entrada)
    elif revisar:
        try:
            with st.spinner("Revisando la redacción…"):
                st.session_state["revisiones"] = [revisar_pregunta(p, opciones)[0].model_dump() for p in preguntas]
        except Exception as e:
            st.error(f"El revisor no respondió ({type(e).__name__}). Prueba de nuevo o mira el ejemplo precargado.")
    elif lanzar:
        semilla = random.randint(1, 10_000)
        hogares = muestrear(perfiles(), n, segmento, semilla=semilla)  # mismos hogares para A y B
        tablas, uso_total = {}, {"tokens_entrada": 0, "tokens_salida": 0, "costo_soles": 0.0, "llamadas": 0, "segundos": 0.0}
        barra = st.progress(0.0, text="Preguntando a los hogares…")
        try:
            for i, p in enumerate(preguntas):
                def avance(hechos, total, i=i):
                    barra.progress((i + hechos / total) / len(preguntas),
                                   text=f"Versión {'AB'[i]}: {hechos}/{total} hogares" if ab else f"{hechos}/{total} hogares")
                t, uso = simular(p, opciones, hogares, permitir_no_entiendo=permitir, al_avanzar=avance)
                tablas["AB"[i] if ab else "A"] = t
                for k in uso_total:
                    uso_total[k] += uso[k]
            barra.empty()
            st.session_state["resultado"] = {
                "origen": "en vivo", "segmento": segmento, "semilla": semilla, "preguntas": preguntas,
                "opciones": opciones + ([NO_ENTIENDO] if permitir and NO_ENTIENDO not in opciones else []),
                "tablas": tablas, "uso": uso_total, "revisiones": []}
        except Exception as e:
            barra.empty()
            st.error(f"La API de Gemini no respondió ({type(e).__name__}). Te muestro el ejemplo precargado.")
            cargar_ejemplo()

    # Revisión pedida con el botón (antes de simular)
    if st.session_state.get("revisiones") and not lanzar:
        cols = st.columns(len(st.session_state["revisiones"]))
        for i, rev in enumerate(st.session_state["revisiones"]):
            with cols[i]:
                mostrar_revision(rev, ["pregunta_a", "pregunta_b"][i], titulo=f"Versión {'AB'[i]} · " if ab else "")

    if "resultado" in st.session_state:
        st.divider()
        mostrar_resultado(st.session_state["resultado"])


# ================================================================ PESTAÑA 3
with tab3:
    res, _ = datos_validacion()
    izq, der = st.columns([1.2, 1])
    with izq:
        st.subheader("El flujo")
        st.graphviz_chart("""
        digraph {
          rankdir=TB; bgcolor="transparent";
          node [shape=box, style="rounded,filled", fillcolor="#f3f2ef", color="#d6d5d0", fontname="Helvetica", fontsize=11, margin="0.2,0.1"];
          edge [color="#8f8e89", fontname="Helvetica", fontsize=9, fontcolor="#52514e"];
          enaho [label="ENAHO 2024 (INEI)\\nmódulos 01, 02, 03, 34", fillcolor="#e7f0fb", color="#2a78d6"];
          perfiles [label="3,000 perfiles de hogares\\n(sin identificadores)"];
          validar [label="Validación: 400 hogares\\nIA vs respuesta real"];
          error [label="Error por segmento\\n(pestaña 1 y margen)", fillcolor="#fdebe3", color="#eb6834"];
          usuario [label="Tu pregunta + segmento + N"];
          revisor [label="Revisor de preguntas\\n(Gemini)"];
          muestreo [label="Sorteo de N hogares\\nponderado por factor07"];
          llm [label="Gemini responde como cada hogar\\n25 por llamada · salida JSON"];
          resultado [label="Distribución, cortes, citas,\\n% no entiendo, A/B y CSV", fillcolor="#fdebe3", color="#eb6834"];
          enaho -> perfiles; perfiles -> validar -> error;
          usuario -> revisor; usuario -> muestreo; perfiles -> muestreo -> llm -> resultado; error -> resultado [label=" margen"];
        }""", width="stretch")
    with der:
        st.subheader("Modelo y costo")
        reg = registro_tokens()
        # Costo real de una simulación de 100 hogares: la versión A del ejemplo precargado
        uso_100 = ejemplo()["uso_a"]
        if len(reg):
            por_llamada = {"tokens_entrada": uso_100["tokens_entrada"] / uso_100["llamadas"],
                           "tokens_salida": uso_100["tokens_salida"] / uso_100["llamadas"]}
            st.metric("Costo de simular 100 encuestados", f"S/ {uso_100['costo_soles']:.3f}",
                      help=f"Tokens reales: {uso_100['tokens_entrada']:,} de entrada + {uso_100['tokens_salida']:,} "
                           f"de salida en {uso_100['llamadas']} llamadas (ejemplo precargado). Todas las llamadas "
                           "quedan en data/registro_tokens.csv")
            st.markdown(
                f"- **Modelo:** `{MODELO}` (Google Gemini, plan gratuito), con salida estructurada en JSON validada con Pydantic.\n"
                f"- **Por qué:** es estable, rápido (~4 s por llamada de {POR_LLAMADA} hogares) y barato. Probamos "
                "`gemini-3.8-flash`, pero no respondía y `gemini-3.6-flash` estaba saturado: para un demo en vivo "
                "pesa más la confiabilidad.\n"
                f"- **Tokens por llamada ({POR_LLAMADA} hogares):** ~{por_llamada['tokens_entrada']:,.0f} de entrada y "
                f"~{por_llamada['tokens_salida']:,.0f} de salida.\n"
                f"- **Precio pagado:** US$ {PRECIO_ENTRADA_USD} / US$ {PRECIO_SALIDA_USD} por millón de tokens "
                f"(entrada/salida), tipo de cambio S/ {TIPO_CAMBIO}. En el plan gratuito pagamos S/ 0.\n"
                f"- **Validación completa** ({int(res['n'].max())} hogares × 5 preguntas, {int(res['llamadas'].sum())} "
                f"llamadas): S/ {res['costo_soles'].sum():.2f}.")
    st.subheader("Limitaciones (honestas)")
    st.markdown(
        "- **La IA no reemplaza el campo.** Sirve para pilotear: detectar preguntas confusas y comparar redacciones "
        "antes de gastar en encuestadores.\n"
        "- **El margen de error se midió con preguntas de tenencia de servicios** (celular, internet, agua…). "
        "En opiniones, precios o marcas el error puede ser distinto, y no lo hemos medido.\n"
        "- **La IA tiene sesgos visibles:** sobreestima el acceso a internet fijo y TV cable (imagina un Perú más "
        "conectado) y subestima el agua de red pública.\n"
        f"- **Muestra de validación acotada:** {int(res['n'].max())} hogares; por departamento hay pocos casos y el "
        "mapa es orientativo.\n"
        "- **Los perfiles son de 2024** y solo describen al hogar y a su jefe(a), no a cada persona.\n"
        "- Los encuestados sintéticos responden en lotes de 25: el modelo puede \"contagiarse\" entre hogares del mismo lote.")
    st.caption("Datos: ENAHO 2024, INEI (código 966). Mapa: GeoJSON departamental del curso Data Science con Python (UP).")
