from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
import pyomo.environ as pyo


@dataclass
class OptimizationResult:
    objective: float
    baseline_cost: float
    savings: float
    cost_breakdown: pd.DataFrame
    schedule: pd.DataFrame
    obligations: pd.DataFrame
    vouchers: pd.DataFrame
    inventory: pd.DataFrame
    fleet_usage: pd.DataFrame
    warnings: list[str]


REQUIRED_COLUMNS = {
    "pallet_types": ["tipo_palete", "custo_estoque_dia_palete"],
    "vehicles": ["veiculo", "capacidade_paletes"],
    "stock": ["tipo_palete", "quantidade_mello"],
    "obligations": ["embarcador", "tipo_palete", "quantidade_devida"],
    "threats": ["embarcador", "data_limite", "debito_integral"],
    "vouchers": [
        "vale_id",
        "cliente",
        "tipo_palete",
        "quantidade",
        "data_vencimento",
        "antecedencia_min_dias",
        "custo_cliente_dia_palete",
        "custo_perda_palete",
    ],
    "fleet": [
        "data",
        "veiculo",
        "veiculos_disponiveis",
        "viagens_por_veiculo",
        "viagens_habilitadas_paletes",
    ],
    "return_costs": ["data", "embarcador", "veiculo", "custo_viagem"],
    "client_costs": ["data", "cliente", "veiculo", "custo_viagem"],
    "shipper_offers": [
        "oferta_id",
        "data",
        "embarcador",
        "capacidade_paletes",
        "custo_para_mello",
    ],
}


def _clean(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame is None:
        frame = pd.DataFrame(columns=REQUIRED_COLUMNS[name])
    missing = set(REQUIRED_COLUMNS[name]) - set(frame.columns)
    if missing:
        raise ValueError(f"Tabela '{name}' sem as colunas: {sorted(missing)}")
    return frame[REQUIRED_COLUMNS[name]].dropna(how="all").copy()


def _strings(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    for column in columns:
        frame[column] = frame[column].fillna("").astype(str).str.strip()
        if frame[column].eq("").any():
            raise ValueError(f"Preencha '{column}' em todas as linhas de {label}.")


def _numbers(
    frame: pd.DataFrame,
    columns: list[str],
    label: str,
    integer_columns: tuple[str, ...] = (),
) -> None:
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].isna().any():
            raise ValueError(f"Há valor não numérico em '{column}' na tabela {label}.")
        if (frame[column] < 0).any():
            raise ValueError(f"Valores negativos não são permitidos em '{column}'.")
        if column in integer_columns:
            if ((frame[column] % 1).abs() > 1e-8).any():
                raise ValueError(f"'{column}' deve conter números inteiros em {label}.")
            frame[column] = frame[column].astype(int)


def _dates(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    for column in columns:
        converted = pd.to_datetime(frame[column], errors="coerce")
        if converted.isna().any():
            raise ValueError(f"Há data inválida em '{column}' na tabela {label}.")
        frame[column] = converted.dt.date


def validate_and_normalize(
    frames: dict[str, pd.DataFrame], start_date: date, horizon_days: int
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    if horizon_days < 1:
        raise ValueError("O horizonte deve possuir pelo menos um dia.")

    data = {name: _clean(frames.get(name), name) for name in REQUIRED_COLUMNS}
    warnings: list[str] = []

    _strings(data["pallet_types"], ["tipo_palete"], "tipos de palete")
    _strings(data["vehicles"], ["veiculo"], "veículos")
    _strings(data["stock"], ["tipo_palete"], "estoque")
    _strings(data["obligations"], ["embarcador", "tipo_palete"], "obrigações")
    _strings(data["threats"], ["embarcador"], "ameaças de débito")
    _strings(data["vouchers"], ["vale_id", "cliente", "tipo_palete"], "vales")
    _strings(data["fleet"], ["veiculo"], "frota")
    _strings(data["return_costs"], ["embarcador", "veiculo"], "custos de devolução")
    _strings(data["client_costs"], ["cliente", "veiculo"], "custos de coleta")
    _strings(data["shipper_offers"], ["oferta_id", "embarcador"], "ofertas de coleta")

    _numbers(data["pallet_types"], ["custo_estoque_dia_palete"], "tipos de palete")
    _numbers(
        data["vehicles"], ["capacidade_paletes"], "veículos", ("capacidade_paletes",)
    )
    _numbers(data["stock"], ["quantidade_mello"], "estoque", ("quantidade_mello",))
    _numbers(
        data["obligations"], ["quantidade_devida"], "obrigações", ("quantidade_devida",)
    )
    _numbers(data["threats"], ["debito_integral"], "ameaças de débito")
    _numbers(
        data["vouchers"],
        [
            "quantidade",
            "antecedencia_min_dias",
            "custo_cliente_dia_palete",
            "custo_perda_palete",
        ],
        "vales",
        ("quantidade", "antecedencia_min_dias"),
    )
    _numbers(
        data["fleet"],
        ["veiculos_disponiveis", "viagens_por_veiculo", "viagens_habilitadas_paletes"],
        "frota",
        ("veiculos_disponiveis", "viagens_por_veiculo", "viagens_habilitadas_paletes"),
    )
    _numbers(data["return_costs"], ["custo_viagem"], "custos de devolução")
    _numbers(data["client_costs"], ["custo_viagem"], "custos de coleta")
    _numbers(
        data["shipper_offers"],
        ["capacidade_paletes", "custo_para_mello"],
        "ofertas de coleta",
        ("capacidade_paletes",),
    )

    _dates(data["threats"], ["data_limite"], "ameaças de débito")
    _dates(data["vouchers"], ["data_vencimento"], "vales")
    _dates(data["fleet"], ["data"], "frota")
    _dates(data["return_costs"], ["data"], "custos de devolução")
    _dates(data["client_costs"], ["data"], "custos de coleta")
    _dates(data["shipper_offers"], ["data"], "ofertas de coleta")

    uniqueness = {
        "pallet_types": ["tipo_palete"],
        "vehicles": ["veiculo"],
        "stock": ["tipo_palete"],
        "obligations": ["embarcador", "tipo_palete"],
        "threats": ["embarcador"],
        "vouchers": ["vale_id"],
        "fleet": ["data", "veiculo"],
        "return_costs": ["data", "embarcador", "veiculo"],
        "client_costs": ["data", "cliente", "veiculo"],
        "shipper_offers": ["oferta_id"],
    }
    for name, columns in uniqueness.items():
        if data[name].duplicated(columns).any():
            raise ValueError(f"Há registros duplicados em {name}: chave {columns}.")

    pallet_types = set(data["pallet_types"]["tipo_palete"])
    vehicles = set(data["vehicles"]["veiculo"])
    shippers = set(data["obligations"]["embarcador"])
    clients = set(data["vouchers"]["cliente"])

    if not pallet_types or not vehicles or data["obligations"].empty:
        raise ValueError("Cadastre ao menos um tipo, um veículo e uma obrigação.")
    if set(data["stock"]["tipo_palete"]) - pallet_types:
        raise ValueError("O estoque contém tipo de palete não cadastrado.")
    if set(data["obligations"]["tipo_palete"]) - pallet_types:
        raise ValueError("As obrigações contêm tipo de palete não cadastrado.")
    if set(data["vouchers"]["tipo_palete"]) - pallet_types:
        raise ValueError("Os vales contêm tipo de palete não cadastrado.")
    if set(data["fleet"]["veiculo"]) - vehicles:
        raise ValueError("A frota contém veículo não cadastrado.")
    if set(data["return_costs"]["veiculo"]) - vehicles:
        raise ValueError("Custos de devolução contêm veículo não cadastrado.")
    if set(data["client_costs"]["veiculo"]) - vehicles:
        raise ValueError("Custos de coleta contêm veículo não cadastrado.")
    if set(data["return_costs"]["embarcador"]) - shippers:
        raise ValueError("Custos de devolução contêm embarcador sem obrigação.")
    if set(data["client_costs"]["cliente"]) - clients:
        raise ValueError("Custos de coleta contêm cliente sem vale.")
    if set(data["threats"]["embarcador"]) - shippers:
        raise ValueError("Ameaça de débito contém embarcador sem obrigação.")
    if set(data["shipper_offers"]["embarcador"]) - shippers:
        raise ValueError("Oferta de coleta contém embarcador sem obrigação.")

    end_date = start_date + timedelta(days=horizon_days - 1)
    for table in ("fleet", "return_costs", "client_costs", "shipper_offers"):
        data[table] = data[table][
            data[table]["data"].between(start_date, end_date)
        ].reset_index(drop=True)

    for row in data["vouchers"].itertuples(index=False):
        earliest = start_date + timedelta(days=int(row.antecedencia_min_dias))
        if row.data_vencimento < start_date:
            warnings.append(f"Vale {row.vale_id} já está vencido e será considerado perdido.")
        elif earliest > row.data_vencimento:
            warnings.append(
                f"Vale {row.vale_id}: a antecedência torna a coleta impossível antes do vencimento."
            )
        elif row.data_vencimento > end_date:
            warnings.append(
                f"Vale {row.vale_id} vence após o horizonte; sua perda ainda não será cobrada."
            )

    for row in data["threats"].itertuples(index=False):
        if row.data_limite > end_date:
            warnings.append(
                f"Débito de {row.embarcador} vence após o horizonte e não será ativado nesta execução."
            )

    return data, warnings


def solve_pallet_plan(
    frames: dict[str, pd.DataFrame],
    start_date: date,
    horizon_days: int,
    time_limit_seconds: int = 30,
) -> OptimizationResult:
    data, warnings = validate_and_normalize(frames, start_date, horizon_days)
    days = [start_date + timedelta(days=k) for k in range(horizon_days)]
    end_date = days[-1]
    day_pos = {day: pos for pos, day in enumerate(days)}

    pallet_types = data["pallet_types"]["tipo_palete"].tolist()
    vehicles = data["vehicles"]["veiculo"].tolist()
    shippers = sorted(data["obligations"]["embarcador"].unique())
    clients = sorted(data["vouchers"]["cliente"].unique())
    lots = data["vouchers"]["vale_id"].tolist()

    capacity = data["vehicles"].set_index("veiculo")["capacidade_paletes"].to_dict()
    storage_cost = data["pallet_types"].set_index("tipo_palete")[
        "custo_estoque_dia_palete"
    ].to_dict()
    opening_stock = {p: 0 for p in pallet_types}
    opening_stock.update(data["stock"].set_index("tipo_palete")["quantidade_mello"].to_dict())
    due = {
        (row.embarcador, row.tipo_palete): int(row.quantidade_devida)
        for row in data["obligations"].itertuples(index=False)
    }
    obligation_idx = list(due)

    voucher_rows = data["vouchers"].set_index("vale_id")
    lot_client = voucher_rows["cliente"].to_dict()
    lot_type = voucher_rows["tipo_palete"].to_dict()
    lot_qty = voucher_rows["quantidade"].astype(int).to_dict()
    lot_expiry = voucher_rows["data_vencimento"].to_dict()
    lot_earliest = {
        lot: start_date + timedelta(days=int(voucher_rows.loc[lot, "antecedencia_min_dias"]))
        for lot in lots
    }
    lot_holding = voucher_rows["custo_cliente_dia_palete"].to_dict()
    lot_loss_cost = voucher_rows["custo_perda_palete"].to_dict()

    fleet = {
        (row.veiculo, row.data): (
            int(row.veiculos_disponiveis),
            int(row.viagens_por_veiculo),
            int(row.viagens_habilitadas_paletes),
        )
        for row in data["fleet"].itertuples(index=False)
    }
    return_cost = {
        (row.embarcador, row.veiculo, row.data): float(row.custo_viagem)
        for row in data["return_costs"].itertuples(index=False)
    }
    client_cost = {
        (row.cliente, row.veiculo, row.data): float(row.custo_viagem)
        for row in data["client_costs"].itertuples(index=False)
    }

    offer_rows = data["shipper_offers"].set_index("oferta_id")
    offers = offer_rows.index.tolist()
    offer_shipper = offer_rows["embarcador"].to_dict()
    offer_date = offer_rows["data"].to_dict()
    offer_capacity = offer_rows["capacidade_paletes"].astype(int).to_dict()
    offer_cost = offer_rows["custo_para_mello"].to_dict()

    return_trip_idx = sorted(return_cost)
    return_qty_idx = [
        (i, p, v, t)
        for i, v, t in return_trip_idx
        for ii, p in obligation_idx
        if ii == i
    ]
    client_trip_idx = sorted(client_cost)
    collect_idx = [
        (lot, v, t)
        for lot in lots
        for v in vehicles
        for t in days
        if lot_earliest[lot] <= t <= lot_expiry[lot]
        and (lot_client[lot], v, t) in client_cost
    ]
    offer_qty_idx = [
        (offer, p)
        for offer in offers
        for i, p in obligation_idx
        if i == offer_shipper[offer]
    ]

    model = pyo.ConcreteModel(name="planejamento_paletes_mello")
    model.P = pyo.Set(initialize=pallet_types, ordered=True)
    model.V = pyo.Set(initialize=vehicles, ordered=True)
    model.T = pyo.Set(initialize=days, ordered=True)
    model.OBL = pyo.Set(dimen=2, initialize=obligation_idx)
    model.RET_TRIP = pyo.Set(dimen=3, initialize=return_trip_idx)
    model.RET_QTY = pyo.Set(dimen=4, initialize=return_qty_idx)
    model.CLI_TRIP = pyo.Set(dimen=3, initialize=client_trip_idx)
    model.COLLECT = pyo.Set(dimen=3, initialize=collect_idx)
    model.L = pyo.Set(initialize=lots)
    model.OFFERS = pyo.Set(initialize=offers)
    model.OFFER_QTY = pyo.Set(dimen=2, initialize=offer_qty_idx)

    model.return_trips = pyo.Var(model.RET_TRIP, domain=pyo.NonNegativeIntegers)
    model.return_qty = pyo.Var(model.RET_QTY, domain=pyo.NonNegativeIntegers)
    model.client_trips = pyo.Var(model.CLI_TRIP, domain=pyo.NonNegativeIntegers)
    model.collect_qty = pyo.Var(model.COLLECT, domain=pyo.NonNegativeIntegers)
    model.offer_used = pyo.Var(model.OFFERS, domain=pyo.Binary)
    model.offer_qty = pyo.Var(model.OFFER_QTY, domain=pyo.NonNegativeIntegers)
    model.inventory = pyo.Var(model.P, model.T, domain=pyo.NonNegativeIntegers)
    model.due_remaining = pyo.Var(model.OBL, model.T, domain=pyo.NonNegativeIntegers)
    model.lost = pyo.Var(model.L, domain=pyo.NonNegativeIntegers)

    threats = data["threats"].set_index("embarcador")
    threat_shippers = threats.index.tolist()
    model.THREAT = pyo.Set(initialize=threat_shippers)
    model.debit_triggered = pyo.Var(model.THREAT, domain=pyo.Binary)

    def return_upper_rule(m: pyo.ConcreteModel, i: str, p: str, v: str, t: date):
        return m.return_qty[i, p, v, t] <= capacity[v] * m.return_trips[i, v, t]

    model.ReturnUpper = pyo.Constraint(model.RET_QTY, rule=return_upper_rule)

    def return_trip_used_rule(m: pyo.ConcreteModel, i: str, v: str, t: date):
        carried = sum(
            m.return_qty[ii, p, vv, tt]
            for ii, p, vv, tt in m.RET_QTY
            if ii == i and vv == v and tt == t
        )
        return m.return_trips[i, v, t] <= carried

    model.ReturnTripUsed = pyo.Constraint(model.RET_TRIP, rule=return_trip_used_rule)

    def client_capacity_rule(m: pyo.ConcreteModel, c: str, v: str, t: date):
        carried = sum(
            m.collect_qty[lot, vv, tt]
            for lot, vv, tt in m.COLLECT
            if lot_client[lot] == c and vv == v and tt == t
        )
        return carried <= capacity[v] * m.client_trips[c, v, t]

    model.ClientCapacity = pyo.Constraint(model.CLI_TRIP, rule=client_capacity_rule)

    def client_trip_used_rule(m: pyo.ConcreteModel, c: str, v: str, t: date):
        carried = sum(
            m.collect_qty[lot, vv, tt]
            for lot, vv, tt in m.COLLECT
            if lot_client[lot] == c and vv == v and tt == t
        )
        return m.client_trips[c, v, t] <= carried

    model.ClientTripUsed = pyo.Constraint(model.CLI_TRIP, rule=client_trip_used_rule)

    def lot_limit_rule(m: pyo.ConcreteModel, lot: str):
        variables = [
            m.collect_qty[ll, v, t] for ll, v, t in m.COLLECT if ll == lot
        ]
        if not variables:
            return pyo.Constraint.Feasible
        return sum(variables) <= lot_qty[lot]

    model.LotLimit = pyo.Constraint(model.L, rule=lot_limit_rule)

    def offer_capacity_rule(m: pyo.ConcreteModel, offer: str):
        quantity = sum(
            m.offer_qty[o, p] for o, p in m.OFFER_QTY if o == offer
        )
        return quantity <= offer_capacity[offer] * m.offer_used[offer]

    model.OfferCapacity = pyo.Constraint(model.OFFERS, rule=offer_capacity_rule)

    def offer_used_rule(m: pyo.ConcreteModel, offer: str):
        quantity = sum(
            m.offer_qty[o, p] for o, p in m.OFFER_QTY if o == offer
        )
        return m.offer_used[offer] <= quantity

    model.OfferUsed = pyo.Constraint(model.OFFERS, rule=offer_used_rule)

    def fleet_physical_rule(m: pyo.ConcreteModel, v: str, t: date):
        available, trips_per_vehicle, _ = fleet.get((v, t), (0, 0, 0))
        used = sum(
            m.return_trips[i, vv, tt]
            for i, vv, tt in m.RET_TRIP
            if vv == v and tt == t
        ) + sum(
            m.client_trips[c, vv, tt]
            for c, vv, tt in m.CLI_TRIP
            if vv == v and tt == t
        )
        return used <= available * trips_per_vehicle

    model.FleetPhysical = pyo.Constraint(model.V, model.T, rule=fleet_physical_rule)

    def fleet_enabled_rule(m: pyo.ConcreteModel, v: str, t: date):
        _, _, enabled = fleet.get((v, t), (0, 0, 0))
        used = sum(
            m.return_trips[i, vv, tt]
            for i, vv, tt in m.RET_TRIP
            if vv == v and tt == t
        ) + sum(
            m.client_trips[c, vv, tt]
            for c, vv, tt in m.CLI_TRIP
            if vv == v and tt == t
        )
        return used <= enabled

    model.FleetEnabled = pyo.Constraint(model.V, model.T, rule=fleet_enabled_rule)

    def inventory_rule(m: pyo.ConcreteModel, p: str, t: date):
        pos = day_pos[t]
        previous = opening_stock[p] if pos == 0 else m.inventory[p, days[pos - 1]]
        arrivals = 0
        if pos > 0:
            prior = days[pos - 1]
            arrivals = sum(
                m.collect_qty[lot, v, tt]
                for lot, v, tt in m.COLLECT
                if lot_type[lot] == p and tt == prior
            )
        mello_returns = sum(
            m.return_qty[i, pp, v, tt]
            for i, pp, v, tt in m.RET_QTY
            if pp == p and tt == t
        )
        shipper_pickups = sum(
            m.offer_qty[offer, pp]
            for offer, pp in m.OFFER_QTY
            if pp == p and offer_date[offer] == t
        )
        return m.inventory[p, t] == previous + arrivals - mello_returns - shipper_pickups

    model.InventoryBalance = pyo.Constraint(model.P, model.T, rule=inventory_rule)

    def due_rule(m: pyo.ConcreteModel, i: str, p: str, t: date):
        pos = day_pos[t]
        previous = due[i, p] if pos == 0 else m.due_remaining[i, p, days[pos - 1]]
        mello_returns = sum(
            m.return_qty[ii, pp, v, tt]
            for ii, pp, v, tt in m.RET_QTY
            if ii == i and pp == p and tt == t
        )
        shipper_pickups = sum(
            m.offer_qty[offer, pp]
            for offer, pp in m.OFFER_QTY
            if offer_shipper[offer] == i and pp == p and offer_date[offer] == t
        )
        return m.due_remaining[i, p, t] == previous - mello_returns - shipper_pickups

    model.DueBalance = pyo.Constraint(model.OBL, model.T, rule=due_rule)

    for lot in lots:
        collected = sum(
            model.collect_qty[ll, v, t]
            for ll, v, t in model.COLLECT
            if ll == lot
        )
        if lot_expiry[lot] <= end_date:
            model.add_component(
                f"LossBalance_{lot}", pyo.Constraint(expr=model.lost[lot] == lot_qty[lot] - collected)
            )
        else:
            model.lost[lot].fix(0)

    for shipper in threat_shippers:
        deadline = threats.loc[shipper, "data_limite"]
        if deadline < start_date:
            model.debit_triggered[shipper].fix(1 if any(i == shipper and q > 0 for (i, _), q in due.items()) else 0)
            warnings.append(f"Prazo de {shipper} já passou; o débito foi considerado acionado.")
        elif deadline > end_date:
            model.debit_triggered[shipper].fix(0)
        else:
            for i, p in obligation_idx:
                if i == shipper:
                    safe = "".join(ch if ch.isalnum() else "_" for ch in f"{shipper}_{p}")
                    model.add_component(
                        f"Threat_{safe}",
                        pyo.Constraint(
                            expr=model.due_remaining[i, p, deadline]
                            <= due[i, p] * model.debit_triggered[shipper]
                        ),
                    )

    return_freight = sum(
        return_cost[i, v, t] * model.return_trips[i, v, t]
        for i, v, t in return_trip_idx
    )
    client_freight = sum(
        client_cost[c, v, t] * model.client_trips[c, v, t]
        for c, v, t in client_trip_idx
    )
    shipper_pickup_cost = sum(offer_cost[o] * model.offer_used[o] for o in offers)
    mello_storage = sum(
        storage_cost[p] * model.inventory[p, t] for p in pallet_types for t in days
    )

    client_holding_terms: list[Any] = []
    for lot in lots:
        for t in days:
            if t <= lot_expiry[lot]:
                collected_to_date = sum(
                    model.collect_qty[ll, v, tt]
                    for ll, v, tt in model.COLLECT
                    if ll == lot and tt <= t
                )
                client_holding_terms.append(
                    lot_holding[lot] * (lot_qty[lot] - collected_to_date)
                )
    client_holding = sum(client_holding_terms)
    loss_cost = sum(lot_loss_cost[lot] * model.lost[lot] for lot in lots)
    debit_cost = sum(
        float(threats.loc[i, "debito_integral"]) * model.debit_triggered[i]
        for i in threat_shippers
    )

    model.TotalCost = pyo.Objective(
        expr=return_freight
        + client_freight
        + shipper_pickup_cost
        + mello_storage
        + client_holding
        + loss_cost
        + debit_cost,
        sense=pyo.minimize,
    )

    solver = pyo.SolverFactory("appsi_highs")
    if not solver.available(exception_flag=False):
        raise RuntimeError("HiGHS indisponível. Instale com: pip install highspy")
    solver.options["time_limit"] = int(time_limit_seconds)
    solver.options["mip_rel_gap"] = 0.001
    results = solver.solve(model)
    termination = results.solver.termination_condition
    if termination not in {pyo.TerminationCondition.optimal, pyo.TerminationCondition.feasible}:
        raise RuntimeError(f"O HiGHS não encontrou solução utilizável: {termination}")

    def value(item: Any) -> float:
        return float(pyo.value(item))

    schedule_rows: list[dict[str, Any]] = []
    for i, v, t in return_trip_idx:
        trips = round(value(model.return_trips[i, v, t]))
        quantities = {
            p: round(value(model.return_qty[i, p, v, t]))
            for ii, p, vv, tt in return_qty_idx
            if ii == i and vv == v and tt == t
        }
        total = sum(quantities.values())
        if total:
            schedule_rows.append(
                {
                    "data": t,
                    "acao": "Devolver ao embarcador",
                    "origem": "Mello",
                    "destino": i,
                    "veiculo": v,
                    "viagens": trips,
                    "paletes": total,
                    "detalhe": ", ".join(f"{p}: {q}" for p, q in quantities.items() if q),
                    "custo": trips * return_cost[i, v, t],
                }
            )
    for c, v, t in client_trip_idx:
        trips = round(value(model.client_trips[c, v, t]))
        quantities = {
            lot: round(value(model.collect_qty[lot, v, t]))
            for lot, vv, tt in collect_idx
            if lot_client[lot] == c and vv == v and tt == t
        }
        total = sum(quantities.values())
        if total:
            detail_by_type: dict[str, int] = {}
            for lot, quantity in quantities.items():
                detail_by_type[lot_type[lot]] = detail_by_type.get(lot_type[lot], 0) + quantity
            schedule_rows.append(
                {
                    "data": t,
                    "acao": "Coletar no cliente",
                    "origem": c,
                    "destino": "Mello",
                    "veiculo": v,
                    "viagens": trips,
                    "paletes": total,
                    "detalhe": ", ".join(f"{p}: {q}" for p, q in detail_by_type.items() if q),
                    "custo": trips * client_cost[c, v, t],
                }
            )
    for offer in offers:
        quantities = {
            p: round(value(model.offer_qty[offer, p]))
            for o, p in offer_qty_idx
            if o == offer
        }
        total = sum(quantities.values())
        if total:
            schedule_rows.append(
                {
                    "data": offer_date[offer],
                    "acao": "Coleta pelo embarcador",
                    "origem": "Mello",
                    "destino": offer_shipper[offer],
                    "veiculo": "Frota do embarcador",
                    "viagens": 1,
                    "paletes": total,
                    "detalhe": ", ".join(f"{p}: {q}" for p, q in quantities.items() if q),
                    "custo": offer_cost[offer],
                }
            )
    schedule = pd.DataFrame(
        schedule_rows,
        columns=["data", "acao", "origem", "destino", "veiculo", "viagens", "paletes", "detalhe", "custo"],
    )
    if not schedule.empty:
        schedule = schedule.sort_values(["data", "acao", "destino"]).reset_index(drop=True)

    obligation_rows = []
    for i, p in obligation_idx:
        returned_mello = sum(
            round(value(model.return_qty[ii, pp, v, t]))
            for ii, pp, v, t in return_qty_idx
            if ii == i and pp == p
        )
        collected_shipper = sum(
            round(value(model.offer_qty[o, pp]))
            for o, pp in offer_qty_idx
            if offer_shipper[o] == i and pp == p
        )
        debit = 0.0
        if i in threat_shippers and round(value(model.debit_triggered[i])):
            debit = float(threats.loc[i, "debito_integral"])
        obligation_rows.append(
            {
                "embarcador": i,
                "tipo_palete": p,
                "quantidade_devida": due[i, p],
                "devolvido_mello": returned_mello,
                "coletado_embarcador": collected_shipper,
                "saldo_final": round(value(model.due_remaining[i, p, end_date])),
                "debito_acionado_embarcador": debit,
            }
        )
    obligations_result = pd.DataFrame(obligation_rows)

    voucher_result_rows = []
    for lot in lots:
        collected = sum(
            round(value(model.collect_qty[ll, v, t]))
            for ll, v, t in collect_idx
            if ll == lot
        )
        lost = round(value(model.lost[lot]))
        active_remaining = 0 if lot_expiry[lot] <= end_date else lot_qty[lot] - collected
        voucher_result_rows.append(
            {
                "vale_id": lot,
                "cliente": lot_client[lot],
                "tipo_palete": lot_type[lot],
                "quantidade": lot_qty[lot],
                "coletado": collected,
                "perdido_no_vencimento": lost,
                "saldo_ativo_fim_horizonte": active_remaining,
                "data_vencimento": lot_expiry[lot],
            }
        )
    vouchers_result = pd.DataFrame(voucher_result_rows)

    inventory_rows = [
        {"data": t, "tipo_palete": p, "estoque_mello_fim_dia": round(value(model.inventory[p, t]))}
        for t in days
        for p in pallet_types
    ]
    inventory_result = pd.DataFrame(inventory_rows)

    fleet_rows = []
    for t in days:
        for v in vehicles:
            available, per_vehicle, enabled = fleet.get((v, t), (0, 0, 0))
            returns_used = sum(
                round(value(model.return_trips[i, vv, tt]))
                for i, vv, tt in return_trip_idx
                if vv == v and tt == t
            )
            collections_used = sum(
                round(value(model.client_trips[c, vv, tt]))
                for c, vv, tt in client_trip_idx
                if vv == v and tt == t
            )
            limit = min(available * per_vehicle, enabled)
            fleet_rows.append(
                {
                    "data": t,
                    "veiculo": v,
                    "limite_viagens_paletes": limit,
                    "viagens_devolucao": returns_used,
                    "viagens_coleta_cliente": collections_used,
                    "viagens_utilizadas": returns_used + collections_used,
                    "viagens_livres": limit - returns_used - collections_used,
                }
            )
    fleet_result = pd.DataFrame(fleet_rows)

    cost_values = {
        "Frete Mello → embarcador": value(return_freight),
        "Frete cliente → Mello": value(client_freight),
        "Coleta pela frota do embarcador": value(shipper_pickup_cost),
        "Estoque na Mello": value(mello_storage),
        "Permanência nos clientes": value(client_holding),
        "Perda de paletes por vencimento": value(loss_cost),
        "Débitos integrais": value(debit_cost),
    }
    cost_breakdown = pd.DataFrame(
        [{"componente": key, "custo": val} for key, val in cost_values.items()]
    )

    baseline_storage = sum(storage_cost[p] * opening_stock[p] for p in pallet_types) * horizon_days
    baseline_client_holding = 0.0
    baseline_loss = 0.0
    for lot in lots:
        active_days = sum(1 for t in days if t <= lot_expiry[lot])
        baseline_client_holding += lot_holding[lot] * lot_qty[lot] * active_days
        if lot_expiry[lot] <= end_date:
            baseline_loss += lot_loss_cost[lot] * lot_qty[lot]
    baseline_debit = sum(
        float(row.debito_integral)
        for row in data["threats"].itertuples(index=False)
        if row.data_limite <= end_date
        and sum(q for (i, _), q in due.items() if i == row.embarcador) > 0
    )
    baseline_cost = baseline_storage + baseline_client_holding + baseline_loss + baseline_debit
    objective = value(model.TotalCost)

    return OptimizationResult(
        objective=objective,
        baseline_cost=baseline_cost,
        savings=baseline_cost - objective,
        cost_breakdown=cost_breakdown,
        schedule=schedule,
        obligations=obligations_result,
        vouchers=vouchers_result,
        inventory=inventory_result,
        fleet_usage=fleet_result,
        warnings=warnings,
    )
