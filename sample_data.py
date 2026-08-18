from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def make_sample_data(start_date: date, horizon_days: int) -> dict[str, pd.DataFrame]:
    days = [start_date + timedelta(days=k) for k in range(horizon_days)]
    last = days[-1]
    d = lambda offset: min(start_date + timedelta(days=offset), last)

    pallet_types = pd.DataFrame(
        [
            ["PBR", 0.50],
            ["CHEP", 0.60],
        ],
        columns=["tipo_palete", "custo_estoque_dia_palete"],
    )
    vehicles = pd.DataFrame(
        [["Carreta padrão", 300]],
        columns=["veiculo", "capacidade_paletes"],
    )
    stock = pd.DataFrame(
        [["PBR", 180], ["CHEP", 40]],
        columns=["tipo_palete", "quantidade_mello"],
    )
    obligations = pd.DataFrame(
        [
            ["Itambé", "PBR", 300],
            ["Italac", "PBR", 100],
            ["Unilever", "CHEP", 120],
        ],
        columns=["embarcador", "tipo_palete", "quantidade_devida"],
    )
    threats = pd.DataFrame(
        [
            ["Itambé", d(4), 100_000.0],
            ["Italac", d(6), 8_000.0],
            ["Unilever", d(6), 12_000.0],
        ],
        columns=["embarcador", "data_limite", "debito_integral"],
    )
    vouchers = pd.DataFrame(
        [
            ["BH-PBR-001", "BH", "PBR", 180, d(3), 2, 0.80, 180.0],
            ["LUNA-CHEP-001", "Luna", "CHEP", 100, d(5), 1, 0.60, 250.0],
        ],
        columns=[
            "vale_id",
            "cliente",
            "tipo_palete",
            "quantidade",
            "data_vencimento",
            "antecedencia_min_dias",
            "custo_cliente_dia_palete",
            "custo_perda_palete",
        ],
    )

    fleet = pd.DataFrame(
        [
            [day, "Carreta padrão", 1, 2, 1 if pos < 3 else 2]
            for pos, day in enumerate(days)
        ],
        columns=[
            "data",
            "veiculo",
            "veiculos_disponiveis",
            "viagens_por_veiculo",
            "viagens_habilitadas_paletes",
        ],
    )
    return_costs = pd.DataFrame(
        [
            [day, shipper, "Carreta padrão", cost]
            for day in days
            for shipper, cost in [("Itambé", 4_500.0), ("Italac", 3_500.0), ("Unilever", 3_800.0)]
        ],
        columns=["data", "embarcador", "veiculo", "custo_viagem"],
    )
    client_costs = pd.DataFrame(
        [
            [day, client, "Carreta padrão", cost]
            for day in days
            for client, cost in [("BH", 2_200.0), ("Luna", 1_800.0)]
        ],
        columns=["data", "cliente", "veiculo", "custo_viagem"],
    )
    shipper_offers = pd.DataFrame(
        [["OF-ITAMBE-01", d(2), "Itambé", 300, 5_800.0]],
        columns=["oferta_id", "data", "embarcador", "capacidade_paletes", "custo_para_mello"],
    )
    return {
        "pallet_types": pallet_types,
        "vehicles": vehicles,
        "stock": stock,
        "obligations": obligations,
        "threats": threats,
        "vouchers": vouchers,
        "fleet": fleet,
        "return_costs": return_costs,
        "client_costs": client_costs,
        "shipper_offers": shipper_offers,
    }


def synchronize_data(
    current: dict[str, pd.DataFrame], start_date: date, horizon_days: int
) -> dict[str, pd.DataFrame]:
    """Expand calendar/cost tables while preserving matching values."""
    sample = make_sample_data(start_date, horizon_days)
    days = [start_date + timedelta(days=k) for k in range(horizon_days)]
    types = current["pallet_types"]["tipo_palete"].dropna().astype(str).str.strip()
    vehicles = current["vehicles"]["veiculo"].dropna().astype(str).str.strip()
    shippers = current["obligations"]["embarcador"].dropna().astype(str).str.strip().unique()
    clients = current["vouchers"]["cliente"].dropna().astype(str).str.strip().unique()

    def merge_grid(grid: pd.DataFrame, old: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        old = old.copy()
        for column in keys:
            if column == "data" and not old.empty:
                old[column] = pd.to_datetime(old[column], errors="coerce").dt.date
        values = [column for column in old.columns if column not in keys]
        if old.empty:
            return grid
        merged = grid.merge(old, on=keys, how="left", suffixes=("_default", ""))
        for column in values:
            default = f"{column}_default"
            if default in merged:
                merged[column] = merged[column].fillna(merged[default])
                merged = merged.drop(columns=default)
        return merged[grid.columns]

    fleet_grid = pd.DataFrame(
        [[day, vehicle, 1, 1, 1] for day in days for vehicle in vehicles],
        columns=sample["fleet"].columns,
    )
    return_grid = pd.DataFrame(
        [[day, shipper, vehicle, 0.0] for day in days for shipper in shippers for vehicle in vehicles],
        columns=sample["return_costs"].columns,
    )
    client_grid = pd.DataFrame(
        [[day, client, vehicle, 0.0] for day in days for client in clients for vehicle in vehicles],
        columns=sample["client_costs"].columns,
    )

    result = {key: value.copy() for key, value in current.items()}
    result["fleet"] = merge_grid(fleet_grid, current["fleet"], ["data", "veiculo"])
    result["return_costs"] = merge_grid(
        return_grid, current["return_costs"], ["data", "embarcador", "veiculo"]
    )
    result["client_costs"] = merge_grid(
        client_grid, current["client_costs"], ["data", "cliente", "veiculo"]
    )

    stock_old = current["stock"].copy()
    stock_grid = pd.DataFrame({"tipo_palete": types, "quantidade_mello": 0})
    result["stock"] = merge_grid(stock_grid, stock_old, ["tipo_palete"])
    return result
