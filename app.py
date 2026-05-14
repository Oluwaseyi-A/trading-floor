"""Hosted Gradio app for the Trading Floor demo.

Two-screen flow:
- Setup: starting balance + 4 persona slots (default / custom toggle) + Launch.
- Trading: live 4-column dashboard with Run now / Auto-run / Pause / Reset
  and session-cap status.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import gradio as gr
import pandas as pd
import plotly.express as px
from agents import add_trace_processor

from accounts import Account, DEFAULT_INITIAL_BALANCE
from database import read_log, make_key
from personas import (
    PersonaSlot,
    available_models,
    default_model,
    default_slots,
    start_session as personas_start_session,
    validate_slots,
    MIN_BALANCE,
    MAX_BALANCE,
)
from session import cleanup_session, ensure_memory_dir, janitor_sweep, session_caps
from session_state import (
    RoundState,
    can_run,
    drop_state,
    get_state,
    remaining_runs,
    remaining_seconds,
    upsert_state,
)
from tracers import LogTracer
from traders import Trader
from util import css, js, Color


LOG_COLORS = {
    "trace": Color.WHITE,
    "agent": Color.CYAN,
    "function": Color.GREEN,
    "generation": Color.YELLOW,
    "response": Color.MAGENTA,
    "account": Color.RED,
}

# Global tracer — relies on the per-trace registry in tracers.py to route
# log writes to the right session+trader rows.
_TRACE_REGISTERED = False


def _ensure_tracer():
    global _TRACE_REGISTERED
    if not _TRACE_REGISTERED:
        add_trace_processor(LogTracer())
        _TRACE_REGISTERED = True


# ---------------------------------------------------------------------------
# Read-side helpers (DB → UI)
# ---------------------------------------------------------------------------

def _portfolio_html(account: Account) -> str:
    pv = account.calculate_portfolio_value() or 0.0
    pnl = account.calculate_profit_loss(pv) or 0.0
    polarity = "positive" if pnl >= 0 else "negative"
    arrow = "▲" if pnl >= 0 else "▼"
    return (
        f"<div class='tf-portfolio {polarity}'>"
        f"<span class='value'>${pv:,.0f}</span>"
        f"<span class='pnl {polarity}'>{arrow} ${pnl:,.0f}</span></div>"
    )


def _portfolio_chart(account: Account):
    df = pd.DataFrame(account.portfolio_value_time_series, columns=["datetime", "value"])
    if df.empty:
        df = pd.DataFrame([{"datetime": pd.Timestamp.now(), "value": account.balance}])
    df["datetime"] = pd.to_datetime(df["datetime"])
    fig = px.line(df, x="datetime", y="value")
    fig.update_layout(
        height=240,
        margin=dict(l=40, r=20, t=10, b=40),
        xaxis_title=None,
        yaxis_title=None,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(30, 41, 59, 0.5)",
        font=dict(color="#cbd5e1"),
    )
    fig.update_traces(line=dict(color="#38bdf8", width=2))
    fig.update_xaxes(tickformat="%m/%d %H:%M", tickangle=45, tickfont=dict(size=9), gridcolor="#334155")
    fig.update_yaxes(tickfont=dict(size=9), tickformat=",.0f", gridcolor="#334155")
    return fig


def _holdings_df(account: Account) -> pd.DataFrame:
    holdings = account.get_holdings()
    if not holdings:
        return pd.DataFrame(columns=["Symbol", "Quantity"])
    return pd.DataFrame([{"Symbol": s, "Quantity": q} for s, q in holdings.items()])


def _transactions_df(account: Account) -> pd.DataFrame:
    transactions = account.list_transactions()
    if not transactions:
        return pd.DataFrame(columns=["Timestamp", "Symbol", "Quantity", "Price", "Rationale"])
    return pd.DataFrame(transactions)


def _logs_html(session_id: str, trader_name: str, previous: Optional[str] = None):
    if not session_id:
        return gr.update()
    key = make_key(trader_name, session_id)
    body = ""
    for ts, type_, message in read_log(key, last_n=14):
        color = LOG_COLORS.get(type_, Color.WHITE).value
        body += f"<span style='color:{color}'>{ts} <span style='color:#64748b'>[{type_}]</span> {message}</span><br/>"
    response = f"<div class='tf-log'>{body}</div>"
    if response == previous:
        return gr.update()
    return response


def _trader_title(slot: PersonaSlot, model_label: str) -> str:
    return (
        f"<div class='tf-trader-title'>{slot.name}</div>"
        f"<div class='tf-trader-meta'>{slot.lastname} · {model_label}</div>"
    )


def _refresh_panel(session_id: str, trader_name: str):
    if not session_id:
        return gr.update(), gr.update(), gr.update(), gr.update()
    account = Account.get(trader_name, session_id)
    return (
        _portfolio_html(account),
        _portfolio_chart(account),
        _holdings_df(account),
        _transactions_df(account),
    )


def _status_html(state: Optional[RoundState]) -> str:
    if state is None or not state.traders:
        return "<span class='tf-status idle'>Configure traders to begin.</span>"

    runs_left = remaining_runs(state)
    secs_left = remaining_seconds(state)
    bits: list[str] = []
    bits.append(f"Round {state.runs_completed}")
    if runs_left >= 0:
        bits.append(f"{runs_left} run(s) left")
    if secs_left >= 0:
        mm, ss = divmod(secs_left, 60)
        bits.append(f"⏱ {mm}:{ss:02d} left")

    cls = "tf-status"
    label = "Idle"
    if state.is_running:
        cls += " running"
        label = "Running…"
    elif state.last_error:
        cls += " error"
        label = f"Error: {state.last_error}"

    meta = " · ".join(bits)
    return f"<span class='{cls}'>{label}</span> &nbsp; <span style='color:#94a3b8;font-size:13px'>{meta}</span>"


def _model_label(model_id: str) -> str:
    for label, mid in available_models():
        if mid == model_id:
            return label
    return model_id


# ---------------------------------------------------------------------------
# Setup screen helpers
# ---------------------------------------------------------------------------

def _read_slot_inputs(
    use_default: bool,
    name: str,
    lastname: str,
    model_id: str,
    strategy: str,
    default_slot: PersonaSlot,
) -> PersonaSlot:
    if use_default:
        return PersonaSlot(
            name=default_slot.name,
            lastname=default_slot.lastname,
            model_name=default_slot.model_name,
            strategy=default_slot.strategy,
            is_custom=False,
        )
    return PersonaSlot(
        name=(name or "").strip() or default_slot.name,
        lastname=(lastname or "").strip() or default_slot.lastname,
        model_name=model_id or default_model(),
        strategy=(strategy or "").strip(),
        is_custom=True,
    )


# ---------------------------------------------------------------------------
# Trading-screen actions
# ---------------------------------------------------------------------------

async def _run_round(session_id: str) -> str:
    """Run one round across all 4 traders. Returns user-visible error string ('' if ok)."""
    state = get_state(session_id)
    if state is None:
        return "Session not initialised."

    ok, reason = can_run(state)
    if not ok:
        return reason

    state.is_running = True
    state.last_error = None
    try:
        await asyncio.gather(*[trader.run() for trader in state.traders])
        state.runs_completed += 1
        return ""
    except Exception as exc:  # noqa: BLE001 — UI surface for any failure
        state.last_error = str(exc)[:200]
        return state.last_error
    finally:
        state.is_running = False


# ---------------------------------------------------------------------------
# UI assembly
# ---------------------------------------------------------------------------

def _build_setup_slot(default_slot: PersonaSlot, model_choices: list[tuple[str, str]]):
    """Returns a dict of components for one slot."""
    with gr.Accordion(label=f"{default_slot.name} · {default_slot.lastname}", open=False, elem_classes=["tf-card"]):
        with gr.Row():
            use_default = gr.Checkbox(value=True, label="Use default persona", interactive=True)
        with gr.Group(visible=False) as custom_group:
            name_in = gr.Textbox(label="Trader name", value=default_slot.name, max_lines=1)
            lastname_in = gr.Textbox(label="Tagline / lastname", value=default_slot.lastname, max_lines=1)
            model_in = gr.Dropdown(
                choices=model_choices,
                value=default_slot.model_name,
                label="Model",
                interactive=True,
            )
            strategy_in = gr.Textbox(
                label="Strategy",
                value=default_slot.strategy,
                lines=8,
                placeholder="Describe how this trader thinks (≥ 50 chars works best).",
            )

    def _toggle(is_default):
        return gr.update(visible=not is_default)

    use_default.change(fn=_toggle, inputs=[use_default], outputs=[custom_group])

    return {
        "use_default": use_default,
        "name": name_in,
        "lastname": lastname_in,
        "model": model_in,
        "strategy": strategy_in,
        "default": default_slot,
    }


def create_ui():
    ensure_memory_dir()
    janitor_sweep()
    _ensure_tracer()

    max_runs, max_seconds = session_caps()
    model_choices = available_models() or [("GPT 4o mini", "gpt-4o-mini")]
    defaults = default_slots()
    cap_blurb = (
        f"Free public demo — each session is capped at "
        f"{max_seconds // 60 if max_seconds else '∞'} minutes or "
        f"{max_runs if max_runs else '∞'} trading rounds, whichever comes first."
    )

    with gr.Blocks(
        title="Trading Floor",
        css=css,
        js=js,
        theme=gr.themes.Default(primary_hue="sky", neutral_hue="slate"),
        fill_width=True,
    ) as ui:
        session_state = gr.State("")  # session_hash captured on load

        # ---------------- Setup screen ----------------
        with gr.Group(visible=True) as setup_screen:
            gr.HTML(
                "<div class='tf-hero'>"
                "<h1>📈 Trading Floor</h1>"
                "<p>Four AI traders compete on a simulated market — each one researches, "
                "thinks, and places trades autonomously. Configure their starting balance and "
                "personas, then watch them go.</p>"
                f"<p style='color:#64748b;font-size:13px'>{cap_blurb}</p>"
                "</div>"
            )

            with gr.Column(elem_classes=["tf-card"]):
                balance_in = gr.Number(
                    label="Starting balance (USD)",
                    value=int(DEFAULT_INITIAL_BALANCE),
                    minimum=int(MIN_BALANCE),
                    maximum=int(MAX_BALANCE),
                    precision=0,
                )

            gr.HTML("<h2 style='margin: 24px 0 12px;font-size:20px;'>Persona slots</h2>")

            slot_components = [
                _build_setup_slot(defaults[i], model_choices) for i in range(4)
            ]

            launch_btn = gr.Button("Launch trading floor →", variant="primary", size="lg")
            setup_status = gr.Markdown("", visible=False)

        # ---------------- Trading screen ----------------
        with gr.Group(visible=False) as trading_screen:
            with gr.Row(elem_classes=["tf-toolbar"]):
                run_btn = gr.Button("▶ Run now", variant="primary")
                pause_btn = gr.Button("⏸ Pause", variant="secondary")
                reset_btn = gr.Button("↺ Reset / new session", variant="secondary")
                auto_toggle = gr.Checkbox(label="Auto-run", value=False, interactive=True)
                auto_minutes = gr.Number(label="every (min)", value=5, minimum=1, maximum=15, precision=0, scale=0)
                status_html = gr.HTML(_status_html(None), elem_classes=["tf-meta"])

            panel_value_htmls: list[gr.HTML] = []
            panel_charts: list[gr.Plot] = []
            panel_logs: list[gr.HTML] = []
            panel_holdings: list[gr.Dataframe] = []
            panel_txns: list[gr.Dataframe] = []
            panel_names: list[gr.State] = []
            panel_titles: list[gr.HTML] = []
            with gr.Row():
                for default_slot in defaults:
                    with gr.Column(elem_classes=["tf-card"]):
                        title_html = gr.HTML(_trader_title(default_slot, _model_label(default_slot.model_name)))
                        value_html = gr.HTML(_portfolio_html(Account(
                            name=default_slot.name.lower(), session_id="", balance=DEFAULT_INITIAL_BALANCE,
                            strategy="", holdings={}, transactions=[], portfolio_value_time_series=[],
                        )))
                        chart = gr.Plot(container=False, show_label=False)
                        log = gr.HTML("<div class='tf-log'></div>")
                        holdings = gr.Dataframe(
                            headers=["Symbol", "Quantity"], row_count=(5, "dynamic"),
                            col_count=2, max_height=220, elem_classes=["dataframe-fix-small"],
                        )
                        transactions = gr.Dataframe(
                            headers=["Timestamp", "Symbol", "Quantity", "Price", "Rationale"],
                            row_count=(5, "dynamic"), col_count=5, max_height=240,
                            elem_classes=["dataframe-fix"],
                        )
                    panel_titles.append(title_html)
                    panel_value_htmls.append(value_html)
                    panel_charts.append(chart)
                    panel_logs.append(log)
                    panel_holdings.append(holdings)
                    panel_txns.append(transactions)
                    panel_names.append(gr.State(default_slot.name))

            # Polling timers — keep dashboards fresh from the DB rows that
            # accounts_server is updating from inside trader.run().
            panel_timer = gr.Timer(value=15)
            log_timer = gr.Timer(value=1.0)
            status_timer = gr.Timer(value=1.0)
            auto_timer = gr.Timer(value=300, active=False)  # rewired on toggle

        # ---------------- Wiring ----------------

        def _init(request: gr.Request):
            sid = request.session_hash if request and request.session_hash else ""
            return sid

        ui.load(_init, outputs=[session_state])

        # Per-panel refresh
        for i in range(4):
            panel_timer.tick(
                fn=_refresh_panel,
                inputs=[session_state, panel_names[i]],
                outputs=[panel_value_htmls[i], panel_charts[i], panel_holdings[i], panel_txns[i]],
                show_progress="hidden",
                queue=False,
            )
            log_timer.tick(
                fn=_logs_html,
                inputs=[session_state, panel_names[i], panel_logs[i]],
                outputs=[panel_logs[i]],
                show_progress="hidden",
                queue=False,
            )

        # Toolbar status refresh
        def _refresh_status(session_id):
            return _status_html(get_state(session_id))

        status_timer.tick(fn=_refresh_status, inputs=[session_state], outputs=[status_html], queue=False, show_progress="hidden")

        # ----- Launch handler -----
        slot_input_components: list[gr.components.Component] = []
        for s in slot_components:
            slot_input_components.extend([s["use_default"], s["name"], s["lastname"], s["model"], s["strategy"]])

        def _launch(session_id, balance, *slot_inputs):
            if not session_id:
                return (
                    gr.update(),  # setup_screen
                    gr.update(),  # trading_screen
                    gr.update(value="⚠️ Could not read your session — try reloading the page.", visible=True),
                    *[gr.update() for _ in range(4)],  # titles
                )

            try:
                balance = float(balance)
            except (TypeError, ValueError):
                balance = DEFAULT_INITIAL_BALANCE

            slots: list[PersonaSlot] = []
            for i in range(4):
                use_default, name, lastname, model_id, strategy = slot_inputs[i * 5 : i * 5 + 5]
                slots.append(_read_slot_inputs(use_default, name, lastname, model_id, strategy, defaults[i]))

            result = validate_slots(slots, balance)
            if not result.ok:
                msg = "**Please fix:**\n" + "\n".join(f"- {e}" for e in result.errors)
                if result.warnings:
                    msg += "\n\n**Nudges:**\n" + "\n".join(f"- {w}" for w in result.warnings)
                return (
                    gr.update(),
                    gr.update(),
                    gr.update(value=msg, visible=True),
                    *[gr.update() for _ in range(4)],
                )

            state = upsert_state(session_id)
            state.slots = slots
            state.initial_balance = balance
            state.runs_completed = 0
            state.started_at = time.time()
            state.last_error = None
            state.auto_run_enabled = False
            state.is_running = False
            state.traders = [
                Trader(slot.name, slot.lastname, slot.model_name, session_id=session_id) for slot in slots
            ]

            personas_start_session(session_id, slots, balance)

            title_updates = [
                gr.update(value=_trader_title(slot, _model_label(slot.model_name))) for slot in slots
            ]
            return (
                gr.update(visible=False),    # hide setup
                gr.update(visible=True),     # show trading
                gr.update(value="", visible=False),
                *title_updates,
            )

        launch_btn.click(
            fn=_launch,
            inputs=[session_state, balance_in, *slot_input_components],
            outputs=[setup_screen, trading_screen, setup_status, *panel_titles],
        )

        # ----- Run now -----
        async def _run_now(session_id):
            err = await _run_round(session_id)
            return _status_html(get_state(session_id)) if not err else _status_html(get_state(session_id))

        run_btn.click(
            fn=_run_now,
            inputs=[session_state],
            outputs=[status_html],
        )

        # ----- Auto-run toggle -----
        def _set_auto(session_id, enabled: bool, minutes: float):
            try:
                interval = max(1, int(minutes or 1))
            except (TypeError, ValueError):
                interval = 5
            state = get_state(session_id)
            if state is None:
                return gr.update(active=False)
            state.auto_run_enabled = bool(enabled)
            state.auto_run_interval_min = interval
            return gr.update(value=interval * 60, active=bool(enabled))

        auto_toggle.change(fn=_set_auto, inputs=[session_state, auto_toggle, auto_minutes], outputs=[auto_timer])
        auto_minutes.change(fn=_set_auto, inputs=[session_state, auto_toggle, auto_minutes], outputs=[auto_timer])

        async def _auto_tick(session_id):
            state = get_state(session_id)
            if state is None or not state.auto_run_enabled:
                return _status_html(state)
            ok, _ = can_run(state)
            if not ok:
                state.auto_run_enabled = False
                return _status_html(state)
            await _run_round(session_id)
            return _status_html(get_state(session_id))

        auto_timer.tick(fn=_auto_tick, inputs=[session_state], outputs=[status_html])

        # ----- Pause: disables auto-run without resetting state -----
        def _pause(session_id):
            state = get_state(session_id)
            if state:
                state.auto_run_enabled = False
            return gr.update(value=False), gr.update(active=False), _status_html(state)

        pause_btn.click(fn=_pause, inputs=[session_state], outputs=[auto_toggle, auto_timer, status_html])

        # ----- Reset: wipe state and go back to Setup -----
        def _reset(session_id):
            if session_id:
                cleanup_session(session_id)
                drop_state(session_id)
            return (
                gr.update(visible=True),   # setup_screen
                gr.update(visible=False),  # trading_screen
                gr.update(value=False),    # auto_toggle
                gr.update(active=False),   # auto_timer
                _status_html(None),
            )

        reset_btn.click(
            fn=_reset,
            inputs=[session_state],
            outputs=[setup_screen, trading_screen, auto_toggle, auto_timer, status_html],
        )

        # ----- Cleanup on tab close -----
        def _end(request: gr.Request):
            if request and request.session_hash:
                cleanup_session(request.session_hash)
                drop_state(request.session_hash)

        ui.unload(_end)

    return ui


if __name__ == "__main__":
    ui = create_ui()
    ui.queue().launch(server_name="0.0.0.0", server_port=7860, inbrowser=False)
