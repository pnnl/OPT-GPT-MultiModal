from pyomo.environ import *
import pandas as pd
def Run(freight_volume_tons, fc_gfuel_ton, energy_demand_mj_ton, emissions_gco2e_ton, transportation_cost_usd_ton, baseline_cost, baseline_ghg, max_cost_increase, mode, mode_fuel_options):

    """
    Optimize the allocation of freight volume to different reporting fuels using Pyomo
    to minimize the total fuel emissions of the freight sector, while keeping costs <20% increase relative to the baseline case.

    Args:
        transportation_cost_usd_ton: The input cost data containing fuel costs for different fuels per ton.
        fc_gfuel_ton: Fuel consumption of fuels per ton
        energy_demand_mj_ton: The energy demand for different fuels per ton
        emissions_gCO2_ton: emissions for different fuels per ton
        freight_volume_tons: Freight volume on the selected route in tons
        max_cost_increase : upper limit on total system cost increase
        mode (str): Transportation mode ("Highway", "Rail", "Maritime").
        mode_fuel_options (dict): which fuels to consider for allocation

    Returns:
        dict: A dictionary containing optimized allocations, emissions, and costs for each scenario.
    """
    # convert to dictionaries
    fc_gfuel_ton_dict = fc_gfuel_ton.groupby("MainEngineFuelType").apply(
         lambda x: x["FC_gFuel_ton"].tolist()
    ).to_dict()
    energy_demand_mj_ton_dict = energy_demand_mj_ton.groupby("MainEngineFuelType").apply(
         lambda x: x["EnergyDemand_MJ_ton"].tolist()
    ).to_dict()
    emissions_gco2e_ton_dict = emissions_gco2e_ton.groupby("MainEngineFuelType").apply(
         lambda x: x["Emissions_gCO2e_ton"].tolist()
    ).to_dict()
    transportation_cost_usd_ton_dict = transportation_cost_usd_ton.groupby("MainEngineFuelType").apply(
         lambda x: x["TransportationCost_USD_ton"].tolist()
    ).to_dict()

    # Initialize results dictionary
    results = {}

    # Define the optimization model
    model = ConcreteModel()
    model.fuels = Set(initialize=mode_fuel_options["Maritime"]) # set of fuels

    # Variables: Fraction of freight volume allocated to each fuel
    model.allocation = Var(model.fuels, bounds=(0,freight_volume_tons))

    # Objective: Minimize relative total fuel ghg
    def objective_rule(model):
        return sum(model.allocation[f] * emissions_gco2e_ton_dict[f][0] for f in model.fuels)
    model.objective = Objective(rule=objective_rule, sense=minimize)

    # Constraint: Total allocation must sum to 100% of freight volume
    def total_allocation_constraint(model):
        return sum(model.allocation[f] for f in model.fuels) == freight_volume_tons
    model.total_allocation = Constraint(rule=total_allocation_constraint)

    # Constraint: Total cost increase < 20% from baseline cost of diesel
    def total_cost_increase(model):
        return sum(model.allocation[f] * transportation_cost_usd_ton_dict[f][0] for f in model.fuels) <= (1+ (max_cost_increase/100))  * baseline_cost
    model.cost_increase = Constraint(rule=total_cost_increase)

    # Solve the optimization problem
    solver = SolverFactory('glpk') # Use GLPK solver; replace with 'gurobi' if available
    result = solver.solve(model)

    if result.solver.status == SolverStatus.ok and result.solver.termination_condition == TerminationCondition.optimal:
        # Extract optimized allocations
            print(f"Optimization succeded")
            allocations = {f: model.allocation[f].value for f in mode_fuel_options["Maritime"]}
            minimized_ghg = model.objective()
            total_cost = sum(model.allocation[f].value * transportation_cost_usd_ton_dict[f][0] for f in mode_fuel_options["Maritime"])

            # Store results
            results = {
                "allocations": allocations,
                "percent_ghg": ((minimized_ghg/baseline_ghg)-1)*100, # convert to percentage change
                "percent_cost": ((total_cost/baseline_cost)-1)*100 # convert to percentage change
            }
    else:
        print(f"Optimization failed")
        results = {"allocations": None, "percent_ghg": None, "percent_cost": None}

    return results

# end code
