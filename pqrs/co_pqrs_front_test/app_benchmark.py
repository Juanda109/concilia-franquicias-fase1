"""Vista "Benchmark" del front de pruebas: lanzar una corrida con nombre y ver el resultado.

Negocio no debe subir YAML ni entrar a OKD para saber si el agente rutea bien.
Esta vista corre el cliente del benchmark (``co_pqrs_benchmark/main.py``) como
subproceso contra el agente configurado en el front, con publicacion de
eventos a RabbitMQ si esta habilitada, y al terminar muestra el resumen y el
enlace al tablero de OpenSearch Dashboards filtrado por la corrida.

Variables de entorno del front:

* ``BENCHMARK_DIR``       carpeta de co_pqrs_benchmark (default: ../co_pqrs_benchmark).
* ``OSD_URL``             base de OpenSearch Dashboards para los enlaces (default http://localhost:5601).
* ``RABBITMQ_ENABLED``, ``RABBITMQ_HOST``, ``RABBITMQ_PORT``, ``RABBITMQ_USER``,
  ``RABBITMQ_PASSWORD``, ``RABBITMQ_VHOST``  se pasan tal cual al benchmark.
* ``CATALOG_VERSION``, ``ENVIRONMENT``      se pasan tal cual (default unknown / local).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import streamlit as st

_RUN_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_SUMMARY_KEYS = (
    ("precision_pct", "Precisión (%)"),
    ("casos", "Casos"),
    ("aciertos", "Aciertos"),
    ("fallos", "Fallos"),
    ("sin_resolver", "Sin resolver"),
    ("modelo", "Modelo"),
    ("duracion_s", "Duración (s)"),
)


def benchmark_dir() -> Path:
    raw = os.getenv("BENCHMARK_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / "co_pqrs_benchmark").resolve()


def osd_url() -> str:
    return os.getenv("OSD_URL", "http://localhost:5601").rstrip("/")


def list_datasets(base: Path) -> list[Path]:
    datasets = base / "datasets"
    if not datasets.is_dir():
        return []
    return sorted(p for p in datasets.glob("*.json") if p.is_file())


def sanitize_run_name(value: str) -> str:
    """Nombre apto para run_id: sin tildes ni signos, guiones en vez de espacios."""

    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    cleaned = _RUN_NAME_RE.sub("-", ascii_value.strip()).strip("-")
    return cleaned[:60] or "corrida-manual"


def dashboard_link(run_name: str, source: str) -> str:
    dashboard = "pqr-canario-dashboard" if source == "canario" else "pqr-benchmark-dashboard"
    query = quote(f'run_name:"{run_name}"', safe="")
    return (
        f"{osd_url()}/app/dashboards#/view/{dashboard}?security_tenant=global"
        f"&_g=(time:(from:now-7d,to:now))&_a=(query:(language:kuery,query:'{query}'))"
    )


def parse_summary(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        values[key.strip()] = value.strip()
    return values


def build_env(*, run_name: str, source: str, dataset: Path, out_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "API_BASE_URL": st.session_state.get("api_base_url", "http://127.0.0.1:8000"),
            "MINIO_ENABLED": "false",
            "INPUT_JSON": str(dataset),
            "OUTPUT_JSON": str(out_dir / f"{run_name}.ndjson"),
            "SUMMARY_TXT": str(out_dir / f"{run_name}_summary.txt"),
            "RUN_NAME": run_name,
            "BENCHMARK_SOURCE": source,
            "CATALOG_VERSION": os.getenv("CATALOG_VERSION", "unknown"),
            "ENVIRONMENT": os.getenv("ENVIRONMENT", "local"),
            "PYTHONUNBUFFERED": "1",
        }
    )
    return env


def run_benchmark(
    *, run_name: str, source: str, dataset: Path, log_area, status_area
) -> tuple[int, dict[str, str], Path]:
    base = benchmark_dir()
    out_dir = base / ".data" / "front"
    out_dir.mkdir(parents=True, exist_ok=True)
    env = build_env(run_name=run_name, source=source, dataset=dataset, out_dir=out_dir)

    process = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=str(base),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    started = time.monotonic()
    assert process.stdout is not None
    for line in process.stdout:
        lines.append(line.rstrip("\n"))
        # Solo las lineas del veredicto por caso y el resumen: el log completo
        # queda en el fichero de salida.
        visible = [l for l in lines if re.search(r"\]\s+(OK|MISS|OPEN)\s|Resumen|precision|published", l)]
        log_area.code("\n".join(visible[-40:]) or "arrancando...", language="text")
        status_area.caption(f"{len(lines)} líneas · {int(time.monotonic() - started)} s")
    code = process.wait()

    summary_path = Path(env["SUMMARY_TXT"])
    summary = parse_summary(summary_path.read_text()) if summary_path.exists() else {}
    return code, summary, Path(env["OUTPUT_JSON"])


def render_benchmark_page() -> None:
    st.header("Benchmark de ruteo")
    st.caption(
        "Corre el dataset elegido contra el agente configurado en la vista de chat y publica los "
        "resultados al mismo pipeline que el CronJob. Al terminar, el enlace abre el tablero filtrado "
        "por esta corrida."
    )

    base = benchmark_dir()
    datasets = list_datasets(base)
    if not datasets:
        st.error(
            f"No encuentro datasets en `{base / 'datasets'}`. Define `BENCHMARK_DIR` apuntando a "
            "la carpeta de co_pqrs_benchmark."
        )
        return

    with st.form("benchmark-form"):
        col1, col2 = st.columns([2, 1])
        with col1:
            default_name = f"manual-{datetime.now(UTC).strftime('%Y%m%d-%H%M')}"
            run_name = st.text_input(
                "Nombre de la corrida",
                value=default_name,
                help="Aparece como run_name en el tablero. Solo letras, números, guion y guion bajo.",
            )
        with col2:
            source = st.selectbox(
                "Origen",
                options=("benchmark", "canario"),
                help="benchmark = dataset completo; canario = 8 casos dorados.",
            )
        labels = {p.name: p for p in datasets}
        preselect = 0
        for i, name in enumerate(labels):
            if (source == "canario" and "canario" in name) or (source != "canario" and "doble_cobro" in name):
                preselect = i
                break
        dataset_name = st.selectbox("Dataset", options=list(labels), index=preselect)
        publish = os.getenv("RABBITMQ_ENABLED", "false").strip().lower() in ("1", "true", "yes")
        st.caption(
            f"Agente: `{st.session_state.get('api_base_url', '')}` · "
            f"Publicación a RabbitMQ: {'activada' if publish else 'desactivada (solo NDJSON local)'} · "
            f"Tablero: `{osd_url()}`"
        )
        submitted = st.form_submit_button("Correr benchmark", type="primary", use_container_width=True)

    if not submitted:
        last = st.session_state.get("benchmark_last")
        if last:
            _render_result(**last)
        return

    clean_name = sanitize_run_name(run_name)
    status_area = st.empty()
    log_area = st.empty()
    with st.spinner(f"Corriendo {dataset_name} como '{clean_name}'..."):
        code, summary, ndjson = run_benchmark(
            run_name=clean_name,
            source=source,
            dataset=labels[dataset_name],
            log_area=log_area,
            status_area=status_area,
        )
    st.session_state["benchmark_last"] = {
        "run_name": clean_name,
        "source": source,
        "code": code,
        "summary": summary,
        "ndjson": str(ndjson),
    }
    _render_result(clean_name, source, code, summary, str(ndjson))


def _render_result(run_name: str, source: str, code: int, summary: dict[str, str], ndjson: str) -> None:
    if code != 0:
        st.error(f"El benchmark terminó con código {code}. Revisa el log de arriba y `{ndjson}`.")
        return
    if not summary:
        st.warning("La corrida terminó pero no encontré el resumen. Revisa el NDJSON.")
        return

    st.success(f"Corrida **{run_name}** terminada.")
    cols = st.columns(len(_SUMMARY_KEYS))
    for col, (key, label) in zip(cols, _SUMMARY_KEYS):
        col.metric(label, summary.get(key, "—"))
    st.link_button(
        "Ver esta corrida en el tablero",
        dashboard_link(run_name, source),
        use_container_width=True,
    )
    st.caption(f"NDJSON de la corrida: `{ndjson}`")
