"""
Despliega Simula en Render (web service gratuito con Docker), desde el repo público de GitHub.

- Si el servicio "simula" no existe, lo crea (plan free, Dockerfile de la raíz del repo).
- Si ya existe, actualiza sus variables de entorno y lanza un nuevo despliegue.
- GEMINI_API_KEY y GEMINI_MODEL se leen de .env y se envían a Render como variables de entorno
  del servicio: nunca se escriben en un archivo ni se imprimen.

Requiere en .env: RENDER_API_KEY, GEMINI_API_KEY y GEMINI_MODEL.
Uso:  python scripts/desplegar_render.py
"""

from pathlib import Path

import requests
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parents[1]
API = "https://api.render.com/v1"
NOMBRE = "simula"
REPO = "https://github.com/JazminGalindoo/simula"


def main():
    cfg = dotenv_values(RAIZ / ".env")
    for clave in ("RENDER_API_KEY", "GEMINI_API_KEY", "GEMINI_MODEL"):
        if not cfg.get(clave):
            raise SystemExit(f"Falta {clave} en .env")
    sesion = requests.Session()
    sesion.headers.update({"Authorization": f"Bearer {cfg['RENDER_API_KEY']}", "Accept": "application/json"})
    variables = [{"key": "GEMINI_API_KEY", "value": cfg["GEMINI_API_KEY"]},
                 {"key": "GEMINI_MODEL", "value": cfg["GEMINI_MODEL"]}]

    def pedir(metodo, ruta, **kw):
        r = sesion.request(metodo, API + ruta, timeout=60, **kw)
        if r.status_code >= 400:  # mostramos el error de Render (no contiene nuestras claves)
            raise SystemExit(f"Render respondió {r.status_code} en {metodo} {ruta}: {r.text[:500]}")
        return r.json() if r.text else {}

    owner_id = pedir("GET", "/owners")[0]["owner"]["id"]
    existentes = pedir("GET", "/services", params={"name": NOMBRE, "type": "web_service", "ownerId": owner_id})

    if existentes:
        servicio = existentes[0]["service"]
        pedir("PUT", f"/services/{servicio['id']}/env-vars", json=variables)
        pedir("POST", f"/services/{servicio['id']}/deploys", json={})
        print("Servicio existente: variables actualizadas y nuevo despliegue lanzado.")
    else:
        respuesta = pedir("POST", "/services", json={
            "type": "web_service",
            "name": NOMBRE,
            "ownerId": owner_id,
            "repo": REPO,
            "branch": "main",
            "autoDeployTrigger": "off",
            "envVars": variables,
            "serviceDetails": {
                "runtime": "docker",
                "plan": "free",
                "region": "oregon",
                "healthCheckPath": "/_stcore/health",  # endpoint de salud de Streamlit
                "envSpecificDetails": {"dockerfilePath": "./Dockerfile", "dockerContext": "."},
            },
        })
        servicio = respuesta.get("service", respuesta)
        print("Servicio creado y primer despliegue lanzado.")

    print("ID del servicio:", servicio["id"])
    print("URL pública:", servicio["serviceDetails"]["url"])


if __name__ == "__main__":
    main()
