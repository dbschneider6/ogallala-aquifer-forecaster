import csv
import matplotlib.pyplot as plt
from collections import defaultdict

# ─────────────────────────────────────────────
# SECTION 1: Load historical water level data
# ─────────────────────────────────────────────

def load_data(filepath):
    data = defaultdict(list)

    with open(filepath, newline='', encoding='utf-8-sig') as f:
        all_lines = f.readlines()

    # Find the real data header
    header_index = None
    for i, line in enumerate(all_lines):
        if 'StateWellNumber' in line:
            header_index = i
            break

    if header_index is None:
        print("ERROR: Could not find header row in CSV")
        return data

    data_lines = all_lines[header_index:]
    reader = csv.DictReader(data_lines)

    for row in reader:
        try:
            # Real data rows start with a numeric well number
            # Lookup table rows won't have a numeric StateWellNumber
            well_num = row['StateWellNumber'].strip()
            if not well_num.isdigit():
                continue

            county = row['County'].strip()
            raw_date = row['Date'].strip()
            depth_str = row['WaterLevel'].strip()

            if not raw_date or not depth_str or not county:
                continue

            year = int(raw_date.split('/')[-1])
            if year < 1900 or year > 2030:
                continue

            obs_code = row['ObsCode'].strip()
            if obs_code not in ['M', 'S', 'L', 'C']:
                continue

            depth = float(depth_str)
            if depth < 50 or depth > 260:
                continue

            data[county].append((year, depth))

        except (ValueError, KeyError):
            continue

    for county in data:
        data[county].sort()

    return data

# ─────────────────────────────────────────────
# SECTION 2: Calculate historical decline rate
# ─────────────────────────────────────────────

def calculate_decline_rate(county_data):
    """
    Simple linear regression to find how fast the
    water level is dropping (feet per year).
    """
    years  = [point[0] for point in county_data]
    depths = [point[1] for point in county_data]

    n = len(years)
    mean_x = sum(years) / n
    mean_y = sum(depths) / n

    numerator   = sum((years[i] - mean_x) * (depths[i] - mean_y) for i in range(n))
    denominator = sum((years[i] - mean_x) ** 2 for i in range(n))

    slope     = numerator / denominator
    intercept = mean_y - slope * mean_x

    return slope, intercept


# ─────────────────────────────────────────────
# SECTION 3: Convert Fermi water usage to
#            aquifer depth impact
# ─────────────────────────────────────────────

def gallons_per_day_to_feet_per_year(gallons_per_day, aquifer_area_acres, porosity=0.15):
    """
    Converts Fermi's daily water withdrawal into equivalent
    feet of aquifer depth lost per year across Carson County.

    1 acre-foot = 325,851 gallons
    Porosity = fraction of rock that holds water (~15% for Ogallala)
    """
    gallons_per_year   = gallons_per_day * 365
    acre_feet_per_year = gallons_per_year / 325_851
    feet_per_year      = acre_feet_per_year / (aquifer_area_acres * porosity)
    return feet_per_year


# ─────────────────────────────────────────────
# SECTION 4: Project future depletion
# ─────────────────────────────────────────────

CARSON_COUNTY_ACRES = 560_000
OGALLALA_POROSITY   = 0.15
START_YEAR          = 2025
END_YEAR            = 2140

FERMI_SCENARIOS = {
    "No Fermi (baseline)":          0,
    "Low use (city cap)":           5_500_000,
    "Medium use (hybrid cooling)":  13_200_000,
    "High use (max disclosed)":     27_500_000,
}

SCENARIO_COLORS = {
    "No Fermi (baseline)":          "#2ecc71",
    "Low use (city cap)":           "#3498db",
    "Medium use (hybrid cooling)":  "#e67e22",
    "High use (max disclosed)":     "#e74c3c",
}


def project_depletion(baseline_slope, start_depth, start_year, end_year,
                      fermi_gallons_per_day):
    fermi_additional = gallons_per_day_to_feet_per_year(
        fermi_gallons_per_day, CARSON_COUNTY_ACRES, OGALLALA_POROSITY
    )
    total_slope = baseline_slope + fermi_additional

    years  = list(range(start_year, end_year + 1))
    depths = [start_depth + total_slope * (year - start_year) for year in years]

    return years, depths


def years_until_critical(years, depths, critical_depth=300):
    """Find the year when depth hits the critical pumping threshold."""
    for i, depth in enumerate(depths):
        if depth >= critical_depth:
            return years[i]
    return None


# ─────────────────────────────────────────────
# SECTION 5: Plot results
# ─────────────────────────────────────────────

def plot_results(all_scenarios, historical_data, county="Carson"):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    fig.suptitle(
        f"Ogallala Aquifer Depletion Analysis — {county} County, TX\n"
        f"Project Matador (Fermi America) Impact Scenarios",
        fontsize=14, fontweight='bold', y=0.98
    )

    # ── Panel 1: Historical trend ──────────────────
    # Average readings by year so the chart isn't overcrowded
    from collections import defaultdict
    yearly = defaultdict(list)
    for year, depth in historical_data:
        yearly[year].append(depth)
    
    avg_years  = sorted(y for y in yearly.keys() if y >= 1960)
    avg_depths = [sum(yearly[y]) / len(yearly[y]) for y in avg_years]

    ax1.scatter(avg_years, avg_depths, color='#2c3e50', zorder=5,
                label='Annual avg depth to water (TWDB)', s=40)
    hist_years  = avg_years

    slope, intercept = calculate_decline_rate(historical_data)
    trend_years  = list(range(min(hist_years), max(hist_years) + 1))
    trend_depths = [slope * y + intercept for y in trend_years]
    ax1.plot(trend_years, trend_depths, '--', color='#e74c3c', linewidth=1.5,
             label=f'Linear trend ({slope:.2f} ft/year deeper)')

    ax1.set_xlabel('Year')
    ax1.set_ylabel('Depth to Water (feet below surface)')
    ax1.set_title('Historical Water Level Decline (1960–2025) — Annual Averages, 7 Panhandle Counties')
    ax1.legend(fontsize=9,)
    ax1.invert_yaxis()
    ax1.grid(True, alpha=0.3)
    ax1.annotate('Deeper = more depleted', xy=(0.02, 0.05),
                 xycoords='axes fraction', fontsize=8, color='gray')

    # ── Panel 2: Future projections ────────────────
    critical_threshold = 300

    for label, (years, depths) in all_scenarios.items():
        color = SCENARIO_COLORS[label]
        ax2.plot(years, depths, linewidth=2.5, color=color, label=label)

        crit_year = years_until_critical(years, depths, critical_threshold)
        if crit_year:
            crit_idx = years.index(crit_year)
            ax2.annotate(
                f'{crit_year}',
                xy=(crit_year, depths[crit_idx]),
                xytext=(crit_year + 1, depths[crit_idx] - 3),
                fontsize=7, color=color, fontweight='bold'
            )

    ax2.axhline(y=critical_threshold, color='black', linestyle=':', linewidth=1,
                label=f'Critical threshold ({critical_threshold} ft)')
    ax2.axvline(x=START_YEAR, color='gray', linestyle='--', linewidth=1, alpha=0.5,
                label='Fermi construction begins (2025)')

    ax2.set_xlabel('Year')
    ax2.set_ylabel('Depth to Water (feet below surface)')
    ax2.set_title('Projected Depletion Under Fermi Project Matador Water Usage Scenarios')
    ax2.legend(fontsize=8, loc='upper right')
    ax2.invert_yaxis()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('ogallala_forecast.png', dpi=150, bbox_inches='tight')
    print("Chart saved as ogallala_forecast.png")
    plt.show()


# ─────────────────────────────────────────────
# SECTION 6: Print summary
# ─────────────────────────────────────────────

def print_summary(all_scenarios, historical_slope):
    print("\n" + "="*60)
    print("OGALLALA AQUIFER DEPLETION SUMMARY — CARSON COUNTY")
    print("="*60)
    print(f"Historical decline rate:  {historical_slope:.2f} ft/year")
    print(f"Critical threshold:       300 ft depth")
    print(f"Forecast window:          {START_YEAR}–{END_YEAR}")
    print()
    print(f"{'Scenario':<35} {'Extra ft/yr':>12} {'Critical year':>14}")
    print("-"*63)

    for label, (years, depths) in all_scenarios.items():
        gallons  = FERMI_SCENARIOS[label]
        extra    = gallons_per_day_to_feet_per_year(gallons, CARSON_COUNTY_ACRES, OGALLALA_POROSITY)
        crit_year = years_until_critical(years, depths, 300)
        crit_str  = str(crit_year) if crit_year else f">{END_YEAR}"
        print(f"{label:<35} {extra:>+12.4f} {crit_str:>14}")

    print()
    print("Data sources:")
    print("  TWDB GWDB: https://www3.twdb.texas.gov/apps/reports/GWDB/WaterLevelsByAquifer")
    print("  USGS SIR 2022-5026 (North Plains GCD, TX Panhandle)")
    print("  Fermi America city council filings (Oct 2025, public record)")
    print("="*60)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("Loading aquifer data...")
    all_data    = load_data('ogallala_panhandle_data.csv')
    # Combine all panhandle counties into one regional dataset
    target_counties = ["Carson", "Potter", "Randall", "Deaf Smith", 
                       "Moore", "Oldham", "Hartley"]
    
    county_data = []
    for c in target_counties:
        if c in all_data:
            county_data.extend(all_data[c])
            print(f"  {c}: {len(all_data[c])} readings")
        else:
            print(f"  {c}: no data found")
    
    county_data.sort()
    county = "TX Panhandle Region (7 Counties)"
    print(f"Total combined: {len(county_data)} readings")

    print(f"Loaded {len(county_data)} data points for {county} County")

    slope, intercept = calculate_decline_rate(county_data)
    print(f"Historical decline rate: {slope:.3f} ft/year")

    latest_year, latest_depth = county_data[-1]
    print(f"Most recent observation: {latest_depth} ft depth in {latest_year}")

    all_scenarios = {}
    for label, gallons_per_day in FERMI_SCENARIOS.items():
        years, depths = project_depletion(
            baseline_slope=slope,
            start_depth=latest_depth,
            start_year=START_YEAR,
            end_year=END_YEAR,
            fermi_gallons_per_day=gallons_per_day
        )
        all_scenarios[label] = (years, depths)

    print_summary(all_scenarios, slope)
    plot_results(all_scenarios, county_data, county=county)


if __name__ == "__main__":
    main()