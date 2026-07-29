import pandas as pd
import plotly.graph_objects as go
from tkinter import Tk, filedialog

# ======================================================================
# Configuration constants
# ======================================================================

# Time interval (in seconds) used to convert octets to bits per second.
# 900 seconds = 15 minutes
INTERVAL_SEG = 900


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


# ======================================================================
# File selection using Tkinter
# ======================================================================

# Initialize Tkinter root (needed only for the file dialog)
root = Tk()
root.withdraw()              # Hide the main Tkinter window
root.attributes('-topmost', True)  # Ensure dialog appears in front

print("Please select the CSV file...")

# Open file selection dialog and capture the selected path
CSV_PATH = filedialog.askopenfilename(
    title="Select the CSV file",
    filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
)

# If the user cancels the dialog, exit the script safely
if not CSV_PATH:
    print("No files were selected. Exiting...")
    exit()

print(f"Selected file: {CSV_PATH}")


# ======================================================================
# Load and preprocess CSV data
# ======================================================================

# Read CSV into a pandas DataFrame
df = pd.read_csv(CSV_PATH, quotechar='"', encoding='latin-1')

# Convert the timestamp column into a datetime object
df["Period End Time"] = pd.to_datetime(
    df["Period End Time"],
    format="%m/%d/%Y, %I:%M:%S %p"
)

# Ensure octet columns are numeric; invalid values become NaN
df["OCTETS"] = pd.to_numeric(
    df["OCTETS"], errors="coerce"
)

# ======================================================================
# Bandwidth calculation
# ======================================================================

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

    # Skip rows with missing octet data
    if pd.isna(octets):
        return None

    # Convert octets to bits and divide by interval to get bps
    return (octets * 8) / INTERVAL_SEG


# Apply bandwidth calculation row by row
df["bps"] = df.apply(calculate_bps, axis=1)

# Remove rows where bps could not be calculated
df = df.dropna(subset=["bps"])


# ======================================================================
# Scale bandwidth values to human-readable units
# ======================================================================

# Determine the best unit based on the maximum bandwidth observed
max_bps = df["bps"].max()
_, unit = escalate_bits(max_bps)

# Conversion factors for each unit
factor = {
    "b/s": 1,
    "Kb/s": 1e3,
    "Mb/s": 1e6,
    "Gb/s": 1e9,
    "Tb/s": 1e12
}[unit]

# Scale bps values to the selected unit
df["scaled_bps"] = df["bps"] / factor


# ======================================================================
# Normalize flow direction names
# ======================================================================

# Map raw directions to more readable labels
df["Flow"] = df["Direction"].map({
    "Incoming": "Ingress",
    "Outgoing": "Egress"
})

# Sort by time to ensure correct line rendering
df = df.sort_values("Period End Time")


# ======================================================================
# Extract dynamic title / subtitle information from CSV data
# ======================================================================

# "Affected Paths" -> used to build the main title
# Multiple values can be combined in a single cell using either a "�" or "¦"
# separator. We only want the first piece of information before whichever
# separator appears first.
PATH_SEPARATORS = ["\ufffd", "\u00a6"]  # "�" replacement char, and "¦" broken bar

def extract_first_path(value):
    """Return only the portion of the string before the first separator found."""
    if pd.isna(value):
        return None
    text = str(value)
    # Find the earliest occurrence among all possible separators
    positions = [text.find(sep) for sep in PATH_SEPARATORS if sep in text]
    if positions:
        cut_index = min(positions)
        text = text[:cut_index]
    return text.strip()

affected_paths_raw = df["Affected Paths"].dropna().unique()
extracted_paths = [extract_first_path(v) for v in affected_paths_raw]
# Deduplicate while preserving order (avoids pandas' pd.unique array-only requirement)
affected_paths = list(dict.fromkeys(extracted_paths))

if len(affected_paths) == 1:
    main_title = f"{affected_paths[0]} Traffic Consumption Graph"
elif len(affected_paths) > 1:
    main_title = f"{', '.join(affected_paths)} Traffic Consumption Graph"
else:
    main_title = "Traffic Consumption Graph"

# "NE/System Name" -> used as the subtitle (location)
system_names = df["NE/System Name"].dropna().unique()

if len(system_names) == 1:
    subtitle = system_names[0]
elif len(system_names) > 1:
    subtitle = ", ".join(system_names)
else:
    subtitle = ""


# ======================================================================
# Plotly visualization
# ======================================================================

# Create an empty Plotly figure
fig = go.Figure()

# -----------------------------
# Egress traffic trace
# -----------------------------
df_egress = df[df["Flow"] == "Egress"]

fig.add_trace(go.Scatter(
    x=df_egress["Period End Time"],
    y=df_egress["scaled_bps"],
    mode="lines",
    name="Egress",
    customdata=df_egress["bps"],  # Original unscaled bps for hover
    hovertemplate=(
        "%{x}<br>"
        "%{y:.2f} " + unit +
        "<br>%{customdata:,.0f} b/s"
        "<extra></extra>"
    )
))

# -----------------------------
# Ingress traffic trace
# -----------------------------
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


# ======================================================================
# Layout configuration
# ======================================================================

fig.update_layout(
    title=dict(
        text=f"{main_title}<br><sup>{subtitle}</sup>",
        x=0.5,       # Center the title horizontally
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


# ======================================================================
# Debug information and display
# ======================================================================

print(f"\nTotal traces: {len(fig.data)}")
for i, trace in enumerate(fig.data):
    print(f"Trace {i}: {trace.name}, points: {len(trace.x)}")

print(f"\nMain title: {main_title}")
print(f"Subtitle: {subtitle}")

# Display the interactive plot
fig.show()
