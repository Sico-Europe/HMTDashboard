import plotly.graph_objects as go
import pandas as pd
from zoneinfo import ZoneInfo
# visualisations.py
"""
from functions import (
    real_breaks, real_shift,
    warmup_time, cleandown_time, now, breaks, shift_start, shift_end, changeover_max
)
"""
from functions import now
def half_donut_gauge(value, target, color="#2ca02c"):
    fig = go.Figure(go.Indicator(mode="gauge",value=value,
        gauge={"shape": "angular",
            "axis": {"range": [0, max(target,value)],"visible": False},
            "bar": {"color": color,"thickness": 0.35},
            "bgcolor": "#e6e6e6","borderwidth": 0,},
        domain={"x": [0, 1],"y": [0, 1]}))

    fig.add_annotation(x=0.5,y=0.25,
        text=(f"<b>{value}</b> / {target}<br>"),
        showarrow=False,font=dict(size=26))

    fig.update_layout(height=220,margin=dict(t=20, b=0, l=20, r=20),)
    return fig

def half_hour(data):
    # Make sure Finish is datetime
    data = data.copy()
    data["Finish"] = pd.to_datetime(data["Finish"])

    current = now()
    shift_end_dt = pd.Timestamp("17:00")
    latest_finish = data["Finish"].max()
    if current < shift_end_dt:
        end = current
    else:
        end = max(shift_end_dt, latest_finish)
    end = end.ceil("30min")

    # Create complete range of half-hour intervals
    finish_range = pd.date_range(
        start=data["Finish"].min().floor("30min"),
        end=end,
        freq="30min")

    # Count completed runs in each half-hour
    finish_counts = (
        data
        .assign(FinishHalfHour=data["Finish"].dt.floor("30min"))
        .groupby("FinishHalfHour")
        .size()
        .reindex(finish_range, fill_value=0)
        .rename("Runs")
        .reset_index()
        .rename(columns={"index": "FinishHalfHour"}))

    # Create labels
    finish_counts["FinishLabel"] = (finish_counts["FinishHalfHour"].dt.strftime("%H:%M"))
    fig = bar(finish_counts["FinishHalfHour"],"Half hour",finish_counts["Runs"],"Programs completed",time_axis=True)
    return fig

def bar(x, x_label, y, y_label, color="#2ca02c", time_axis=False):
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=x,
        y=y,
        text=y,
        textposition="outside",
        marker_color=color,
        hovertemplate=(
            "<b>%{x}</b><br>"
            f"{y_label}: %{{y}}"
            "<extra></extra>"
        )
    ))

    xaxis = dict(
        title=x_label,
        categoryorder='total ascending',
    )

    if time_axis:
        xaxis.update(
            tickformat="%H:%M",
        )

    fig.update_layout(
        xaxis=xaxis,
        yaxis=dict(
            title=y_label,
            rangemode="tozero",
        ),
        height=400,
        margin=dict(t=60, b=50, l=50, r=20),
        showlegend=False,
    )

    return fig

def per_part(data, color="#2ca02c"):
    program_counts = (data                        .groupby("Program")
                        .size()
                        .sort_values(ascending=False))

    fig = go.Figure(go.Bar(
        x=program_counts.values,
        y=program_counts.index,
        orientation="h",
        marker_color=color,
        text=program_counts.values,
        textposition="outside",
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Parts machined: %{x}"
            "<extra></extra>"
        )
    )
)

    fig.update_layout(
        xaxis_title="Parts machined",
        yaxis=dict(
            title="Program",
            type="category",
        ),
        height=350,
        margin=dict(l=20, r=50, t=20, b=50),
        showlegend=False
    )
    return fig

def time_pie(week):
    labels = ["Scheduled Breaks", "Bending", "Loading/Unloading", "Editing", "Downtime"]
    values = [week["Breaks_Time"], week["Total_Bending_Time"], week["Total_Loading_Time"],
              week["Total_Editing_Time"], week["Total_Downtime"]]
    return pie_chart(labels, [round(v / 3600, 1) for v in values])

def pie_chart(labels, values):
    fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.2)])
    fig.update_layout(
        height=400,
        margin=dict(t=20, b=50, l=50, r=20),
        showlegend=True,
        legend=dict(
            font=dict(size=16),
            x=0.8,
            y=0.5,
            xanchor="left",
            yanchor="middle",
    ))
    return fig


def scatter(data):
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=data["Week"],
        y=data["Availability"] * 100,
        mode="lines+markers",
        name="Availability",
        line=dict(color="#5e0570", width=3),
        marker=dict(size=7),
    ))

    fig.add_trace(go.Scatter(
        x=data["Week"],
        y=data["Performance"] * 100,
        mode="lines+markers",
        name="Performance",
        line=dict(color="#852ca0", width=3),
        marker=dict(size=7),
    ))

    fig.update_layout(
        height=400,
        yaxis=dict(
            title="Percentage",
            range=[0, 100],
            ticksuffix="%",
        ),
        xaxis=dict(
            title="Week",
            tickformat="%d %b",
        ),
        hovermode="x unified",
        margin=dict(t=30, b=50, l=50, r=20),
    )
    return fig

    
