from datetime import date

import pandas as pd

from optimizer import solve_pallet_plan
from sample_data import make_sample_data


def test_sample_model_solves_and_balances():
    start = date(2026, 8, 17)
    data = make_sample_data(start, 7)
    result = solve_pallet_plan(data, start, 7)

    assert result.objective >= 0
    assert result.objective <= result.baseline_cost + 1e-6
    assert (result.inventory["estoque_mello_fim_dia"] >= 0).all()
    assert (result.obligations["saldo_final"] >= 0).all()
    assert (
        result.vouchers["coletado"]
        + result.vouchers["perdido_no_vencimento"]
        + result.vouchers["saldo_ativo_fim_horizonte"]
        == result.vouchers["quantidade"]
    ).all()


def test_expired_uncollected_voucher_pays_unit_loss():
    start = date(2026, 8, 17)
    data = make_sample_data(start, 2)
    data["fleet"]["viagens_habilitadas_paletes"] = 0
    data["vouchers"] = pd.DataFrame(
        [["V1", "BH", "PBR", 10, start, 0, 2.0, 100.0]],
        columns=data["vouchers"].columns,
    )
    data["client_costs"] = pd.DataFrame(
        [[start, "BH", "Carreta padrão", 10.0]],
        columns=data["client_costs"].columns,
    )
    result = solve_pallet_plan(data, start, 2)

    voucher = result.vouchers.iloc[0]
    assert voucher["coletado"] == 0
    assert voucher["perdido_no_vencimento"] == 10
    loss = result.cost_breakdown.set_index("componente").loc[
        "Perda de paletes por vencimento", "custo"
    ]
    assert loss == 1_000.0


def test_notice_period_blocks_early_collection():
    start = date(2026, 8, 17)
    data = make_sample_data(start, 3)
    data["vouchers"] = pd.DataFrame(
        [["V1", "BH", "PBR", 10, start, 2, 10.0, 100.0]],
        columns=data["vouchers"].columns,
    )
    data["client_costs"] = data["client_costs"][
        data["client_costs"]["cliente"] == "BH"
    ].reset_index(drop=True)
    result = solve_pallet_plan(data, start, 3)

    voucher = result.vouchers.iloc[0]
    assert voucher["coletado"] == 0
    assert voucher["perdido_no_vencimento"] == 10
    assert any("coleta impossível" in warning for warning in result.warnings)


def test_full_debit_is_not_reduced_by_partial_return():
    start = date(2026, 8, 17)
    data = make_sample_data(start, 1)
    data["obligations"] = pd.DataFrame(
        [["Itambé", "PBR", 400]], columns=data["obligations"].columns
    )
    data["stock"] = pd.DataFrame([["PBR", 300]], columns=data["stock"].columns)
    data["threats"] = pd.DataFrame(
        [["Itambé", start, 100_000.0]], columns=data["threats"].columns
    )
    data["vouchers"] = data["vouchers"].iloc[0:0]
    data["client_costs"] = data["client_costs"].iloc[0:0]
    data["shipper_offers"] = data["shipper_offers"].iloc[0:0]
    data["return_costs"] = pd.DataFrame(
        [[start, "Itambé", "Carreta padrão", 1.0]],
        columns=data["return_costs"].columns,
    )
    data["fleet"] = pd.DataFrame(
        [[start, "Carreta padrão", 1, 1, 1]], columns=data["fleet"].columns
    )

    result = solve_pallet_plan(data, start, 1)
    assert result.obligations["debito_acionado_embarcador"].max() == 100_000.0
