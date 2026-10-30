import os

import streamlit as st
import pandas as pd
import numpy as np
import re
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import plotly.express as px
#import BaselineObj
import MultiObjOpt_module
import MultiObjOpt_module_Maritime
import MultiObjOpt_module_Rail
from sqlalchemy import create_engine, text


def get_setting(name):
    """Read deployment configuration from environment or Streamlit secrets."""
    value = os.getenv(name)
    if value:
        return value
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    if value:
        return str(value)
    raise RuntimeError(f"Required runtime setting '{name}' is not configured.")


@st.cache_resource
def get_engine(database_url):
    """Reuse a SQLAlchemy connection pool across Streamlit reruns."""
    return create_engine(database_url, pool_pre_ping=True)


@st.cache_data(ttl=300)
def load_highway_facilities(database_url):
    query = """
    SELECT DISTINCT FACNAME, FACLTYTYPE, State, FAC_ID
    FROM dbo.ModelingNetwork_IntermodalStationLocations_Simplified
    WHERE FACNAME IS NOT NULL
    ORDER BY State, FACNAME
    """
    return pd.read_sql(query, get_engine(database_url))


@st.cache_data
def load_rail_station_list(database_url, query):
    return pd.read_sql(query, get_engine(database_url))


@st.cache_data
def load_maritime_freight_volume(csv_path):
    return pd.read_csv(csv_path)


@st.cache_data
def load_maritime_simulation_data(parquet_path):
    return pd.read_parquet(parquet_path)

# Title and Description
st.title("Freight Transportation Fuel Optimization Dashboard")
st.write("This dashboard helps optimize fuel allocations for different transport modes (Highway, Rail, Maritime) "
         "based on cost and emissions. Adjust parameters, upload data, and visualize the results.")

# Sidebar Section for Inputs
st.sidebar.header("User Inputs")

# ── Mode selector ──────────────────────────────────────────────────────────────
st.sidebar.subheader("Select Transportation Mode")
selected_mode = st.sidebar.radio("Mode:", ["Highway", "Rail", "Maritime"])

# Store file data in session state
if "facilities_loaded" not in st.session_state:
    st.session_state.facilities_loaded = False

# Cost Increase Limit
st.sidebar.subheader("Cost Constraints")
max_cost_increase = st.sidebar.slider("Max Cost Increase Allowed (%)", min_value=0, max_value=100, value=20)

# Dropdown for selecting Year
st.sidebar.subheader("Select Year")
years_options = [2025, 2030, 2035, 2040, 2045, 2050]
selected_year = st.sidebar.selectbox("Select Year:", options=years_options)

# ── Fuel options: show only the relevant mode's fuels ─────────────────────────
st.sidebar.subheader("Select Fuels to Consider")
all_fuels = [
    "petroleum diesel", "e-diesel", "FT biofuels", "FT biofuels CCS", "renewable diesel",
    "hydrogen", "LNG", "electricity", "ammonia", "bio-methanol", "e-methanol",
    "HFO", "MDO"
]

fuel_defaults = {
    "Highway":  ["petroleum diesel", "e-diesel", "electricity", "hydrogen",
                 "FT biofuels", "FT biofuels CCS", "renewable diesel"],
    "Rail":     ["petroleum diesel", "e-diesel", "electricity", "hydrogen",
                 "FT biofuels", "FT biofuels CCS", "renewable diesel"],
    "Maritime": ["HFO", "MDO", "LNG", "hydrogen", "ammonia"],
}

selected_fuels = st.sidebar.multiselect(
    f"Fuels for {selected_mode}",
    options=all_fuels,
    default=fuel_defaults[selected_mode]
)

# mode_fuel_options keeps the same interface expected by optimization modules
mode_fuel_options = {selected_mode: selected_fuels}

# ── Scenario dropdowns (shared across all modes) ───────────────────────────────
st.sidebar.subheader("Scenario Selection Breakdown")

hydrogen_options = {
    "h1": "Blue",
    "h2": "Default",
    "h3": "Green advanced cost",
    "h4": "Green default cost"
}
selected_h = st.sidebar.selectbox(
    "Select Hydrogen and Ammonia Scenario (h):",
    options=list(hydrogen_options.keys()),
    format_func=lambda x: f"{x} - {hydrogen_options[x]}"
)

renewable_options = {
    "r1": "Advanced cost",
    "r2": "Constrained",
    "r3": "Default"
}
selected_r = st.sidebar.selectbox(
    "Select Renewable electricity option (r):",
    options=list(renewable_options.keys()),
    format_func=lambda x: f"{x} - {renewable_options[x]}"
)

biomass_options = {
    "b1": "Constrained",
    "b2": "Default"
}
selected_b = st.sidebar.selectbox(
    "Select Biomass supply option (b):",
    options=list(biomass_options.keys()),
    format_func=lambda x: f"{x} - {biomass_options[x]}"
)

nuclear_options = {
    "n1": "Advanced cost",
    "n2": "Default"
}
selected_n = st.sidebar.selectbox(
    "Select Nuclear electricity option (n):",
    options=list(nuclear_options.keys()),
    format_func=lambda x: f"{x} - {nuclear_options[x]}"
)

co2_storage_options = {
    "c1": "Constrained",
    "c2": "Default"
}
selected_c = st.sidebar.selectbox(
    "Select CO2 storage option (c):",
    options=list(co2_storage_options.keys()),
    format_func=lambda x: f"{x} - {co2_storage_options[x]}"
)

emissions_options = {
    "p1": "50% reduction by 2050",
    "p2": "Net zero by 2050",
    "p3": "No policy"
}
selected_p = st.sidebar.selectbox(
    "Select Emissions policy option (p):",
    options=list(emissions_options.keys()),
    format_func=lambda x: f"{x} - {emissions_options[x]}"
)

combined_scenario = f"{selected_h}{selected_r}{selected_b}{selected_n}{selected_c}{selected_p}"

# Rail stations are loaded inside the Rail branch (year-aware query)
if "df_rail_stations" not in st.session_state:
    st.session_state.df_rail_stations = pd.DataFrame(columns=["NAME", "LocState"])
    st.session_state.rail_stations_loaded = False
    st.session_state.rail_stations_year = None

# ==============================================================================
# ── Route / facility selection — driven by selected_mode ──────────────────────
# ==============================================================================
st.sidebar.subheader("Select Route")

# ── HIGHWAY ───────────────────────────────────────────────────────────────────
if selected_mode == "Highway":
    try:
        highway_database_url = get_setting("HIGHWAY_DATABASE_URL")
        engine = get_engine(highway_database_url)
        st.session_state.df_facilities = load_highway_facilities(highway_database_url)
        st.session_state.facilities_loaded = True
    except Exception:
        st.error("Highway data is unavailable. Configure HIGHWAY_DATABASE_URL and verify database access.")
        st.stop()

    if not st.session_state.facilities_loaded:
        st.error("Highway facilities could not be loaded. Check database connection.")
        st.stop()

    states_hw = sorted(st.session_state.df_facilities["State"].dropna().astype(str).unique())
    selected_state = st.sidebar.selectbox("Select Origin State:", options=states_hw)

    portA_options = st.session_state.df_facilities[
        st.session_state.df_facilities["State"] == selected_state
    ]["FACNAME"].dropna().astype(str).unique()

    selected_portA = st.sidebar.selectbox("Select Origin Facility:", options=portA_options)

    portB_options = st.session_state.df_facilities[
        st.session_state.df_facilities["FACNAME"] != selected_portA
    ]["FACNAME"].unique()
    selected_portB = st.sidebar.selectbox("Select Destination Facility:", options=portB_options)

    # Tonnage level
    st.sidebar.subheader("Tonnage Level")
    selected_tonnage = st.sidebar.selectbox("Select Tonnage Level:", options=['MaxTonnage', 'MinTonnage'])

    # Route selection basis
    st.sidebar.subheader("Route Selection Basis")
    route_selection = st.sidebar.selectbox(
        "Route Selection Basis:", options=['Shortest Path', 'Max Traffic', 'Least Cost']
    )

    # ── Main panel: Highway ───────────────────────────────────────────────────
    st.write("### Selected Highway Scenario Breakdown")
    st.write(f"**Hydrogen and Ammonia (h):** {selected_h} - {hydrogen_options[selected_h]}")
    st.write(f"**Renewable electricity (r):** {selected_r} - {renewable_options[selected_r]}")
    st.write(f"**Biomass supply (b):** {selected_b} - {biomass_options[selected_b]}")
    st.write(f"**Nuclear electricity (n):** {selected_n} - {nuclear_options[selected_n]}")
    st.write(f"**CO2 storage (c):** {selected_c} - {co2_storage_options[selected_c]}")
    st.write(f"**Emissions policy (p):** {selected_p} - {emissions_options[selected_p]}")
    st.write(f"**Origin:** {selected_portA}")
    st.write(f"**Destination:** {selected_portB}")
    st.write(f"**Year:** {selected_year}  |  **Tonnage:** {selected_tonnage}  |  **Route basis:** {route_selection}")
    st.write(f"### Combined Highway Scenario: `{combined_scenario}`")

    # Powertrain query
    query_powertrain = f"""
    SELECT RouteEModelID, Powertrain, ModelName, ModelYear
    FROM dbo.RouteEModel
    WHERE ModelYear = {selected_year}
    ORDER BY Powertrain, ModelName
    """
    df_powertrain = pd.read_sql(query_powertrain, engine)

    def simplify_model_name(model_name):
        if 'sleeper' in model_name.lower():
            return 'sleeper_cab'
        elif 'day' in model_name.lower():
            return 'day_cab'
        else:
            return model_name

    def replace_powertrain_name(powertrain):
        return 'Hydrogen' if powertrain == 'UNDEFINED' else powertrain

    df_powertrain['SimplifiedName']    = df_powertrain['ModelName'].apply(simplify_model_name)
    df_powertrain['DisplayPowertrain'] = df_powertrain['Powertrain'].apply(replace_powertrain_name)
    unique_powertrains = df_powertrain['Powertrain'].unique().tolist()

    selected_models = {}
    cols = st.sidebar.columns(len(unique_powertrains))
    for idx, display_powertrain in enumerate(unique_powertrains):
        original_powertrain = 'UNDEFINED' if display_powertrain == 'Hydrogen' else display_powertrain
        powertrain_models   = df_powertrain[df_powertrain['Powertrain'] == original_powertrain]
        if len(powertrain_models) == 0:
            continue
        simplified_options = powertrain_models['SimplifiedName'].unique().tolist()
        if len(simplified_options) == 0:
            continue
        with cols[idx]:
            selected_simplified = 'day_cab'   # default
        matching_models = powertrain_models[powertrain_models['SimplifiedName'] == selected_simplified]
        if len(matching_models) > 0:
            selected_row = matching_models.iloc[0]
            selected_models[display_powertrain] = {
                'SimplifiedName':    selected_simplified,
                'ModelName':         selected_row['ModelName'],
                'RouteEModelID':     selected_row['RouteEModelID'],
                'OriginalPowertrain': original_powertrain
            }

    # Route query
    query_routes = text("""
    SELECT
        origin_fac.FACNAME  as OriginFacility,
        origin_fac.NodeID   as OriginNodeID,
        dest_fac.FACNAME    as DestinationFacility,
        dest_fac.NodeID     as DestinationNodeID,
        rr.Id               as RollupRouteID,
        rr.Miles            as RollupRouteMiles,
        rrl.InputId         as RouteID,
        rrl.SortIndex
    FROM dbo.RollupRoute rr
    INNER JOIN dbo.ModelingNetwork_IntermodalStationLocations_Simplified origin_fac
        ON rr.OriginNode = origin_fac.NodeID
    INNER JOIN dbo.ModelingNetwork_IntermodalStationLocations_Simplified dest_fac
        ON rr.DestinationNode = dest_fac.NodeID
    INNER JOIN dbo.RollupRouteLink rrl
        ON rr.Id = rrl.RollupRouteId
    WHERE origin_fac.FACNAME = :origin
      AND dest_fac.FACNAME   = :destination
    ORDER BY rrl.SortIndex
    """).bindparams(origin=selected_portA, destination=selected_portB)

    try:
        df_routes = pd.read_sql(query_routes, engine)
        if len(df_routes) > 0:
            route_ids         = df_routes['RouteID'].unique().tolist()
            route_miles       = df_routes['RollupRouteMiles']
            min_miles_route_id = int(df_routes.loc[df_routes['RollupRouteMiles'].idxmin(), 'RouteID'])
            st.write(f"**Route:** {selected_portA} → {selected_portB}")
            st.write(f"**Shortest route distance:** {min(route_miles)} miles")

            cache_key = f"{selected_portA}_{selected_portB}_{selected_year}_{selected_tonnage}_{combined_scenario}_{route_selection}"
            if 'tonnage_cache' not in st.session_state:
                st.session_state.tonnage_cache = {}

            if cache_key not in st.session_state.tonnage_cache:
                with st.spinner('Loading baseline data...'):
                    fuel_powertrain_map = {
                        'petroleum diesel': 'HEAVY_DUTY',
                        'e-diesel':         'HEAVY_DUTY',
                        'FT biofuels':      'HEAVY_DUTY',
                        'FT biofuels CCS':  'HEAVY_DUTY',
                        'renewable diesel': 'HEAVY_DUTY',
                        'electricity':      'BEV',
                        'hydrogen':         'UNDEFINED'
                    }
                    fuel_conditions = []
                    for fuel in mode_fuel_options['Highway']:
                        if fuel in fuel_powertrain_map:
                            powertrain = fuel_powertrain_map[fuel]
                            if powertrain in selected_models:
                                model_id = selected_models[powertrain]['RouteEModelID']
                                fuel_conditions.append(
                                    f"(Fuel = '{fuel}' AND Powertrain = '{powertrain}' AND RouteEModelID = {model_id})"
                                )

                    if fuel_conditions:
                        try:
                            query_emissions = f"""
                            SELECT
                                Fuel, Powertrain, RouteEModelID, RouteID, Lcotkm, GjPerTrip,
                                MAX(Tonnage) as Tonnage,
                                SUM(TotalCostDisc) as TotalCostDiscounted,
                                SUM(Co2eLifetimeKg) as TotalCo2eLifetimeKg,
                                CASE WHEN MAX(Tonnage) > 0 THEN SUM(TotalCostDisc) / MAX(Tonnage) ELSE 0 END as CostPerTon,
                                CASE WHEN MAX(Tonnage) > 0 THEN SUM(Co2eLifetimeKg) / MAX(Tonnage) ELSE 0 END as EmissionsPerTon_Lifetime_kg,
                                COUNT(DISTINCT RouteID) as NumRoutes
                            FROM dbo.vDissolvedRouteEResult{selected_year}_Joined
                            WHERE RouteID IN ({','.join(map(str, route_ids))})
                              AND FreightYear = {selected_year}
                              AND Scenario = '{combined_scenario}'
                              AND TonnageSourceLookupValue = '{selected_tonnage}'
                              AND ({' OR '.join(fuel_conditions)})
                            GROUP BY Fuel, Powertrain, RouteEModelID, RouteID, Lcotkm, GjPerTrip
                            ORDER BY Powertrain, Fuel
                            """
                            df_emissions = pd.read_sql(query_emissions, engine)
                            st.session_state.tonnage_cache[cache_key] = df_emissions
                        except Exception as e:
                            st.error(f"Error querying emissions: {e}")
                            df_emissions = pd.DataFrame()

                        st.write(f"### Emissions and Costs by Fuel — {selected_year} | Scenario: {combined_scenario}")

                        if len(df_emissions) > 0:
                            st.session_state.tonnage_cache[cache_key] = {}
                            for fuel in mode_fuel_options["Highway"]:
                                fuel_data = df_emissions[df_emissions['Fuel'] == fuel]
                                if len(fuel_data) > 0:
                                    if route_selection == 'Shortest Path':
                                        row = fuel_data.loc[fuel_data['RouteID'] == min_miles_route_id]
                                        if len(row) > 0:
                                            st.session_state.tonnage_cache[cache_key][fuel] = {
                                                'tonnage':   float(row['Tonnage'].iloc[0]),
                                                'cost':      float(row['TotalCostDiscounted'].iloc[0]),
                                                'emissions': float(row['TotalCo2eLifetimeKg'].iloc[0]),
                                                'energyuse': float(row['GjPerTrip'].iloc[0]),
                                                'lcotkm':    float(row['Lcotkm'].iloc[0])
                                            }
                                        else:
                                            st.warning(f"No data for RouteID {min_miles_route_id} and Fuel {fuel}")
                                    elif route_selection == 'Max Traffic':
                                        row = fuel_data.loc[fuel_data['Tonnage'].idxmax()]
                                        st.session_state.tonnage_cache[cache_key][fuel] = {
                                            'tonnage':   row['Tonnage'],
                                            'cost':      row['TotalCostDiscounted'],
                                            'emissions': row['TotalCo2eLifetimeKg'],
                                            'energyuse': row['GjPerTrip'],
                                            'lcotkm':    row['Lcotkm']
                                        }
                                    elif route_selection == 'Least Cost':
                                        row = fuel_data.loc[fuel_data['TotalCostDiscounted'].idxmin()]
                                        st.session_state.tonnage_cache[cache_key][fuel] = {
                                            'tonnage':   row['Tonnage'],
                                            'cost':      row['TotalCostDiscounted'],
                                            'emissions': row['TotalCo2eLifetimeKg'],
                                            'energyuse': row['GjPerTrip'],
                                            'lcotkm':    row['Lcotkm']
                                        }

                            if 'petroleum diesel' in st.session_state.tonnage_cache[cache_key]:
                                d = st.session_state.tonnage_cache[cache_key]['petroleum diesel']
                                st.write(f"**Baseline (petroleum diesel) — {selected_year}, Scenario: {combined_scenario}**")
                                st.write(f"**Total CO2e Lifetime:** {d['emissions']:,.2f} kg")
                                st.write(f"**Total Cost:** ${d['cost']:,.2f}")
                                st.write(f"**Total Tonnage:** {d['tonnage']:,.2f} tons")
                                st.write(f"**Energy Usage:** {d['energyuse']:,.2f} GJ")
                                st.write(f"**LCOTKM:** {d['lcotkm']:,.2f} $/km-ton")
                        else:
                            st.warning("No emissions data available.")
                    else:
                        st.warning("No valid fuel-powertrain combinations selected.")
        else:
            st.warning("No routes found between these facilities.")
    except Exception as e:
        st.error(f"Error querying routes: {e}")

    # ── Highway optimization button ───────────────────────────────────────────
    Fuel_data_dict = {}
    if 'tonnage_cache' in st.session_state and 'cache_key' in dir() and cache_key in st.session_state.tonnage_cache:
        for fuel in mode_fuel_options['Highway']:
            if fuel in st.session_state.tonnage_cache[cache_key]:
                Fuel_data_dict[fuel] = st.session_state.tonnage_cache[cache_key][fuel]

    if st.sidebar.button("Run Optimization"):
        try:
            st.write("**Running Optimization for Highway Fuels...**")
            highway_results = MultiObjOpt_module.Run(
                Fuel_data_dict, max_cost_increase, "Highway", mode_fuel_options
            )
            st.success("Highway Optimization Complete!")
            st.header("Optimization Results")
            total_tonnage = Fuel_data_dict['petroleum diesel']['tonnage']
            for fuel, allocation in highway_results['allocations'].items():
                pct = round((allocation / total_tonnage) * 100)
                st.write(f"**Fuel Allocation %:** {fuel} - {pct}%")
            st.write(f"**Percent GHG change:** {highway_results['percent_ghg']:.2f}%")
            st.write(f"**Percent Cost change:** {highway_results['percent_cost']:.2f}%")
            st.write(f"**Percent LCOTKM change:** {highway_results['percent_lcotkm']:.2f}%")
        except Exception as e:
            st.error(f"Error during Highway optimization: {e}")


# ── RAIL ───────────────────────────────────────────────────────────────────────
elif selected_mode == "Rail":
    try:
        rail_database_url = get_setting("RAIL_DATABASE_URL")
        engine_rail = get_engine(rail_database_url)
    except Exception:
        st.error("Rail data is unavailable. Configure RAIL_DATABASE_URL and verify database access.")
        st.stop()

    # ── Load rail stations for the selected year (only stations with actual routes) ──
    if st.session_state.rail_stations_year != selected_year:
        with st.spinner(f"Loading Rail stations for {selected_year}..."):
            try:
                query_rail_stations = f"""
                SELECT DISTINCT stn.NAME, stn.LocState
                FROM AltriosResults.Results{selected_year} r
                JOIN AltriosResults.RouteDefinition rd ON r.RouteId = rd.RouteId
                JOIN AltriosResults.ARPAE_STATIONSWITHNEARNODES stn
                    ON rd.OriginUniqueID = stn.UNQUIEID
                    OR rd.DestinationUniqueID = stn.UNQUIEID
                WHERE stn.NAME IS NOT NULL
                ORDER BY stn.LocState, stn.NAME
                """
                st.session_state.df_rail_stations = load_rail_station_list(
                    rail_database_url, query_rail_stations
                )
                st.session_state.rail_stations_loaded = True
                st.session_state.rail_stations_year = selected_year
            except Exception as e:
                st.error(f"Error loading Rail stations: {e}")
                st.session_state.df_rail_stations = pd.DataFrame(columns=["NAME", "LocState"])
                st.session_state.rail_stations_loaded = False

    if not st.session_state.rail_stations_loaded or len(st.session_state.df_rail_stations) == 0:
        st.error("Rail station data could not be loaded. Check ARPAERail database connection.")
        st.stop()

    states_rail = sorted(st.session_state.df_rail_stations["LocState"].dropna().astype(str).unique())
    selected_state = st.sidebar.selectbox("Select Origin State/Province:", options=states_rail)

    origin_options = sorted(st.session_state.df_rail_stations[
        st.session_state.df_rail_stations["LocState"] == selected_state
    ]["NAME"].dropna().astype(str).unique())

    selected_rail_origin = st.sidebar.selectbox("Select Origin Rail Station:", options=origin_options)

    # Destinations: only stations reachable from the selected origin
    try:
        query_dest = f"""
        SELECT DISTINCT stn_dest.NAME, stn_dest.LocState
        FROM AltriosResults.Results{selected_year} r
        JOIN AltriosResults.RouteDefinition rd ON r.RouteId = rd.RouteId
        JOIN AltriosResults.ARPAE_STATIONSWITHNEARNODES stn_orig
            ON rd.OriginUniqueID = stn_orig.UNQUIEID
        JOIN AltriosResults.ARPAE_STATIONSWITHNEARNODES stn_dest
            ON rd.DestinationUniqueID = stn_dest.UNQUIEID
        WHERE stn_orig.NAME = '{selected_rail_origin}'
          AND stn_dest.NAME IS NOT NULL
        ORDER BY stn_dest.NAME
        """
        df_dest = load_rail_station_list(rail_database_url, query_dest)
        dest_options = sorted(df_dest["NAME"].dropna().astype(str).unique()) if len(df_dest) > 0 else []
    except Exception as e:
        st.error(f"Error loading destinations: {e}")
        dest_options = []

    if len(dest_options) == 0:
        st.warning(f"No destinations found from {selected_rail_origin} for year {selected_year}.")
        st.stop()

    selected_rail_dest = st.sidebar.selectbox("Select Destination Rail Station:", options=dest_options)

    # ── Main panel: Rail ─────────────────────────────────────────────────────
    st.write("### Selected Rail Scenario Breakdown")
    st.write(f"**Hydrogen and Ammonia (h):** {selected_h} - {hydrogen_options[selected_h]}")
    st.write(f"**Renewable electricity (r):** {selected_r} - {renewable_options[selected_r]}")
    st.write(f"**Biomass supply (b):** {selected_b} - {biomass_options[selected_b]}")
    st.write(f"**Nuclear electricity (n):** {selected_n} - {nuclear_options[selected_n]}")
    st.write(f"**CO2 storage (c):** {selected_c} - {co2_storage_options[selected_c]}")
    st.write(f"**Emissions policy (p):** {selected_p} - {emissions_options[selected_p]}")
    st.write(f"**Rail Origin:** {selected_rail_origin}")
    st.write(f"**Rail Destination:** {selected_rail_dest}")
    st.write(f"**Year:** {selected_year}")
    st.write(f"### Combined Rail Scenario: `{combined_scenario}`")

    # Cache key
    rail_cache_key = f"rail_{selected_rail_origin}_{selected_rail_dest}_{selected_year}_{combined_scenario}"
    if 'rail_cache' not in st.session_state:
        st.session_state.rail_cache = {}

    if rail_cache_key not in st.session_state.rail_cache:
        with st.spinner('Loading Rail baseline data...'):
            try:
                # Map display fuel names → Rail DB fuel names (stored lowercase)
                rail_fuel_name_map = {
                    "petroleum diesel": "petroleum diesel",
                    "e-diesel":         "e-diesel",
                    "electricity":      "electricity",
                    "FT biofuels":      "ft biofuels",
                    "FT biofuels CCS":  "ft biofuels ccs",
                    "hydrogen":         "hydrogen",
                    "renewable diesel": "renewable diesel",
                }
                selected_rail_fuels_db = [
                    rail_fuel_name_map[f] for f in mode_fuel_options["Rail"] if f in rail_fuel_name_map
                ]
                rail_fuel_list_sql = ", ".join([f"'{f}'" for f in selected_rail_fuels_db])

                query_rail = f"""
                SELECT
                    ft.FuelType           AS Fuel,
                    rd.OriginUniqueID     AS Origin,
                    rd.DestinationUniqueID AS Destination,
                    r.RouteId,
                    r.TotalTonnageSt      AS Tonnage,
                    r.CostTotalDiscounted AS Cost,
                    r.GHG                 AS Emissions,
                    r.EnergyUsageMJ       AS EnergyUsage,
                    r.LCOTKM              AS Lcotkm
                FROM AltriosResults.Results{selected_year} r
                JOIN Reference.FuelType ft
                    ON r.FuelTypeID = ft.FuelTypeID
                JOIN Reference.GcamScenario gs
                    ON r.GcamScenarioID = gs.GcamScenarioID
                JOIN AltriosResults.RouteDefinition rd
                    ON r.RouteId = rd.RouteId
                JOIN AltriosResults.ARPAE_STATIONSWITHNEARNODES stn_orig
                    ON rd.OriginUniqueID = stn_orig.UNQUIEID
                JOIN AltriosResults.ARPAE_STATIONSWITHNEARNODES stn_dest
                    ON rd.DestinationUniqueID = stn_dest.UNQUIEID
                WHERE gs.Scenario = '{combined_scenario}'
                  AND LOWER(ft.FuelType) IN ({rail_fuel_list_sql})
                  AND stn_orig.NAME = '{selected_rail_origin}'
                  AND stn_dest.NAME = '{selected_rail_dest}'
                ORDER BY ft.FuelType
                """
                df_rail = pd.read_sql(query_rail, engine_rail)

                if len(df_rail) > 0:
                    st.session_state.rail_cache[rail_cache_key] = {}
                    for _, row in df_rail.iterrows():
                        db_fuel = row["Fuel"].lower()
                        display_fuel = next(
                            (k for k, v in rail_fuel_name_map.items() if v == db_fuel), db_fuel
                        )
                        st.session_state.rail_cache[rail_cache_key][display_fuel] = {
                            "tonnage":   float(row["Tonnage"]),
                            "cost":      float(row["Cost"]),
                            "emissions": float(row["Emissions"]),
                            "energyuse": float(row["EnergyUsage"]),
                            "lcotkm":    float(row["Lcotkm"]),
                        }

                    if "petroleum diesel" in st.session_state.rail_cache[rail_cache_key]:
                        d = st.session_state.rail_cache[rail_cache_key]["petroleum diesel"]
                        st.write(f"**Baseline (petroleum diesel) — {selected_year}, Scenario: {combined_scenario}**")
                        st.write(f"**Total GHG:** {d['emissions']:,.2f}")
                        st.write(f"**Total Cost (discounted):** ${d['cost']:,.2f}")
                        st.write(f"**Total Tonnage (short tons):** {d['tonnage']:,.2f}")
                        st.write(f"**Energy Usage:** {d['energyuse']:,.2f} MJ")
                        st.write(f"**LCOTKM:** {d['lcotkm']:,.4f} $/ton-km")
                    else:
                        st.warning("Petroleum diesel baseline not found for this route/scenario/year.")
                else:
                    st.warning("No Rail data found for the selected route, scenario, and year.")

            except Exception as e:
                st.error(f"Error querying Rail data: {e}")

    # Show cached baseline if already loaded
    elif "petroleum diesel" in st.session_state.rail_cache.get(rail_cache_key, {}):
        d = st.session_state.rail_cache[rail_cache_key]["petroleum diesel"]
        st.write(f"**Baseline (petroleum diesel) — {selected_year}, Scenario: {combined_scenario}**")
        st.write(f"**Total GHG:** {d['emissions']:,.2f}")
        st.write(f"**Total Cost (discounted):** ${d['cost']:,.2f}")
        st.write(f"**Total Tonnage (short tons):** {d['tonnage']:,.2f}")
        st.write(f"**Energy Usage:** {d['energyuse']:,.2f} MJ")
        st.write(f"**LCOTKM:** {d['lcotkm']:,.4f} $/ton-km")

    # ── Rail optimization button ──────────────────────────────────────────────
    Fuel_data_dict_rail = {}
    if 'rail_cache' in st.session_state and rail_cache_key in st.session_state.rail_cache:
        for fuel in mode_fuel_options['Rail']:
            if fuel in st.session_state.rail_cache[rail_cache_key]:
                Fuel_data_dict_rail[fuel] = st.session_state.rail_cache[rail_cache_key][fuel]

    if st.sidebar.button("Run Optimization"):
        try:
            if 'petroleum diesel' not in Fuel_data_dict_rail:
                st.error("Petroleum diesel baseline data is required. Please ensure it is selected and data is loaded.")
            else:
                st.write("**Running Optimization for Rail Fuels...**")
                rail_results = MultiObjOpt_module_Rail.Run(
                    Fuel_data_dict_rail, max_cost_increase, "Rail", mode_fuel_options
                )
                st.success("Rail Optimization Complete!")
                st.header("Rail Optimization Results")
                total_tonnage_rail = Fuel_data_dict_rail['petroleum diesel']['tonnage']
                for fuel, allocation in rail_results['allocations'].items():
                    pct = round((allocation / total_tonnage_rail) * 100)
                    st.write(f"**Fuel Allocation %:** {fuel} - {pct}%")
                st.write(f"**Percent GHG change:** {rail_results['percent_ghg']:.2f}%")
                st.write(f"**Percent Cost change:** {rail_results['percent_cost']:.2f}%")
                st.write(f"**Percent LCOTKM change:** {rail_results['percent_lcotkm']:.2f}%")
        except Exception as e:
            st.error(f"Error during Rail optimization: {e}")


# ── MARITIME ───────────────────────────────────────────────────────────────────
elif selected_mode == "Maritime":
    try:
        freight_volume_path = get_setting("MARITIME_FREIGHT_VOLUME_CSV")
        maritime_simulation_path = get_setting("MARITIME_SIMULATION_PARQUET")
        st.session_state.freight_volume_df = load_maritime_freight_volume(freight_volume_path)
        st.session_state.emissions_cost_df = load_maritime_simulation_data(maritime_simulation_path)
    except Exception:
        st.error(
            "Maritime data is unavailable. Configure MARITIME_FREIGHT_VOLUME_CSV and "
            "MARITIME_SIMULATION_PARQUET and verify the protected files are readable."
        )
        st.stop()

    states_mar = sorted(
        st.session_state.freight_volume_df["PortA_state"].dropna().astype(str).unique()
    )
    selected_state = st.sidebar.selectbox("Select Origin State:", options=states_mar)

    portA_options_mar = st.session_state.freight_volume_df[
        st.session_state.freight_volume_df["PortA_state"] == selected_state
    ]["PortA"].dropna().astype(str).unique()
    selected_portA = st.sidebar.selectbox("Select Origin Port:", options=portA_options_mar)

    portB_options_raw = st.session_state.freight_volume_df[
        st.session_state.freight_volume_df["PortA"] == selected_portA
    ]["PortB"].dropna().astype(str).unique()

    if len(portB_options_raw) > 0:
        selected_portB = st.sidebar.selectbox("Select Destination Port:", options=portB_options_raw)
    else:
        st.warning(f"No destination ports found with a connection to {selected_portA}")
        st.stop()

    # Speed
    st.sidebar.subheader("Select Speed")
    speed_options = st.session_state.emissions_cost_df["Speed"].unique()
    selected_speed = st.sidebar.selectbox("Select Speed:", options=speed_options)

    # ── Main panel: Maritime ─────────────────────────────────────────────────
    st.write("### Selected Maritime Scenario Breakdown")
    st.write(f"**Hydrogen and Ammonia (h):** {selected_h} - {hydrogen_options[selected_h]}")
    st.write(f"**Renewable electricity (r):** {selected_r} - {renewable_options[selected_r]}")
    st.write(f"**Biomass supply (b):** {selected_b} - {biomass_options[selected_b]}")
    st.write(f"**Nuclear electricity (n):** {selected_n} - {nuclear_options[selected_n]}")
    st.write(f"**CO2 storage (c):** {selected_c} - {co2_storage_options[selected_c]}")
    st.write(f"**Emissions policy (p):** {selected_p} - {emissions_options[selected_p]}")
    st.write(f"**Port A (Origin):** {selected_portA}")
    st.write(f"**Port B (Destination):** {selected_portB}")
    st.write(f"**Year:** {selected_year}  |  **Speed:** {selected_speed}")
    st.write(f"### Combined Maritime Scenario: `{combined_scenario}`")

    # Freight volume
    filtered_row = st.session_state.freight_volume_df[
        (st.session_state.freight_volume_df["PortA"] == selected_portA) &
        (st.session_state.freight_volume_df["PortB"] == selected_portB)
    ]
    if not filtered_row.empty:
        selected_route      = filtered_row["Route"].values[0]
        freight_volume_tons = filtered_row[f"Freight_Volume (Tons) {selected_year}"].values[0]
        st.write(f"**Freight Volume ({selected_year}):** {freight_volume_tons:,.0f} tons  |  Route: {selected_portA} → {selected_portB}")
    else:
        st.warning("No freight volume data found for the selected route.")
        st.stop()

    # Emissions/cost data
    filtered_row = st.session_state.emissions_cost_df[
        (st.session_state.emissions_cost_df["MainEngineFuelType"].isin(mode_fuel_options["Maritime"])) &
        (st.session_state.emissions_cost_df["route"] == selected_route) &
        (st.session_state.emissions_cost_df["ProjectionYear"] == selected_year) &
        (st.session_state.emissions_cost_df["Speed"] == selected_speed) &
        (st.session_state.emissions_cost_df["Scenario"] == combined_scenario)
    ]

    if not filtered_row.empty:
        fc_gfuel_ton              = filtered_row[["MainEngineFuelType", "FC_gFuel_ton"]]
        energy_demand_mj_ton      = filtered_row[["MainEngineFuelType", "EnergyDemand_MJ_ton"]]
        emissions_gco2e_ton       = filtered_row[["MainEngineFuelType", "Emissions_gCO2e_ton"]]
        transportation_cost_usd_ton = filtered_row[["MainEngineFuelType", "TransportationCost_USD_ton"]]
    else:
        st.warning("No emissions/cost data found for the selected Route, Year, Speed, and Scenario.")
        st.stop()

    # ── Maritime optimization button ──────────────────────────────────────────
    if st.sidebar.button("Run Optimization"):
        try:
            st.write("**Calculating Baseline using HFO...**")
            Baseline_FC_gFuel = (
                fc_gfuel_ton[fc_gfuel_ton["MainEngineFuelType"] == "HFO"]["FC_gFuel_ton"].values
                * freight_volume_tons
            )[0]
            Baseline_EnergyDemand_MJ = (
                energy_demand_mj_ton[energy_demand_mj_ton["MainEngineFuelType"] == "HFO"]["EnergyDemand_MJ_ton"].values
                * freight_volume_tons
            )[0]
            Baseline_Emissions_gCO2 = (
                emissions_gco2e_ton[emissions_gco2e_ton["MainEngineFuelType"] == "HFO"]["Emissions_gCO2e_ton"].values
                * freight_volume_tons
            )[0]
            Baseline_TransportationCost_USD = (
                transportation_cost_usd_ton[transportation_cost_usd_ton["MainEngineFuelType"] == "HFO"]["TransportationCost_USD_ton"].values
                * freight_volume_tons
            )[0]

            st.write(f"**Baseline Fuel Consumption (gFuel):** {Baseline_FC_gFuel:,.2f}")
            st.write(f"**Baseline Energy Demand (MJ):** {Baseline_EnergyDemand_MJ:,.2f}")
            st.write(f"**Baseline Emissions (gCO2e):** {Baseline_Emissions_gCO2:,.2f}")
            st.write(f"**Baseline Transportation Cost (USD):** {Baseline_TransportationCost_USD:,.2f}")

            st.write("**Running Optimization for Maritime Fuels...**")
            maritime_results = MultiObjOpt_module_Maritime.Run(
                freight_volume_tons, fc_gfuel_ton, energy_demand_mj_ton, emissions_gco2e_ton,
                transportation_cost_usd_ton, Baseline_TransportationCost_USD,
                Baseline_Emissions_gCO2, max_cost_increase, "Maritime", mode_fuel_options
            )

            st.success("Maritime Optimization Complete!")
            st.header("Optimization Results")
            for fuel, allocation in maritime_results['allocations'].items():
                pct = round((allocation / freight_volume_tons) * 100)
                st.write(f"**Fuel Allocation %:** {fuel} - {pct}%")
            st.write(f"**Percent GHG change:** {maritime_results['percent_ghg']:.2f}%")
            st.write(f"**Percent Cost change:** {maritime_results['percent_cost']:.2f}%")

        except Exception as e:
            st.error(f"Error during Maritime optimization: {e}")
