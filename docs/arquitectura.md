# Arquitectura de Simula

```mermaid
flowchart LR
    subgraph datos["1 · Datos (una vez, en local)"]
        ENAHO[("ENAHO 2024 · INEI<br/>módulos 01, 02, 03, 34<br/>datos_crudos/ · no se sube")]
        PREP["scripts/preparar_perfiles.py<br/>une módulos · encuestas completas e incompletas"]
        PERF[("data/perfiles.parquet<br/>3,000 hogares sin IDs<br/>perfil + factor07 + 5 respuestas reales")]
        ENAHO --> PREP --> PERF
    end

    subgraph val["2 · Validación (precalculada)"]
        VAL["ai/validar.py<br/>400 hogares sorteados por factor07"]
        RES[("data/validacion_*.csv<br/>docs/validacion.md")]
        VAL --> RES
    end

    subgraph ia["Motor de IA · ai/"]
        PROM["prompts.py<br/>ficha del hogar · prompts"]
        SIM["simulador.py<br/>sorteo ponderado · 25 hogares por llamada<br/>reintentos 429/5xx · caché · registro de tokens"]
        GEM{{"Gemini<br/>gemini-3.5-flash-lite<br/>salida JSON (Pydantic)"}}
        PROM --> SIM <--> GEM
    end

    subgraph app["3 · App · app/streamlit_app.py (Streamlit Cloud)"]
        T1["Pestaña 1<br/>¿Cuánto se equivoca la IA?<br/>gráficos + mapa Folium"]
        T2["Pestaña 2<br/>Prueba tu pregunta<br/>revisor · simulación · A/B · CSV"]
        T3["Pestaña 3<br/>Cómo funciona<br/>costo real por tokens"]
        EJ[("data/ejemplo_precargado.json<br/>respaldo si falla la API")]
    end

    PERF --> VAL
    VAL --> SIM
    PERF --> SIM
    RES --> T1
    RES -- "margen de error<br/>por segmento" --> T2
    SIM --> T2
    EJ --> T2
    SIM -- "data/registro_tokens.csv" --> T3
```

**Cómo leerlo:** los microdatos de la ENAHO se procesan una sola vez en local y quedan como 3,000 perfiles
sin identificadores. La validación usa esos perfiles para medir el error de la IA, y la app muestra ese error
(pestaña 1) y lo usa como margen empírico de cada simulación en vivo (pestaña 2).
