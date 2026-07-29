import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# ======================================================================
# Page configuration
# ======================================================================

st.set_page_config(
    page_title="Traffic Consumption Grapher",
    layout="wide"
)

# ======================================================================
# Configuration constants
# ======================================================================

# Time interval (in seconds) used to convert octets to bits per second.
# 900 seconds = 15 minutes
INTERVAL_SEG = 900

# Separators that may combine multiple values in the "Affected Paths" column
PATH_SEPARATORS = ["\ufffd", "\u00a6"]  # "�" replacement char, and "¦" broken bar


# ======================================================================
# Utility functions
# ======================================================================

def escalate_bits(value):
    """
    Scale a bits-per-second value to the most appropriate unit.

    Returns:
        tuple: (scaled_value, unit_string)
               Example: (125, 'Mb/s')
    """
    if value >= 1e12:
        return value / 1e12, "Tb/s"
    elif value >= 1e9:
        return value / 1e9, "Gb/s"
    elif value >= 1e6:
        return value / 1e6, "Mb/s"
    elif value >= 1e3:
        return value / 1e3, "Kb/s"
    else:
        return value, "b/s"


def extract_first_path(value):
    """Return only the portion of the string before the first separator found."""
    if pd.isna(value):
        return None
    text = str(value)
    positions = [text.find(sep) for sep in PATH_SEPARATORS if sep in text]
    if positions:
        cut_index = min(positions)
        text = text[:cut_index]
    return text.strip()


def calculate_bps(row):
    """
    Calculate bits per second for a row based on traffic direction.

    - Incoming  -> uses 'OCTETS'
    - Outgoing  -> uses 'OCTETS'

    Returns:
        float or None
    """
    if row["Direction"] == "Incoming":
        octets = row["OCTETS"]
    elif row["Direction"] == "Outgoing":
        octets = row["OCTETS"]
    else:
        return None

    if pd.isna(octets):
        return None

    return (octets * 8) / INTERVAL_SEG


@st.cache_data
def process_csv(file_bytes):
    """
    Load and process the uploaded CSV file.
    Cached so re-running the app doesn't reprocess the same file.
    """
    df = pd.read_csv(file_bytes, quotechar='"', encoding='latin-1')

    df["Period End Time"] = pd.to_datetime(
        df["Period End Time"],
        format="%m/%d/%Y, %I:%M:%S %p"
    )

    df["OCTETS"] = pd.to_numeric(df["OCTETS"], errors="coerce")

    df["bps"] = df.apply(calculate_bps, axis=1)
    df = df.dropna(subset=["bps"])

    max_bps = df["bps"].max()
    _, unit = escalate_bits(max_bps)

    factor = {
        "b/s": 1,
        "Kb/s": 1e3,
        "Mb/s": 1e6,
        "Gb/s": 1e9,
        "Tb/s": 1e12
    }[unit]

    df["scaled_bps"] = df["bps"] / factor

    df["Flow"] = df["Direction"].map({
        "Incoming": "Ingress",
        "Outgoing": "Egress"
    })

    df = df.sort_values("Period End Time")

    return df, unit


def build_titles(df):
    """Extract dynamic main title and subtitle from the dataframe."""
    affected_paths_raw = df["Affected Paths"].dropna().unique()
    extracted_paths = [extract_first_path(v) for v in affected_paths_raw]
    affected_paths = list(dict.fromkeys(extracted_paths))

    if len(affected_paths) == 1:
        main_title = f"{affected_paths[0]} Traffic Consumption Graph"
    elif len(affected_paths) > 1:
        main_title = f"{', '.join(affected_paths)} Traffic Consumption Graph"
    else:
        main_title = "Traffic Consumption Graph"

    system_names = df["NE/System Name"].dropna().unique()

    if len(system_names) == 1:
        subtitle = system_names[0]
    elif len(system_names) > 1:
        subtitle = ", ".join(system_names)
    else:
        subtitle = ""

    return main_title, subtitle


def build_figure(df, unit, main_title, subtitle):
    """Build the Plotly figure with Egress and Ingress traces."""
    fig = go.Figure()

    df_egress = df[df["Flow"] == "Egress"]
    fig.add_trace(go.Scatter(
        x=df_egress["Period End Time"],
        y=df_egress["scaled_bps"],
        mode="lines",
        name="Egress",
        customdata=df_egress["bps"],
        hovertemplate=(
            "%{x}<br>"
            "%{y:.2f} " + unit +
            "<br>%{customdata:,.0f} b/s"
            "<extra></extra>"
        )
    ))

    df_ingress = df[df["Flow"] == "Ingress"]
    fig.add_trace(go.Scatter(
        x=df_ingress["Period End Time"],
        y=df_ingress["scaled_bps"],
        mode="lines",
        name="Ingress",
        customdata=df_ingress["bps"],
        hovertemplate=(
            "%{x}<br>"
            "%{y:.2f} " + unit +
            "<br>%{customdata:,.0f} b/s"
            "<extra></extra>"
        )
    ))

    fig.update_layout(
        title=dict(
            text=f"{main_title}<br><sup>{subtitle}</sup>",
            x=0.5,
            xanchor="center"
        ),
        xaxis=dict(
            title="Date & Time",
            type="date",
            tickformat="%d/%m/%Y %H:%M",
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1h", step="hour", stepmode="backward"),
                    dict(count=6, label="6h", step="hour", stepmode="backward"),
                    dict(count=12, label="12h", step="hour", stepmode="backward"),
                    dict(count=1, label="1d", step="day", stepmode="backward"),
                    dict(step="all", label="All")
                ]
            ),
            rangeslider=dict(visible=False)
        ),
        yaxis=dict(
            title=f"Bits per second ({unit})"
        ),
        template="plotly_white"
    )

    return fig


# ======================================================================
# Streamlit UI
# ======================================================================

st.title("Traffic Consumption Grapher")
st.write("Upload a CSV file to generate an interactive Ingress/Egress traffic graph.")

uploaded_file = st.file_uploader("Select CSV file", type=["csv"])

if uploaded_file is not None:
    try:
        df, unit = process_csv(uploaded_file)
        main_title, subtitle = build_titles(df)
        fig = build_figure(df, unit, main_title, subtitle)

        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Debug info"):
            st.write(f"Total rows after processing: {len(df)}")
            st.write(f"Egress rows: {len(df[df['Flow'] == 'Egress'])}")
            st.write(f"Ingress rows: {len(df[df['Flow'] == 'Ingress'])}")
            st.write(f"Date range: {df['Period End Time'].min()} to {df['Period End Time'].max()}")
            st.write(f"Main title: {main_title}")
            st.write(f"Subtitle: {subtitle}")

    except Exception as e:
        st.error(f"Error processing the file: {e}")
else:
    st.info("Waiting for a CSV file to be uploaded.")