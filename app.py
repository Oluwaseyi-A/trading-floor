"""Per-session Gradio viewer for the trading floor.

Phase 1 scope: the UI is session-isolated (each visitor gets their own
session_id, portfolios, and logs) but does not yet drive trading rounds —
that arrives with the Setup → Trading screens in Phase 3. For now the
panel renders whatever's already in the per-session DB rows.
"""

from typing import Optional

import gradio as gr
import pandas as pd
import plotly.express as px

from util import css, js, Color
from trading_floor import names, lastnames, short_model_names
from accounts import Account
from database import read_log, make_key
from session import cleanup_session, ensure_memory_dir, janitor_sweep

LOG_COLORS = {
    "trace": Color.WHITE,
    "agent": Color.CYAN,
    "function": Color.GREEN,
    "generation": Color.YELLOW,
    "response": Color.MAGENTA,
    "account": Color.RED,
}


def trader_title(name: str, model_name: str, lastname: str) -> str:
    return (
        f"<div style='text-align: center;font-size:34px;'>{name}"
        f"<span style='color:#ccc;font-size:24px;'> ({model_name}) - {lastname}</span></div>"
    )


def portfolio_html(account: Account) -> str:
    portfolio_value = account.calculate_portfolio_value() or 0.0
    pnl = account.calculate_profit_loss(portfolio_value) or 0.0
    color = "green" if pnl >= 0 else "red"
    arrow = "⬆" if pnl >= 0 else "⬇"
    return (
        f"<div style='text-align: center;background-color:{color};'>"
        f"<span style='font-size:32px'>${portfolio_value:,.0f}</span>"
        f"<span style='font-size:24px'>&nbsp;&nbsp;&nbsp;{arrow}&nbsp;${pnl:,.0f}</span></div>"
    )


def portfolio_chart(account: Account):
    df = pd.DataFrame(account.portfolio_value_time_series, columns=["datetime", "value"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    fig = px.line(df, x="datetime", y="value")
    fig.update_layout(
        height=300,
        margin=dict(l=40, r=20, t=20, b=40),
        xaxis_title=None,
        yaxis_title=None,
        paper_bgcolor="#bbb",
        plot_bgcolor="#dde",
    )
    fig.update_xaxes(tickformat="%m/%d", tickangle=45, tickfont=dict(size=8))
    fig.update_yaxes(tickfont=dict(size=8), tickformat=",.0f")
    return fig


def holdings_df(account: Account) -> pd.DataFrame:
    holdings = account.get_holdings()
    if not holdings:
        return pd.DataFrame(columns=["Symbol", "Quantity"])
    return pd.DataFrame([{"Symbol": s, "Quantity": q} for s, q in holdings.items()])


def transactions_df(account: Account) -> pd.DataFrame:
    transactions = account.list_transactions()
    if not transactions:
        return pd.DataFrame(columns=["Timestamp", "Symbol", "Quantity", "Price", "Rationale"])
    return pd.DataFrame(transactions)


def logs_html(session_id: Optional[str], name: str, previous: Optional[str] = None):
    if not session_id:
        return gr.update()
    key = make_key(name, session_id)
    logs = read_log(key, last_n=13)
    body = ""
    for ts, type_, message in logs:
        color = LOG_COLORS.get(type_, Color.WHITE).value
        body += f"<span style='color:{color}'>{ts} : [{type_}] {message}</span><br/>"
    response = f"<div style='height:250px; overflow-y:auto;'>{body}</div>"
    if response != previous:
        return response
    return gr.update()


def refresh_panel(session_id: Optional[str], name: str):
    if not session_id:
        return (gr.update(), gr.update(), gr.update(), gr.update())
    account = Account.get(name, session_id)
    return (
        portfolio_html(account),
        portfolio_chart(account),
        holdings_df(account),
        transactions_df(account),
    )


def make_panel(name: str, lastname: str, model_name: str, session_state: gr.State):
    name_state = gr.State(name)
    with gr.Column():
        gr.HTML(trader_title(name, model_name, lastname))
        with gr.Row():
            value_html = gr.HTML()
        with gr.Row():
            chart = gr.Plot(container=True, show_label=False)
        with gr.Row(variant="panel"):
            log = gr.HTML()
        with gr.Row():
            holdings = gr.Dataframe(
                headers=["Symbol", "Quantity"],
                row_count=(5, "dynamic"),
                col_count=2,
                max_height=300,
                elem_classes=["dataframe-fix-small"],
            )
        with gr.Row():
            transactions = gr.Dataframe(
                headers=["Timestamp", "Symbol", "Quantity", "Price", "Rationale"],
                row_count=(5, "dynamic"),
                col_count=5,
                max_height=300,
                elem_classes=["dataframe-fix"],
            )

    panel_timer = gr.Timer(value=120)
    panel_timer.tick(
        fn=refresh_panel,
        inputs=[session_state, name_state],
        outputs=[value_html, chart, holdings, transactions],
        show_progress="hidden",
        queue=False,
    )
    log_timer = gr.Timer(value=0.5)
    log_timer.tick(
        fn=logs_html,
        inputs=[session_state, name_state, log],
        outputs=[log],
        show_progress="hidden",
        queue=False,
    )

    return value_html, chart, log, holdings, transactions


def create_ui():
    ensure_memory_dir()
    janitor_sweep()

    with gr.Blocks(
        title="Trading Floor",
        css=css,
        js=js,
        theme=gr.themes.Default(primary_hue="sky"),
        fill_width=True,
    ) as ui:
        session_state = gr.State()
        panel_outputs: list[gr.components.Component] = []
        with gr.Row():
            for name, lastname, model_name in zip(names, lastnames, short_model_names):
                value_html, chart, log, holdings, transactions = make_panel(
                    name, lastname, model_name, session_state
                )
                panel_outputs.extend([value_html, chart, holdings, transactions])

        def init_session(request: gr.Request):
            session_id = request.session_hash if request and request.session_hash else ""
            outputs: list = [session_id]
            for name in names:
                if not session_id:
                    outputs.extend([gr.update(), gr.update(), gr.update(), gr.update()])
                    continue
                account = Account.get(name, session_id)
                outputs.extend(
                    [
                        portfolio_html(account),
                        portfolio_chart(account),
                        holdings_df(account),
                        transactions_df(account),
                    ]
                )
            return outputs

        ui.load(init_session, outputs=[session_state, *panel_outputs])

        def end_session(request: gr.Request):
            if request and request.session_hash:
                cleanup_session(request.session_hash)

        ui.unload(end_session)

    return ui


if __name__ == "__main__":
    ui = create_ui()
    ui.launch(server_name="0.0.0.0", server_port=7860, inbrowser=False)
