def age_distribution_plot(
    city_name: str,
    output_dir: str,
    render_dir: str,
    font_dict: dict
):
    """
    Generate population age–sex distribution plots and demographic summary.

    This function:
    1. Reads a tabular demographic CSV (by age group and sex)
    2. Harmonizes age bins (0–1 and 1–4 into 0–4)
    3. Aggregates population counts
    4. Produces:
       - A static Matplotlib bar chart (PNG)
       - An interactive Plotly bar chart (HTML)
    5. Computes high-level demographic indicators
    6. Saves a YAML summary interpretation

    Parameters
    ----------
    city_name : str
        Display name of the city (used in titles).
    output_dir : str
        Base output directory where plots and summaries are saved.
    render_dir : str
        Directory where resulting plots will be stored.
    font_dict : dict
        Font configuration dictionary for Plotly layout.

    Returns
    -------
    None
        Outputs are written to disk (PNG, HTML, YAML).
    """

    import os
    import pandas as pd
    import matplotlib.pyplot as plt
    import plotly.express as px
    import yaml

    # ------------------------------------------------------------------
    # File paths
    # ------------------------------------------------------------------
    tabular_dir = os.path.join(output_dir, "tabular")
    os.makedirs(tabular_dir, exist_ok=True)
    csv_path = os.path.join(tabular_dir, f"{city_name}_demographic.csv")
    png_path = os.path.join(render_dir, f"plots/png/{city_name}_age_stats.png")
    html_path = os.path.join(render_dir, f"plots/html/{city_name}_age_stats.html")
    yaml_path = os.path.join(tabular_dir, f"{city_name}_demographics_summary.yml")

    # ------------------------------------------------------------------
    # Load and clean demographic data
    # ------------------------------------------------------------------
    df = pd.read_csv(csv_path)

    # Standardize column names
    df = df.rename(columns={
        "age_group": "Age_Bracket",
        "sex": "Sex"
    })

    # Ensure population values are numeric
    df["Count"] = pd.to_numeric(df["population"], errors="coerce")

    # Merge infant age groups into a single 0–4 bin
    df["Age_Bracket"] = df["Age_Bracket"].replace({
        "0-1": "0-4",
        "1-4": "0-4"
    })

    # Explicit age ordering for plots and aggregation
    age_order = [
        "0-4", "5-9", "10-14", "15-19", "20-24", "25-29",
        "30-34", "35-39", "40-44", "45-49", "50-54",
        "55-59", "60-64", "65-69", "70-74", "75-79", "80+"
    ]

    df["Age_Bracket"] = pd.Categorical(
        df["Age_Bracket"],
        categories=age_order,
        ordered=True
    )

    # Aggregate population counts by age and sex
    df = (
        df.groupby(["Age_Bracket", "Sex"], as_index=False)
          .agg(Count=("Count", "sum"))
    )

    # ------------------------------------------------------------------
    # Percentage calculations
    # ------------------------------------------------------------------
    df["Percentage"] = (
        df.groupby("Sex")["Count"]
          .transform(lambda x: x / x.sum() * 100)
    )

    # Retained for legacy logic (used later in interpretation)
    df["Sexed_Percent"] = df["Percentage"]
    df["Sexed_Percent_cum"] = (
        df.groupby("Sex")["Sexed_Percent"].cumsum()
    )

    # ------------------------------------------------------------------
    # Static Matplotlib plot (PNG)
    # ------------------------------------------------------------------

    # Ensure consistent age ordering
    df_sorted = df.sort_values("Age_Bracket")

    # Split by sex
    df_female = df_sorted[df_sorted["Sex"] == "f"]
    df_male = df_sorted[df_sorted["Sex"] == "m"]

    x = range(len(age_order))
    bar_width = 0.4

    plt.figure(figsize=(8, 6))

    # Female bars
    plt.bar(
        [i - bar_width / 2 for i in x],
        df_female["Percentage"],
        width=bar_width,
        color="red",
        label="Female"
    )

    # Male bars
    plt.bar(
        [i + bar_width / 2 for i in x],
        df_male["Percentage"],
        width=bar_width,
        color="blue",
        label="Male"
    )

    plt.title(f"Population distribution in {city_name} by sex")
    plt.xlabel("Age Bracket")
    plt.ylabel("Percentage")

    plt.xticks(x, age_order, rotation=45)
    plt.legend(title="Sex", loc="upper right")

    plt.tight_layout()
    plt.savefig(png_path)
    plt.close()


    # ------------------------------------------------------------------
    # Interactive Plotly bar chart (HTML)
    # ------------------------------------------------------------------
    df_sorted = df.sort_values("Age_Bracket")

    fig = px.bar(
        df_sorted,
        x="Age_Bracket",
        y="Percentage",
        color="Sex",
        barmode="group",
        labels={
            "Age_Bracket": "Age Bracket",
            "Percentage": "Percentage",
            "Sex": "Sex"
        },
        color_discrete_map={"f": "red", "m": "blue"}
    )

    fig.update_layout(
        template="plotly_white",
        xaxis_title="",
        yaxis_title="Percentage of Age Distribution",
        legend_title="",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.4,
            xanchor="center",
            x=0.5
        ),
        xaxis=dict(linecolor="black"),
        yaxis=dict(linecolor="black"),
        autosize=True,
        font=font_dict,
        plot_bgcolor="white"
    )

    # Replace sex codes with readable labels
    fig.for_each_trace(
        lambda t: t.update(name="Female" if t.name == "f" else "Male")
    )

    fig.update_xaxes(tickangle=45)
    fig.write_html(html_path, full_html=False, include_plotlyjs="cdn")

    # ------------------------------------------------------------------
    # Demographic summary indicators
    # ------------------------------------------------------------------
    under5 = df[df["Age_Bracket"] == "0-4"]["Percentage"].sum()
    youth = df[df["Age_Bracket"].isin(["15-19", "20-24"])]["Percentage"].sum()

    working_age_rows = df[df["Age_Bracket"].isin([
        "15-19", "20-24", "25-29", "30-34", "35-39",
        "40-44", "45-49", "50-54", "55-59", "60-64"
    ])]
    working_age = working_age_rows["Percentage"].sum() / df["Percentage"].sum()

    elderly = df[df["Age_Bracket"].isin([
        "60-64", "65-69", "70-74", "75-79", "80+"
    ])]["Percentage"].sum()

    male_count = df[df["Sex"] == "m"]["Count"].sum()
    female_count = df[df["Sex"] == "f"]["Count"].sum()
    sex_ratio = male_count / female_count * 100

    reproductive_age = df[
        (df["Sex"] == "f") &
        (df["Age_Bracket"].isin([
            "15-19", "20-24", "25-29", "30-34",
            "35-39", "40-44", "45-49"
        ]))
    ]["Sexed_Percent"].sum()

    # ------------------------------------------------------------------
    # Save YAML summary
    # ------------------------------------------------------------------
    summary_data = {
        "under5": f"{under5:.2f}%",
        "youth (15-24)": f"{youth:.2f}%",
        "working_age (15-64)": f"{working_age:.2f}%",
        "elderly (60+)": f"{elderly:.2f}%",
        "reproductive_age, percent of women (15-49)": f"{reproductive_age:.2f}%",
        "sex_ratio": f"{round(sex_ratio, 2)} males to 100 females"
    }

    with open(yaml_path, "w") as f:
        yaml.dump(summary_data, f, default_flow_style=False)
