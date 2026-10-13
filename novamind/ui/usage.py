"""ui / usage responsibilities extracted from the Streamlit launcher."""
import streamlit as st
from novamind.ui.state import _session_cost, _usage_totals
from services.auth_service import protect_state


def _render_usage() -> None:
    protect_state(st.session_state)
    st.markdown("### 📊 Token Usage")
    totals = _usage_totals()
    cost = _session_cost()
    cost_label = "Unknown" if cost is None else f"${cost:.8f}"
    st.markdown(
        f'<div class="nm-token-card">'
        f'📥 Known input &nbsp;<span class="val">{st.session_state.total_input_tokens:,}</span> tokens<br>'
        f'📤 Known output &nbsp;<span class="val">{st.session_state.total_output_tokens:,}</span> tokens<br>'
        f'💵 Configured-rate estimate &nbsp;<span class="cost">{cost_label}</span>'
        f'</div>', unsafe_allow_html=True,
    )
    st.caption("Bedrock-reported tokens. Costs use unverified configured USD rates, not an AWS bill. Totals cover this conversation, including summaries.")
    if totals["unknown_cost"]:
        st.caption(f"Known cost subtotal: ${totals['known_cost']:.8f}; "
                   f"{totals['unknown_cost']} accounting record(s) with unknown cost; "
                   f"{totals['unknown_usage']} with missing token counts.")
    if st.session_state.usage_ledger:
        with st.expander("Request usage details"):
            rows = []
            for request in st.session_state.usage_ledger:
                for record in request["attempts"]:
                    rows.append({
                        "Request": record.request_id, "Attempt": record.attempt,
                        "Time": request["timestamp"], "Operation": record.operation,
                        "Model": record.model_id, "Region": record.region,
                        "Response": request["status"], "Invocation": record.status,
                        "Stop reason": record.stop_reason or "Unknown",
                        "Input tokens": record.input_tokens if record.input_tokens is not None else "Unknown",
                        "Output tokens": record.output_tokens if record.output_tokens is not None else "Unknown",
                        "Estimated USD": str(record.cost_usd) if record.cost_usd is not None else "Unknown",
                        "Note": record.unknown_reason or record.pricing_source,
                    })
                if not request["attempts"]:
                    rows.append({"Time": request["timestamp"], "Operation": request["operation"],
                                 "Response": request["status"], "Note": "No invocation metadata; usage and cost unknown"})
            # Strings avoid mixed numeric/string Arrow columns for unknown values.
            st.dataframe([{k: str(v) for k, v in row.items()} for row in rows], hide_index=True)
