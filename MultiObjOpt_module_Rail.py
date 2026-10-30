from pyomo.environ import *
import pandas as pd

def Run(Fuel_cost_data, max_cost_increase, mode, mode_fuel_options):

    """
    Optimize the allocation of freight volume to different rail fuels using Pyomo
    to minimize total GHG emissions, while keeping costs within a user-defined
    percentage increase relative to the petroleum diesel baseline.

    The input Fuel_cost_data is a dictionary built from the ARPAERail database
    (AltriosResults.Results{year} joined with Reference.FuelType, Reference.GcamScenario,
    AltriosResults.RouteDefinition, and AltriosResults.ARPAE_STATIONSWITHNEARNODES),
    with the following DB column mappings:

        Fuel_cost_data[fuel] = {
            'tonnage'   : TotalTonnageSt          (short tons of freight moved),
            'cost'      : CostTotalDiscounted      (total discounted cost, $),
            'emissions' : GHG                      (total GHG emissions),
            'energyuse' : EnergyUsageMJ            (total energy usage, MJ),
            'lcotkm'    : LCOTKM                   (levelized cost per ton-km, $/ton-km)
        }

    ARPAE_STATIONSWITHNEARNODES key columns:
        NAME      : station name (used for origin/destination station selection)
        LocState  : state abbreviation (used for state filtering)
        UNQUIEID  : unique station ID (note DB typo) — joined to RouteDefinition.OriginUniqueID
                    and RouteDefinition.DestinationUniqueID

    Rail fuels available in Reference.FuelType:
        'petroleum diesel', 'e-diesel', 'electricity',
        'ft biofuels', 'ft biofuels ccs', 'hydrogen', 'renewable diesel'

    Args:
        Fuel_cost_data (dict): Per-fuel cost, emissions, tonnage, energy, and lcotkm data
                               keyed by fuel name. Must include 'petroleum diesel' as the
                               baseline entry.
        max_cost_increase (float): Maximum allowable % cost increase above the petroleum
                                   diesel baseline (e.g. 20 means <= 20% cost increase).
        mode (str): Transportation mode string, should be "Rail".
        mode_fuel_options (dict): Dictionary mapping mode name to list of fuel strings
                                  to consider for optimization, e.g.:
                                  {"Rail": ["petroleum diesel", "electricity", "hydrogen", ...]}

    Returns:
        dict: A dictionary containing:
            - 'allocations'    (dict)  : Optimized tonnage allocation per fuel {fuel: tons}
            - 'percent_ghg'    (float) : % change in total GHG vs. petroleum diesel baseline
            - 'percent_cost'   (float) : % change in total cost vs. petroleum diesel baseline
            - 'percent_lcotkm' (float) : % change in LCOTKM vs. petroleum diesel baseline
            Returns None values for all keys if the solver fails to find an optimal solution.
    """

    tonnage = Fuel_cost_data['petroleum diesel']['tonnage']

    # Initialize results dictionary
    results = {}

    # Define the optimization model
    model = ConcreteModel()
    model.fuels = Set(initialize=mode_fuel_options["Rail"])  # set of rail fuels

    # Decision variables: tonnage allocated to each fuel, bounded [0, total tonnage]
    model.allocation = Var(model.fuels, bounds=(0, tonnage))

    # Objective: Minimize relative total GHG (weighted average emissions intensity)
    def objective_rule(model):
        return sum(model.allocation[f] * (Fuel_cost_data[f]['emissions'] / tonnage) for f in model.fuels)
    model.objective = Objective(rule=objective_rule, sense=minimize)

    # Constraint: Total allocation must equal 100% of freight volume (short tons)
    def total_allocation_constraint(model):
        return sum(model.allocation[f] for f in model.fuels) == tonnage
    model.total_allocation = Constraint(rule=total_allocation_constraint)

    # Constraint: Weighted-average cost must not exceed (1 + max_cost_increase%) x baseline cost
    # Baseline is petroleum diesel (CostTotalDiscounted from AltriosResults.Results{year})
    def total_cost_increase(model):
        return sum(model.allocation[f] * (Fuel_cost_data[f]['cost'] / tonnage) for f in model.fuels) \
               <= (1 + (max_cost_increase / 100)) * Fuel_cost_data['petroleum diesel']['cost']
    model.cost_increase = Constraint(rule=total_cost_increase)

    # Solve the optimization problem using GLPK (replace with 'gurobi' if available)
    solver = SolverFactory('glpk')
    result = solver.solve(model)

    if result.solver.status == SolverStatus.ok and result.solver.termination_condition == TerminationCondition.optimal:
        print(f"Rail optimization succeeded")

        allocations = {f: model.allocation[f].value for f in mode_fuel_options["Rail"]}
        minimized_ghg = model.objective()
        total_cost = sum(
            model.allocation[f].value * (Fuel_cost_data[f]['cost'] / tonnage)
            for f in mode_fuel_options["Rail"]
        )
        total_lcotkm = sum(
            model.allocation[f].value * (Fuel_cost_data[f]['lcotkm'] / tonnage)
            for f in mode_fuel_options["Rail"]
        )

        results = {
            "allocations":    allocations,
            "percent_ghg":    ((minimized_ghg / Fuel_cost_data['petroleum diesel']['emissions']) - 1) * 100,
            "percent_cost":   ((total_cost / Fuel_cost_data['petroleum diesel']['cost']) - 1) * 100,
            "percent_lcotkm": ((total_lcotkm / Fuel_cost_data['petroleum diesel']['lcotkm']) - 1) * 100
        }
    else:
        print(f"Rail optimization failed")
        results = {"allocations": None, "percent_ghg": None, "percent_cost": None, "percent_lcotkm": None}

    return results

# end code
