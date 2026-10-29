#from io import StringIO
import pandas as pd
import numpy as np
import streamlit as st
import dropbox
import re
#import datetime
from zoneinfo import ZoneInfo
#import math

start_date = pd.Timestamp("2026-10-01") #When we started using the machine - ignore previous data, machine was second hand

#Workday assumptions
work_days = 4   # Mon-Thu: weekday() 0..3
workday_offset = pd.offsets.CustomBusinessDay(weekmask="Mon Tue Wed Thu")
shift_start = "08:00"
shift_end = "17:00"
breaks = [("10:00", "10:15"), ("13:00", "13:30")]

file = "/HMTbender.txt"

def now():
    return pd.Timestamp.now(tz=ZoneInfo("Europe/London")).tz_localize(None)

@st.cache_data(ttl=300)
def data_handling():
    text = download_data(file) #text, legacy = 
    if not text:
        st.error("No data returned from Dropbox download.")
        return None, None, None, None
    df = load_log(text)
    runs = build_runs(df)
    today = runs_today(runs)
    part_breakdown = weekly_part_counts(runs)
    weekly = split_weekly(runs)
    edits = runs[runs["Event"] == "Edited part"]
    return today, weekly, part_breakdown, edits

def weekly_part_counts(df):
    df = df[df["Event"] == "Bent part"].copy()
    df["Week"] = df["Finish"].dt.to_period("W").dt.start_time
    #Currently returns week, program, count
    return df.groupby(["Week", "Program"], as_index=False).agg(Count=("Program", "size"))

def runs_today(runs): #Filter today only
    today = pd.Timestamp.today().normalize()
    today_runs = runs[(runs["Finish"].dt.normalize() == today) &(runs["Event"] == "Bent part")]
    return today_runs

def download_data(file):
    dbx = dropbox.Dropbox(
        oauth2_refresh_token=st.secrets["DROPBOX_REFRESH_TOKEN"],
        app_key=st.secrets["DROPBOX_APP_KEY"],
        app_secret=st.secrets["DROPBOX_APP_SECRET"],)
    metadata, response = dbx.files_download(file)

    return response.content.decode("utf-8")

#def summarise(file):
    #rows = []
    #for line in text.splitlines():
        #m = LINE_RE.match(line)
        #if m:
            #rows.append(m.groupdict())
    #df = pd.DataFrame(rows).drop(columns=["Type"])
    #df["DateTime"] = pd.to_datetime(df["DateTime"], format="%Y-%m-%d %H:%M:%S,%f")

    #return program, count
    #and week, part count, availability, performance
    #save to Dropbox as CSV

LINE_RE = re.compile(
    r"^(?P<DateTime>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+"
    r"\w+\s+"                       # level (INFO etc.), not captured
    r"(?P<Type>\S+)\s*:\s*"
    r"(?P<Event>.*)$")


def load_log(text):
    rows = []
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if m:
            rows.append(m.groupdict())
    df = pd.DataFrame(rows).drop(columns=["Type"])
    df["DateTime"] = pd.to_datetime(df["DateTime"], format="%Y-%m-%d %H:%M:%S,%f")
    df["DateTime"] += pd.Timedelta(hours=5) # bender is in US time
    df = df[df["DateTime"] >= start_date]
    return df.sort_values("DateTime", kind="stable").reset_index(drop=True)

def build_runs(df):
    program_start = re.compile(r"Auto Cycle started partnumber\s+(?P<partnumber>\S+)")
    program_end = re.compile(r"Auto Cycle Complete Cycle Time\s+(?P<cycle_time>[\d.]+)")
    edit_start_row = re.compile(r"Open Form Part Editor - Editing Part: (?P<partnumber>\S+)\s+Units: (?P<units>\S+)")
    edit_end = re.compile(r"Close Form Part Editor - Editing Part: (?P<partnumber>\S+)\s+Units: (?P<units>\S+)")

    runs = []
    active_start = {}
    active_partnumber = None
    edit_start = {}

    for DateTime, Event in df[["DateTime", "Event"]].itertuples(index=False):
        
        m_start = program_start.match(Event)
        m_end = program_end.match(Event)
        m_edit_start = edit_start_row.match(Event)
        m_edit_end = edit_end.match(Event)

        if m_start:
            active_start[m_start.group("partnumber")] = DateTime
            active_partnumber = m_start.group("partnumber")
        elif m_end:
            if active_partnumber != None:
                runs.append({
                    "Program": active_partnumber,
                    "Start": active_start[active_partnumber],
                    "Finish": DateTime,
                    "Event": "Bent part",
                    "Cycle_Time": float(m_end.group("cycle_time")),
                })
            active_partnumber = None
        elif m_edit_start:
            edit_start[m_edit_start.group("partnumber")] = DateTime
        elif m_edit_end:
            if m_edit_end.group("partnumber") in edit_start:
                runs.append({
                    "Program": m_edit_end.group("partnumber"),
                    "Start": edit_start[m_edit_end.group("partnumber")],
                    "Finish": DateTime,
                    "Event": "Edited part",
                    "Cycle_Time": None,
                })
                del edit_start[m_edit_end.group("partnumber")]

    runs = pd.DataFrame(runs)
    if runs.empty:
        return runs

    runs["Cycle_Time"] = pd.to_numeric(runs["Cycle_Time"])
    runs["Total_time"] = (runs["Finish"] - runs["Start"]).dt.total_seconds()
    runs["Extra_Time"] = runs["Total_time"] - runs["Cycle_Time"]                                             
    return runs

def real_breaks(day, current):
    total = 0
    for bstart, bend in breaks:  # Have the breaks happened yet?
        b0 = pd.Timestamp(f"{day:%Y-%m-%d} {bstart}")
        b1 = pd.Timestamp(f"{day:%Y-%m-%d} {bend}")
        end = min(b1, current)          # for past days this is the full break
        if end > b0:
            total += (end - b0).total_seconds()
    return total

def real_shift(day, current):
    if day.weekday() >= work_days:
        return 0.0
    s = pd.Timestamp(f"{day:%Y-%m-%d} {shift_start}")
    e = pd.Timestamp(f"{day:%Y-%m-%d} {shift_end}")
    return max(0.0, (min(e, current) - s).total_seconds())

def loading_prediction(runs):
    stats = prod(runs)
    runs["Downtime"] = np.nan
    runs["Loading"] = np.nan
    runs["Performance"] = np.nan 
    for idx, row in runs.iterrows():
        runs.at[idx, "Downtime"] = 0.0
        if row.Event == "Bent part":
            prod_stats = stats[stats["Program"] == row.Program]
            if not prod_stats.empty:
                mean = prod_stats["Mean_Time_Per_Part"].iloc[0]
                upper = prod_stats["Upper_Quartile"].iloc[0]
                lower = prod_stats["Lower_Quartile"].iloc[0]
                confidence = prod_stats["Confidence"].iloc[0]
                if confidence:
                    runs.at[idx, "Performance"] = lower / row.Total_time
                    if row.Total_time > upper:
                        runs.at[idx, "Downtime"] = max(0, row["Total_time"] - mean)
            runs.at[idx, "Loading"] = row["Total_time"] - row ["Cycle_Time"]- runs.at[idx, "Downtime"]
    return runs

def split_weekly(runs):
    #Add in stored summary data
    #Currently returns: Week, Days Recorded, Total Runs, Total Bending Time, Total Loading Time, Total Editing Time, Shift Time, Breaks Time, Total Downtime, Availability
    runs["Week"] = runs["Finish"].dt.to_period("W").dt.start_time
    loading = loading_prediction(runs)

    split = loading.groupby("Week").agg(
        Days_Recorded=("Finish", lambda x: x.dt.normalize().nunique()),   # was "nunique" (counts timestamps)
        Total_Runs=("Program", "count"),
        Total_Bending_Time=("Cycle_Time", "sum"),
        Total_Loading_Time=("Loading", "sum"),
        Performance=("Performance", "mean"),
    )
    edit_time = loading[loading["Event"] == "Edited part"].groupby("Week")["Total_time"].sum()
    split["Total_Editing_Time"] = edit_time
    split["Total_Editing_Time"] = split["Total_Editing_Time"].fillna(0)

    # shift and break time available so far in each week
    current = now()
    shifts, week_breaks = [], []
    for week in split.index:
        days = [week + pd.Timedelta(days=d) for d in range(work_days)]
        days = [d for d in days if d >= start_date]
        shifts.append(sum(real_shift(d, current) for d in days))
        week_breaks.append(sum(real_breaks(d, current) for d in days))
    split["Shift_Time"] = shifts
    split["Breaks_Time"] = week_breaks

    planned = (split["Shift_Time"] - split["Breaks_Time"]).where(lambda p: p > 0)
    busy = split["Total_Bending_Time"] + split["Total_Loading_Time"] + split["Total_Editing_Time"]
    split["Total_Downtime"] = (planned.fillna(0) - busy).clip(lower=0)
    split["Availability"] = (busy / planned).clip(upper=1)
    return split
      
def prod(runs): #calculate mean, lower and upper quartiles of run time for each product  
    if runs.empty:
        return runs

    prod_data = (
        runs[runs["Event"] == "Bent part"]
        .groupby("Program", as_index=False)
        .agg(
            Mean_Time_Per_Part=("Total_time", "mean"),
            Lower_Quartile=("Total_time", lambda x: x.quantile(0.25)),
            Upper_Quartile=("Total_time", lambda x: x.quantile(0.75)),
            Run_count =("Program", "count"),

        )
    )
    prod_data["Confidence"] = prod_data["Run_count"] > 200 
    return prod_data


"""
def upload_data(data, path):

    csv_data = data.to_csv(index=False).encode("utf-8")

    dbx = dropbox.Dropbox(
        oauth2_refresh_token=st.secrets["DROPBOX_REFRESH_TOKEN"],
        app_key=st.secrets["DROPBOX_APP_KEY"],
        app_secret=st.secrets["DROPBOX_APP_SECRET"],
    )

    dbx.files_upload(
        csv_data,
        path,
        mode=dropbox.files.WriteMode.overwrite,
    )



def productive_seconds_per_day():
    start_dt = datetime.datetime.strptime(shift_start, "%H:%M")
    end_dt = datetime.datetime.strptime(shift_end, "%H:%M")
    shift_seconds = (end_dt - start_dt).total_seconds()

    break_seconds = sum(
        (datetime.datetime.strptime(bend, "%H:%M") - datetime.datetime.strptime(bstart, "%H:%M")).total_seconds()
        for bstart, bend in breaks
    )
    return shift_seconds - break_seconds - (warmup_time * 60) - (cleandown_time * 60)


def predict_job_time(avg_cycle_time, avg_changeover_time, qty):
    routing_time = avg_cycle_time * qty
    available_per_day = productive_seconds_per_day() - avg_changeover_time

    if available_per_day <= 0:
        # changeover alone eats the whole day's productive time - degenerate case
        changeovers = max(1, math.ceil(routing_time / max(avg_changeover_time, 1)))
    else:
        changeovers = max(1, math.ceil(routing_time / available_per_day))

    total_time = routing_time + changeovers * avg_changeover_time
    return total_time, changeovers

def format_duration(seconds):

    minutes = seconds / 60
    hours = seconds / 3600

    shift_start_dt = datetime.datetime.strptime(shift_start, "%H:%M")
    shift_end_dt = datetime.datetime.strptime(shift_end, "%H:%M")
    shift_hours = productive_seconds_per_day() / 3600

    if minutes < 60:
        return f"{minutes:.0f} min"
    elif hours < shift_hours:
        return f"{hours:.1f} hours"
    else:
        shifts = hours / shift_hours
        return f"{hours:.1f} hours (~{shifts:.1f} shifts)"

def compute_job_list(input_df, summary):
    rows = []
    grand_total_seconds = 0

    for _, r in input_df.iterrows():
        program, qty = r.get("Program"), r.get("Number Required")

        if pd.isna(program) or pd.isna(qty) or program not in summary["Program"].values:
            rows.append({
                "Program": program, "Number Required": qty,
                "Estimated Batches": None, "Changeover Time": "",
                "Routing Time": "", "Total Time": "",
            })
            continue

        qty = int(qty)
        stat = summary[summary["Program"] == program].iloc[0]
        total_seconds, changeovers = predict_job_time(stat["Avg_Cycle_Time"], stat["Avg_Changeover_Time"], qty)
        routing_seconds = stat["Avg_Cycle_Time"] * qty
        changeover_seconds = total_seconds - routing_seconds
        grand_total_seconds += total_seconds

        rows.append({
            "Program": program, "Number Required": qty,
            "Estimated Batches": changeovers,
            "Changeover Time": format_duration(changeover_seconds),
            "Routing Time": format_duration(routing_seconds),
            "Total Time": format_duration(total_seconds),
        })

    columns = ["Program", "Number Required", "Estimated Batches", "Changeover Time", "Routing Time", "Total Time"]
    return pd.DataFrame(rows, columns=columns), grand_total_seconds

"""