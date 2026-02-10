"""
Streamlit interface for Heylen Vastgoed contract generator pipeline.
Focuses on legal testing with 4 readiness statuses and jurist review levels.

Run: streamlit run app.py
"""

import io
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

from src.selector import select_clauses
from src.assembler_strict import assemble_strict
from src.generate import _validate_dossier_raw

# --- Constants ---

REPO_ROOT = Path(__file__).parent
LIBRARY_PATH = REPO_ROOT / "clause_library" / "clauses_v0.2.json"
LOCAL_OUT = REPO_ROOT / ".local_out"

DOSSIER_OPTIONS = {
    "dossier_001": "examples/dossier_001.json",
    "F1 - Happy path (financing confirmed)": "examples/fixtures/f1_happy_path_confirmed_financing.json",
    "F2 - Financiering lopend": "examples/fixtures/f2_financing_lopend.json",
    "F3 - Elektriciteit niet conform": "examples/fixtures/f3_electricity_niet_conform.json",
    "F4 - Bodem risico": "examples/fixtures/f4_bodem_risico.json",
    "F5 - Bouwjaar 2005 (no asbest)": "examples/fixtures/f5_bouwjaar_2005_no_asbest.json",
    "F6 - Missing required fields": "examples/fixtures/f6_missing_required_field.json",
}

_RRN_PATTERN = re.compile(r"\d{2}\.\d{2}\.\d{2}-\d{3}\.\d{2}")

STATUS_CONFIG = {
    "DRAFT_BLOCKED": {
        "color": "red",
        "icon": "🔴",
        "label": "BLOCKED",
        "description": "Niet genereerbaar (data ontbreekt)",
    },
    "DRAFT_REVIEW_REQUIRED": {
        "color": "orange",
        "icon": "🟠",
        "label": "REVIEW REQUIRED",
        "description": "Review verplicht",
    },
    "DRAFT_REVIEW_RECOMMENDED": {
        "color": "blue",
        "icon": "🔵",
        "label": "REVIEW RECOMMENDED",
        "description": "OK (review aanbevolen)",
    },
    "DRAFT_OK": {
        "color": "green",
        "icon": "🟢",
        "label": "OK",
        "description": "Geen review nodig",
    },
}


def _scan_rrn(text: str) -> list[str]:
    """Scan text for Belgian RRN patterns (excluding TEST_RRN_ values)."""
    matches = _RRN_PATTERN.findall(text)
    return [m for m in matches if f"TEST_RRN_{m}" not in text]


def _run_pipeline(dossier: dict) -> tuple[dict, dict, dict]:
    """Run pipeline in-process. Returns (validation, selection, assembled)."""
    with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
        library = json.load(f)
    validation = _validate_dossier_raw(dossier)
    selection = select_clauses(dossier, library)
    assembled = assemble_strict(dossier, selection)
    return validation, selection, assembled


def _build_review_pack_zip(dossier: dict, selection: dict, assembled: dict) -> bytes:
    """Build a review pack zip in memory."""
    dossier_id = dossier.get("dossier_id", "unknown")
    jurist_review = selection.get("jurist_review_clauses", {})

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f"{dossier_id}/assembled.json",
            json.dumps(assembled, ensure_ascii=False, indent=2),
        )
        zf.writestr(
            f"{dossier_id}/selection.json",
            json.dumps(selection, ensure_ascii=False, indent=2),
        )
        risk_flags_data = {
            "dossier_id": dossier_id,
            "readiness_status": assembled["readiness_status"],
            "confidence_score": assembled["confidence_score"],
            "risk_flags": selection["risk_flags"],
            "risk_summary": {
                "high": selection["summary"]["risk_flags_high"],
                "medium": selection["summary"]["risk_flags_medium"],
                "low": selection["summary"]["risk_flags_low"],
            },
            "next_actions": assembled["next_actions"],
        }
        zf.writestr(
            f"{dossier_id}/risk_flags.json",
            json.dumps(risk_flags_data, ensure_ascii=False, indent=2),
        )
        jurist_review_data = {
            "dossier_id": dossier_id,
            "jurist_required_count": selection["summary"].get("jurist_required_count", 0),
            "jurist_recommended_count": selection["summary"].get("jurist_recommended_count", 0),
            "jurist_required": jurist_review.get("required", []),
            "jurist_recommended": jurist_review.get("recommended", []),
        }
        zf.writestr(
            f"{dossier_id}/jurist_review.json",
            json.dumps(jurist_review_data, ensure_ascii=False, indent=2),
        )
        zf.writestr(
            f"{dossier_id}/contract.txt",
            assembled["document_text"],
        )
    buf.seek(0)
    return buf.read()


# --- Page config ---

st.set_page_config(
    page_title="Heylen Contract Generator",
    layout="wide",
)

st.title("Heylen Vastgoed — Contract Generator")

# --- Session state init ---

if "dossier_json" not in st.session_state:
    st.session_state.dossier_json = ""
if "results" not in st.session_state:
    st.session_state.results = None

# --- Layout ---

left, right = st.columns([1, 2])

with left:
    st.subheader("Dossier")

    selected_label = st.selectbox("Select dossier", list(DOSSIER_OPTIONS.keys()))

    if st.button("Load", use_container_width=True):
        path = REPO_ROOT / DOSSIER_OPTIONS[selected_label]
        with open(path, "r", encoding="utf-8") as f:
            st.session_state.dossier_json = f.read()
        st.session_state.results = None

    dossier_text = st.text_area(
        "Dossier JSON (editable)",
        value=st.session_state.dossier_json,
        height=400,
        key="editor",
    )
    st.session_state.dossier_json = dossier_text

    col_gen, col_pack = st.columns(2)
    with col_gen:
        generate_clicked = st.button("Generate", use_container_width=True, type="primary")
    with col_pack:
        pack_clicked = st.button("Build review pack", use_container_width=True)

    if generate_clicked and dossier_text.strip():
        try:
            dossier = json.loads(dossier_text)
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}")
            dossier = None

        if dossier:
            validation, selection, assembled = _run_pipeline(dossier)
            st.session_state.results = {
                "dossier": dossier,
                "validation": validation,
                "selection": selection,
                "assembled": assembled,
            }

    if generate_clicked and not dossier_text.strip():
        st.warning("Load a dossier first.")

with right:
    results = st.session_state.results

    if results is None:
        st.info("Load a dossier and click Generate to see results.")
    else:
        dossier = results["dossier"]
        assembled = results["assembled"]
        selection = results["selection"]
        validation = results["validation"]

        # --- RRN scan ---
        rrn_hits = _scan_rrn(json.dumps(dossier))
        if rrn_hits:
            st.warning(
                f"GDPR waarschuwing: {len(rrn_hits)} mogelijke rijksregisternummer(s) "
                f"gedetecteerd in dossier: {', '.join(rrn_hits)}"
            )

        # --- Status badge ---
        status = assembled["readiness_status"]
        cfg = STATUS_CONFIG.get(status, STATUS_CONFIG["DRAFT_OK"])
        st.markdown(
            f"### {cfg['icon']} {status}\n{cfg['description']}"
        )

        # --- Metrics row ---
        m1, m2, m3, m4, m5 = st.columns(5)
        summary = selection["summary"]
        m1.metric("Confidence", assembled["confidence_score"])
        m2.metric("High risk", summary["risk_flags_high"])
        m3.metric("Medium risk", summary["risk_flags_medium"])
        m4.metric("Jurist required", summary["jurist_required_count"])
        m5.metric("Jurist recommended", summary["jurist_recommended_count"])

        # --- Next actions ---
        if assembled["next_actions"]:
            st.markdown("**Next actions:**")
            for action in assembled["next_actions"]:
                st.markdown(f"- {action}")

        # --- Status detail ---
        if status == "DRAFT_BLOCKED":
            st.error("Unresolved placeholders:")
            for u in assembled["unresolved_placeholders"]:
                st.markdown(f"- `{u['placeholder']}` (clause: {u['clause_id']})")
        elif status == "DRAFT_REVIEW_REQUIRED":
            high_flags = [f for f in selection["risk_flags"] if f["risk_level"] == "high"]
            if high_flags:
                st.warning("High risk flags:")
                for f in high_flags:
                    st.markdown(f"- **{f['clause_id']}**: {f['flag'][:120]}...")
            req = selection["jurist_review_clauses"].get("required", [])
            if req:
                st.warning(f"Jurist required clauses: {', '.join(req)}")
        elif status == "DRAFT_REVIEW_RECOMMENDED":
            rec = selection["jurist_review_clauses"].get("recommended", [])
            if rec:
                st.info(f"Jurist recommended clauses: {', '.join(rec)}")

        # --- Tabs ---
        tab_contract, tab_flags, tab_jurist, tab_selection = st.tabs(
            ["Contract", "Flags", "Jurist review", "Selection"]
        )

        with tab_contract:
            contract_text = assembled["document_text"]
            st.text_area("Contract text", value=contract_text, height=400, disabled=True)
            st.download_button(
                "Download contract.txt",
                data=contract_text,
                file_name=f"{dossier.get('dossier_id', 'contract')}.contract.txt",
                mime="text/plain",
            )

        with tab_flags:
            flags = assembled["flags"]
            if flags:
                rows = []
                for f in flags:
                    row = {
                        "type": f.get("type", ""),
                        "risk_level": f.get("risk_level", ""),
                        "clause_id": f.get("clause_id", ""),
                        "detail": f.get("detail", f.get("placeholder", "")),
                    }
                    rows.append(row)
                st.dataframe(rows, use_container_width=True)
            else:
                st.success("No flags.")

        with tab_jurist:
            jrc = selection["jurist_review_clauses"]
            st.markdown("#### Required")
            if jrc.get("required"):
                for cid in jrc["required"]:
                    st.markdown(f"- **{cid}**")
            else:
                st.markdown("_(geen)_")

            st.markdown("#### Recommended")
            if jrc.get("recommended"):
                for cid in jrc["recommended"]:
                    st.markdown(f"- {cid}")
            else:
                st.markdown("_(geen)_")

            st.markdown("---")
            st.markdown("#### Activation evaluation")
            ae = selection["activation_evaluation"]
            active_count = sum(1 for e in ae if e["evaluated"])
            inactive_count = sum(1 for e in ae if not e["evaluated"])
            st.markdown(f"Active: **{active_count}** / Inactive: **{inactive_count}** / Total: **{len(ae)}**")

            with st.expander("Per-clause evaluation detail"):
                for e in ae:
                    icon = "+" if e["evaluated"] else "-"
                    st.markdown(
                        f"`[{icon}]` **{e['clause_id']}** — {e['reason']}"
                    )

        with tab_selection:
            st.markdown("#### Selected clauses")
            st.markdown(f"{len(selection['selected_clause_ids'])} clauses selected")
            for cid in selection["selected_clause_ids"]:
                st.markdown(f"- {cid}")

            st.markdown("#### Skipped clauses")
            skipped = selection["skipped_clause_ids"]
            if skipped:
                for s in skipped:
                    st.markdown(f"- **{s['id']}**: {s['reason']}")
            else:
                st.markdown("_(geen)_")

        # --- Downloads ---
        st.markdown("---")
        st.markdown("### Downloads")
        dl1, dl2, dl3 = st.columns(3)
        with dl1:
            st.download_button(
                "assembled.json",
                data=json.dumps(assembled, ensure_ascii=False, indent=2),
                file_name=f"{dossier.get('dossier_id', 'out')}.assembled.json",
                mime="application/json",
            )
        with dl2:
            st.download_button(
                "selection.json",
                data=json.dumps(selection, ensure_ascii=False, indent=2),
                file_name=f"{dossier.get('dossier_id', 'out')}.selection.json",
                mime="application/json",
            )
        with dl3:
            zip_bytes = _build_review_pack_zip(dossier, selection, assembled)
            st.download_button(
                "review_pack.zip",
                data=zip_bytes,
                file_name=f"{dossier.get('dossier_id', 'out')}_review_pack.zip",
                mime="application/zip",
            )
