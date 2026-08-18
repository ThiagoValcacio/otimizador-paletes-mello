from __future__ import annotations

from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st

from optimizer import OptimizationResult, solve_pallet_plan
from sample_data import make_sample_data, synchronize_data


st.set_page_config(
    page_title="Planejamento de Paletes — Mello",
    page_icon="🚛",
    layout="wide",
)


def brl(value: float) -> str:
    formatted = f"{value:,.2f}"
    return "R$ " + formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def excel_result(result: OptimizationResult) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result.schedule.to_excel(writer, sheet_name="Plano diário", index=False)
        result.cost_breakdown.to_excel(writer, sheet_name="Custos", index=False)
        result.obligations.to_excel(writer, sheet_name="Obrigações", index=False)
        result.vouchers.to_excel(writer, sheet_name="Vales", index=False)
        result.inventory.to_excel(writer, sheet_name="Estoque Mello", index=False)
        result.fleet_usage.to_excel(writer, sheet_name="Uso da frota", index=False)
    return output.getvalue()


def editor(name: str, title: str, help_text: str | None = None, **kwargs) -> pd.DataFrame:
    st.subheader(title)
    if help_text:
        st.caption(help_text)
    edited = st.data_editor(
        st.session_state.app_data[name],
        key=f"editor_{name}",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        **kwargs,
    )
    st.session_state.app_data[name] = edited.copy()
    return edited


def reset_editors(names: list[str]) -> None:
    for name in names:
        st.session_state.pop(f"editor_{name}", None)


if "planning_start" not in st.session_state:
    st.session_state.planning_start = date.today()
if "horizon_days" not in st.session_state:
    st.session_state.horizon_days = 7
if "app_data" not in st.session_state:
    st.session_state.app_data = make_sample_data(
        st.session_state.planning_start, st.session_state.horizon_days
    )


with st.sidebar:
    st.header("Horizonte")
    planning_start = st.date_input(
        "Primeiro dia",
        value=st.session_state.planning_start,
        format="DD/MM/YYYY",
    )
    horizon_days = st.number_input(
        "Quantidade de dias",
        min_value=1,
        max_value=365,
        value=int(st.session_state.horizon_days),
        step=1,
    )
    st.session_state.planning_start = planning_start
    st.session_state.horizon_days = int(horizon_days)

    if st.button("Restaurar exemplo", width="stretch"):
        st.session_state.app_data = make_sample_data(planning_start, int(horizon_days))
        st.session_state.pop("last_result", None)
        reset_editors(list(st.session_state.app_data))
        st.rerun()

    st.divider()
    st.markdown(
        """
        **Premissas desta versão**

        - datas inclusivas;
        - antecedência em dias corridos;
        - coleta parcial permitida;
        - palete coletado entra na Mello no dia seguinte;
        - uma viagem atende um único destino;
        - tipos iguais são intercambiáveis.
        """
    )


st.title("Planejamento diário de paletes")
st.caption(
    "Decide quando coletar paletes retidos nos clientes e quando devolvê-los aos "
    "embarcadores, minimizando fretes, permanência, armazenagem, perdas e débitos."
)

with st.expander("Como o vale é tratado", expanded=False):
    st.markdown(
        """
        O vale **não quita a obrigação**. Ele registra uma quantidade de paletes físicos
        retida no cliente e uma data até a qual a Mello pode buscá-la. Enquanto o lote
        permanecer no cliente, incide `custo_cliente_dia_palete`. Se não for coletado até
        o vencimento, incide `custo_perda_palete` sobre cada palete perdido. A obrigação
        com o embarcador só diminui quando o palete é entregue a ele.
        """
    )

tab_base, tab_vouchers, tab_transport, tab_results = st.tabs(
    ["Cadastros e saldos", "Vales nos clientes", "Frota e transportes", "Resultados"]
)

with tab_base:
    left, right = st.columns(2)
    with left:
        editor(
            "pallet_types",
            "Tipos de palete",
            "Inclua quantos tipos forem necessários.",
            column_config={
                "custo_estoque_dia_palete": st.column_config.NumberColumn(
                    "Custo estoque/dia/palete", min_value=0.0, format="R$ %.2f"
                )
            },
        )
        editor(
            "stock",
            "Estoque físico inicial na Mello",
            column_config={
                "quantidade_mello": st.column_config.NumberColumn(
                    "Quantidade na Mello", min_value=0, step=1
                )
            },
        )
    with right:
        editor(
            "vehicles",
            "Tipos de veículo",
            "A capacidade é de paletes vazios por viagem e deve ser ajustada à operação.",
            column_config={
                "capacidade_paletes": st.column_config.NumberColumn(
                    "Capacidade de paletes", min_value=1, step=1
                )
            },
        )

    editor(
        "obligations",
        "Obrigações consolidadas por embarcador e tipo",
        "Não subtraia os vales: o vale representa palete ainda retido no cliente.",
        column_config={
            "quantidade_devida": st.column_config.NumberColumn(
                "Quantidade devida", min_value=0, step=1
            )
        },
    )
    editor(
        "threats",
        "Ameaças de débito integral",
        "Se faltar qualquer quantidade na data-limite, o débito inteiro é cobrado.",
        column_config={
            "data_limite": st.column_config.DateColumn("Data-limite", format="DD/MM/YYYY"),
            "debito_integral": st.column_config.NumberColumn(
                "Débito integral", min_value=0.0, format="R$ %.2f"
            ),
        },
    )

with tab_vouchers:
    editor(
        "vouchers",
        "Lotes de vales",
        "Use uma linha por cliente, tipo e vencimento. Se o aviso já foi dado, use antecedência zero.",
        column_config={
            "quantidade": st.column_config.NumberColumn("Quantidade", min_value=0, step=1),
            "data_vencimento": st.column_config.DateColumn(
                "Vencimento inclusivo", format="DD/MM/YYYY"
            ),
            "antecedencia_min_dias": st.column_config.NumberColumn(
                "Antecedência mínima (dias)", min_value=0, step=1
            ),
            "custo_cliente_dia_palete": st.column_config.NumberColumn(
                "Custo cliente/dia/palete", min_value=0.0, format="R$ %.2f"
            ),
            "custo_perda_palete": st.column_config.NumberColumn(
                "Custo da perda/palete", min_value=0.0, format="R$ %.2f"
            ),
        },
    )

with tab_transport:
    st.info(
        "Depois de adicionar embarcadores, clientes, veículos ou alterar o horizonte, "
        "use o botão abaixo para reconstruir as combinações de datas e custos."
    )
    if st.button("Sincronizar calendário e rotas", type="secondary"):
        st.session_state.app_data = synchronize_data(
            st.session_state.app_data, planning_start, int(horizon_days)
        )
        st.session_state.pop("last_result", None)
        reset_editors(["stock", "fleet", "return_costs", "client_costs"])
        st.rerun()

    editor(
        "fleet",
        "Disponibilidade diária da frota",
        "O limite usado é o menor entre veículos × viagens por veículo e viagens habilitadas.",
        column_config={
            "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "veiculos_disponiveis": st.column_config.NumberColumn(
                "Veículos disponíveis", min_value=0, step=1
            ),
            "viagens_por_veiculo": st.column_config.NumberColumn(
                "Viagens/veículo/dia", min_value=0, step=1
            ),
            "viagens_habilitadas_paletes": st.column_config.NumberColumn(
                "Viagens habilitadas para paletes", min_value=0, step=1
            ),
        },
    )
    editor(
        "return_costs",
        "Custo Mello → embarcador",
        "Cada linha habilita aquela combinação de data, embarcador e veículo.",
        column_config={
            "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "custo_viagem": st.column_config.NumberColumn(
                "Custo fixo da viagem", min_value=0.0, format="R$ %.2f"
            ),
        },
    )
    editor(
        "client_costs",
        "Custo cliente → Mello",
        "A coleta respeita a antecedência e o vencimento informados no lote do vale.",
        column_config={
            "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "custo_viagem": st.column_config.NumberColumn(
                "Custo fixo da viagem", min_value=0.0, format="R$ %.2f"
            ),
        },
    )
    editor(
        "shipper_offers",
        "Ofertas de coleta pelo embarcador",
        "Informe o custo efetivamente suportado pela Mello; use zero se o embarcador pagar.",
        column_config={
            "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "capacidade_paletes": st.column_config.NumberColumn(
                "Capacidade oferecida", min_value=0, step=1
            ),
            "custo_para_mello": st.column_config.NumberColumn(
                "Custo para a Mello", min_value=0.0, format="R$ %.2f"
            ),
        },
    )

st.divider()
run_col, note_col = st.columns([1, 3], vertical_alignment="center")
with run_col:
    optimize = st.button("Otimizar plano", type="primary", width="stretch")
with note_col:
    st.caption(
        "O modelo pode deixar saldos pendentes quando essa for a alternativa de menor custo. "
        "A comparação 'sem agir' usa o mesmo horizonte selecionado."
    )

if optimize:
    try:
        with st.spinner("Montando o MILP e executando o HiGHS..."):
            result = solve_pallet_plan(
                st.session_state.app_data,
                planning_start,
                int(horizon_days),
            )
        st.session_state.last_result = result
        st.success("Plano ótimo encontrado. Abra a aba Resultados.")
    except Exception as exc:
        st.exception(exc)

with tab_results:
    result = st.session_state.get("last_result")
    if result is None:
        st.info("Preencha os dados e clique em **Otimizar plano**.")
    else:
        for warning in result.warnings:
            st.warning(warning)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Custo do plano", brl(result.objective))
        c2.metric("Custo sem agir", brl(result.baseline_cost))
        c3.metric("Economia estimada", brl(result.savings))
        c4.metric(
            "Paletes movimentados",
            f"{int(result.schedule['paletes'].sum()) if not result.schedule.empty else 0:,}".replace(",", "."),
        )

        st.subheader("Plano diário")
        if result.schedule.empty:
            st.info("O plano de menor custo não realiza movimentações neste horizonte.")
        else:
            st.dataframe(
                result.schedule,
                hide_index=True,
                width="stretch",
                column_config={
                    "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "custo": st.column_config.NumberColumn("Custo", format="R$ %.2f"),
                },
            )

        left, right = st.columns(2)
        with left:
            st.subheader("Composição do custo")
            st.dataframe(
                result.cost_breakdown,
                hide_index=True,
                width="stretch",
                column_config={"custo": st.column_config.NumberColumn("Custo", format="R$ %.2f")},
            )
            st.bar_chart(result.cost_breakdown.set_index("componente")["custo"])
        with right:
            st.subheader("Uso da frota")
            st.dataframe(result.fleet_usage, hide_index=True, width="stretch")

        st.subheader("Obrigações por embarcador e tipo")
        st.dataframe(
            result.obligations,
            hide_index=True,
            width="stretch",
            column_config={
                "debito_acionado_embarcador": st.column_config.NumberColumn(
                    "Débito acionado", format="R$ %.2f"
                )
            },
        )

        st.subheader("Situação dos vales")
        st.dataframe(
            result.vouchers,
            hide_index=True,
            width="stretch",
            column_config={
                "data_vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY")
            },
        )

        st.subheader("Estoque diário na Mello")
        st.dataframe(result.inventory, hide_index=True, width="stretch")

        st.download_button(
            "Baixar resultados em Excel",
            data=excel_result(result),
            file_name="plano_otimizado_paletes.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
