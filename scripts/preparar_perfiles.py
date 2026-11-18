"""
Prepara data/perfiles.parquet a partir de la ENAHO 2024 (INEI, código 966).

Qué hace (en orden):
  1. Lee los módulos 01 (vivienda/hogar), 02 (miembros), 03 (educación) y 34 (sumaria)
     desde datos_crudos/ (esa carpeta NO se sube a GitHub).
  2. Se queda con las encuestas completas e incompletas (result 1 y 2), lo estándar en la ENAHO para
     variables del hogar: las incompletas tienen el módulo de hogar respondido y son sobre todo de Lima
     (excluirlas dejaba a Lima Metropolitana con 16.8% de los hogares en vez de 32.5%).
  3. Arma el perfil de cada hogar: departamento, dominio, área, tamaño, gasto per cápita,
     quintil de gasto, pobreza y datos del jefe(a) de hogar (sexo, edad, educación).
  4. Agrega las 5 respuestas REALES de validación (celular, internet, TV cable, agua de red
     pública y cocinar con gas). Se usan en ai/validar.py para medir el error de la IA.
  5. Toma una muestra aleatoria simple de 3,000 hogares y guarda el parquet SIN
     identificadores (sin conglome/vivienda/hogar ni ubigeo completo).
  6. Imprime un chequeo: % ponderado (factor07) de las 5 preguntas, ENAHO vs muestra.

Sobre los pesos: la muestra de 3,000 es uniforme, así que conserva el diseño de la ENAHO
(que sobrerrepresenta zonas rurales y departamentos chicos). Por eso, en cualquier cálculo
o sorteo posterior hay que ponderar por factor07 para representar a los hogares del Perú.

Uso:  python scripts/preparar_perfiles.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

RAIZ = Path(__file__).resolve().parents[1]
CRUDOS = RAIZ / "datos_crudos"
SALIDA = RAIZ / "data" / "perfiles.parquet"

N_PERFILES = 3000
SEMILLA = 42
LLAVE = ["conglome", "vivienda", "hogar"]  # llave de hogar en la ENAHO

# Códigos de departamento = 2 primeros dígitos del ubigeo (coinciden con FIRST_IDDP del GeoJSON)
DEPARTAMENTOS = {
    "01": "Amazonas", "02": "Áncash", "03": "Apurímac", "04": "Arequipa", "05": "Ayacucho",
    "06": "Cajamarca", "07": "Callao", "08": "Cusco", "09": "Huancavelica", "10": "Huánuco",
    "11": "Ica", "12": "Junín", "13": "La Libertad", "14": "Lambayeque", "15": "Lima",
    "16": "Loreto", "17": "Madre de Dios", "18": "Moquegua", "19": "Pasco", "20": "Piura",
    "21": "Puno", "22": "San Martín", "23": "Tacna", "24": "Tumbes", "25": "Ucayali",
}
DOMINIOS = {
    1: "Costa norte", 2: "Costa centro", 3: "Costa sur", 4: "Sierra norte",
    5: "Sierra centro", 6: "Sierra sur", 7: "Selva", 8: "Lima Metropolitana",
}
POBREZA = {1: "Pobre extremo", 2: "Pobre no extremo", 3: "No pobre"}

# Educación del jefe (p301a) agrupada en 5 niveles fáciles de leer para el LLM
EDUCACION = {
    1: "Sin nivel", 2: "Sin nivel", 12: "Sin nivel",  # 2 = inicial, 12 = básica especial
    3: "Primaria", 4: "Primaria",
    5: "Secundaria", 6: "Secundaria",
    7: "Superior técnica", 8: "Superior técnica",
    9: "Superior universitaria", 10: "Superior universitaria", 11: "Superior universitaria",
}


def leer(ruta, columnas):
    """Lee un .dta de Stata con solo las columnas que necesitamos."""
    df, _ = pyreadstat.read_dta(str(CRUDOS / ruta), usecols=columnas)
    return df


def a_numero(serie):
    """Algunas columnas vienen como texto ('0', '1'); las pasamos a número."""
    return pd.to_numeric(serie, errors="coerce")


def quintiles_ponderados(valor, peso):
    """Quintil (1 = más pobre, 5 = más rico) usando pesos de población, como el INEI."""
    orden = np.argsort(valor.to_numpy())
    peso_acum = np.cumsum(peso.to_numpy()[orden]) / peso.sum()
    quintil = np.empty(len(valor), dtype=int)
    quintil[orden] = np.minimum(np.ceil(peso_acum * 5), 5).astype(int)
    return quintil


def pct_ponderado(df, columna):
    """% de hogares con columna == 1, ponderado por factor07 (ignora vacíos)."""
    d = df[df[columna].notna()]
    return 100 * (d[columna] * d["factor07"]).sum() / d["factor07"].sum()


def main():
    # ---------- 1. Módulo 01: hogar + respuestas reales de validación ----------
    m01 = leer("mod01/966-Modulo01/enaho01-2024-100.dta",
               LLAVE + ["ubigeo", "dominio", "estrato", "result", "factor07",
                        "p1142", "p1144", "p114b1", "p1143", "p110", "p113a"])
    m01 = m01[m01["result"].isin([1, 2])].copy()  # 1 = completa, 2 = incompleta (hogar respondido)

    # ---------- 2. Sumaria (mód. 34): tamaño, gasto y pobreza ----------
    sumaria = leer("mod34/966-Modulo34/sumaria-2024.dta",
                   LLAVE + ["mieperho", "gashog2d", "pobreza"])
    hogares = m01.merge(sumaria, on=LLAVE, how="inner")

    # ---------- 3. Jefe(a) de hogar: mód. 02 (sexo, edad) + mód. 03 (educación) ----------
    m02 = leer("mod02/966-Modulo02/enaho01-2024-200.dta",
               LLAVE + ["codperso", "p203", "p207", "p208a"])
    jefes = m02[a_numero(m02["p203"]) == 1]  # p203 == 1 → jefe/jefa
    m03 = leer("mod03/966-Modulo03/enaho01a-2024-300.dta", LLAVE + ["codperso", "p301a"])
    jefes = jefes.merge(m03, on=LLAVE + ["codperso"], how="left")
    hogares = hogares.merge(jefes[LLAVE + ["p207", "p208a", "p301a"]], on=LLAVE, how="left")

    # ---------- 4. Variables de perfil (nombres claros en español) ----------
    p = pd.DataFrame()
    p["departamento_cod"] = hogares["ubigeo"].str[:2]
    p["departamento"] = p["departamento_cod"].map(DEPARTAMENTOS)
    p["dominio"] = hogares["dominio"].map(DOMINIOS)
    # Urbano = estratos 1–5 (2,000+ habitantes). La Ficha Técnica ubica los centros
    # poblados de 500 a <2,000 habitantes (estrato 6) y las AER (7–8) en el área rural.
    p["area"] = np.where(hogares["estrato"] <= 5, "Urbano", "Rural")
    p["miembros"] = hogares["mieperho"].astype(int)
    p["gasto_pc_mensual"] = (hogares["gashog2d"] / hogares["mieperho"] / 12).round(0)
    p["quintil_gasto"] = quintiles_ponderados(p["gasto_pc_mensual"],
                                              hogares["factor07"] * hogares["mieperho"])
    p["pobreza"] = hogares["pobreza"].map(POBREZA)
    p["jefe_sexo"] = a_numero(hogares["p207"]).map({1: "Hombre", 2: "Mujer"})
    p["jefe_edad"] = a_numero(hogares["p208a"]).astype("Int64")
    p["jefe_educacion"] = a_numero(hogares["p301a"]).map(EDUCACION).fillna("Sin dato")
    p["factor07"] = hogares["factor07"]

    # ---------- 5. Respuestas reales (1 = sí, 0 = no) ----------
    p["real_celular"] = a_numero(hogares["p1142"])          # p1142: tiene teléfono celular
    # p1144: internet fijo O móvil (incluye datos prepago en el celular) → ~91% de hogares.
    # Ojo: el INEI publica 58.4% de hogares con internet (IV trim. 2024), con otra definición.
    p["real_internet"] = a_numero(hogares["p1144"])
    # p114b1: solo conexión fija (en el diccionario aparece como P1144B1) → ~21% de hogares
    # Viene vacío si el hogar no tiene internet (no se le pregunta) → eso es un "no" (0).
    p["real_internet_fijo"] = a_numero(hogares["p114b1"]).fillna(0)
    p["real_tv_cable"] = a_numero(hogares["p1143"])         # p1143: TV por cable o satelital
    # p110: agua por red pública (1 = dentro de la vivienda, 2 = fuera pero dentro del edificio)
    p["real_agua_red"] = a_numero(hogares["p110"]).isin([1, 2]).astype(int)
    # p113a: combustible más usado para cocinar. Gas = 2 (balón GLP) o 3 (gas natural).
    # Vacío = el hogar no cocina (p1138 = 1) → queda vacío (no aplica la pregunta).
    combustible = a_numero(hogares["p113a"])
    p["real_gas"] = np.where(combustible.isna(), np.nan, combustible.isin([2, 3]).astype(float))

    # ---------- 6. Muestra de 3,000 hogares y guardado ----------
    muestra = p.sample(n=N_PERFILES, random_state=SEMILLA).reset_index(drop=True)
    muestra.insert(0, "id_perfil", range(1, N_PERFILES + 1))  # id propio, no del INEI
    SALIDA.parent.mkdir(exist_ok=True)
    muestra.to_parquet(SALIDA, index=False)

    # ---------- 7. Chequeo de razonabilidad ----------
    print(f"Hogares (result 1 y 2) en la ENAHO 2024: {len(p):,}  |  muestra guardada: {len(muestra):,}")
    print(f"Archivo: {SALIDA.relative_to(RAIZ)}\n")
    print(f"{'Indicador (% hogares, ponderado)':38}{'ENAHO':>8}{'Muestra':>9}{'Urbano':>8}{'Rural':>7}")
    for col in ["real_celular", "real_internet", "real_internet_fijo",
                "real_tv_cable", "real_agua_red", "real_gas"]:
        fila = [pct_ponderado(p, col), pct_ponderado(muestra, col),
                pct_ponderado(p[p.area == "Urbano"], col), pct_ponderado(p[p.area == "Rural"], col)]
        print(f"{col:38}" + "".join(f"{v:>8.1f} " for v in fila))
    print("\nVacíos por columna en la muestra:")
    print(muestra.isna().sum()[lambda s: s > 0].to_string() or "  ninguno")


if __name__ == "__main__":
    main()
