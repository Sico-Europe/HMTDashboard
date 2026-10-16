import streamlit as st
from streamlit_autorefresh import st_autorefresh
#from functions import data_handling, now, predict_job_time, format_duration, compute_job_list
from functions import data_handling, now
from visualisations import half_donut_gauge, half_hour, per_part, time_pie, pie_chart, bar, scatter
#from maintenance_functions import maintenance_data, save_changes
import pandas as pd

st.set_page_config(layout="wide")
st_autorefresh(interval=300000) #Refreshes every 5 minutes

st.title("HMT Bender Hub")

activity, time, maintenance = st.tabs(["Activity", "Time predictor", "Maintenance"],on_change="rerun")

if activity.open:
    with activity:
        result = data_handling()
        if result is None or result[0] is None:
            st.stop()
        today, weekly, part_breakdown, edits = result

        st.title("Activity Dashboard")
        with st.expander("Today's activity"):
            if len(today):
                with st.container():
                    #Graph showing number of programs run today, and the target of 90
                    st.subheader("Parts bent - Target: TBD",text_alignment="center")
                    programs_run = len(today)
                    st.plotly_chart(half_donut_gauge(programs_run, target=500),key="parts_today")
                    #Activity per half hour
                    st.subheader("Number Throughout Day")
                    st.plotly_chart(half_hour(today),key="half_hour_today")
                    #Bar graph of products made today
                    st.subheader("Types of parts bent")
                    st.plotly_chart(per_part(today), key="spread_today")
                    #Number and time of edits
                    st.subheader("Program tweaks")
                    st.info("Time spent editing the program when parts deviate due to differences in metal batches")
                    col1, col2= st.columns(2)
                    edits_today = edits.loc[edits["Finish"].dt.normalize() == now().normalize()]
                    edits_count_today = len(edits_today)
                    edits_time_today = edits_today["Total_time"].sum()
                    col1.metric("Number of edits", edits_count_today,)
                    col2.metric("Time spent on edits (minutes)", round(edits_time_today)/60)
                    #Number and time of changeovers
                    st.subheader("Changeovers")
                    st.info("Tracking of time taken changing toolings between different tubes will be added in the future")
            else:
                st.info("No data available for today.")
        with st.expander("This week"):
            current = now()
            week_start = (current - pd.Timedelta(days=current.weekday())).normalize()
            this_week = part_breakdown.loc[part_breakdown["Week"] == week_start]
            week = weekly.loc[week_start]
            if this_week.empty:
                st.info("No data available for this week.")
            else:
            #Availability and performance gauges
                col1, col2= st.columns(2)
                with col1:
                    st.subheader("Availability",text_alignment="center")
                    availability = week["Availability"]
                    st.plotly_chart(half_donut_gauge(round(availability*100), target=100,color="#2c41a0"), key="availability_week")
                    if availability < 0.6:
                        avail_message = "Poor: Machine is being underutilised, sitting idle a lot of the time."
                    elif availability < 0.75:
                        avail_message = "OK: Machine is sometimes sitting idle."
                    else:
                        avail_message = "Great! Machine is working for most of the shift."
                    st.markdown(f"<div style='text-align: center;'>{avail_message}</div>",unsafe_allow_html=True)
                with col2:
                    st.subheader("Performance",text_alignment="center")
                    performance = week["Performance"]
                    st.plotly_chart(half_donut_gauge(round(performance*100), target=100,color="#2c41a0"), key="performance_week")
                    if performance < 0.6:
                        perf_message = "Poor: Cycle times are much longer than usual."
                    elif performance < 0.8:
                        perf_message = "Good: Cycle times are as expected."
                    else:
                        perf_message = "Great! Machine is running at (or close to) optimal speed."
                    st.markdown(f"<div style='text-align: center;'>{perf_message}</div>",unsafe_allow_html=True)

                col3,col4= st.columns(2)
                with col3:
                    #Pie chart of time breakdown
                    st.subheader("Time breakdown (hrs)",text_alignment="center")
                    st.plotly_chart(time_pie(week), key="time_breakdown_week")
                with col4:
                    #Pie chart of parts machined
                    st.subheader("Parts breakdown",text_alignment="center")
                    st.plotly_chart(pie_chart(this_week["Program"], this_week["Count"]), key="spread_week")


        with st.expander("Historical activity"):
            st.subheader("Parts per week")
            weekly_count = part_breakdown.groupby("Week", as_index=False).agg(Total_Parts=("Count", "sum"))
            st.plotly_chart(bar(weekly_count["Week"], "Week",weekly_count["Total_Parts"],"Number of parts", color="#852ca0"), key="parts_per_week")

            st.subheader("Parts breakdown",text_alignment="center")
            st.plotly_chart(pie_chart(part_breakdown["Program"], part_breakdown["Count"]), key="parts_breakdown")
            st.subheader("Efficiency over time")
            st.plotly_chart(scatter(weekly.reset_index()), key="efficiency_trend")
"""
if time.open:
    result = data_handling()
    if result is None or result[0] is None:
        st.stop()
    _, _, _, _, summary = result

    st.title("Time calculator")

    st.info("Add each product and total quantity needed to estimate total CNC time for the job list.")

    programs = sorted(summary["Program"].tolist())

    if "job_list" not in st.session_state:
        st.session_state.job_list = pd.DataFrame(
            columns=["Program", "Number Required", "Estimated Batches", "Changeover Time", "Routing Time", "Total Time"]
        )
    if "job_list_version" not in st.session_state:
        st.session_state.job_list_version = 0

    editor_key = f"job_list_editor_{st.session_state.job_list_version}"

    edited = st.data_editor(
        st.session_state.job_list,
        num_rows="dynamic",
        column_config={
            "Program": st.column_config.SelectboxColumn("Program", options=programs, required=True),
            "Number Required": st.column_config.NumberColumn("Number Required", min_value=1, step=1, required=True),
            "Estimated Batches": st.column_config.NumberColumn("Estimated Batches", disabled=True), ##Make Estimated batches editable, adjust changeover time and total time accordingly
            "Changeover Time": st.column_config.TextColumn("Changeover Time", disabled=True),
            "Routing Time": st.column_config.TextColumn("Routing Time", disabled=True),
            "Total Time": st.column_config.TextColumn("Total Time", disabled=True),
        },
        key=editor_key,
    )

    recomputed, grand_total_seconds = compute_job_list(edited[["Program", "Number Required"]], summary)

    if not recomputed.equals(edited.reset_index(drop=True)):
        # Inputs changed since last computed - refresh the disabled columns and re-render
        st.session_state.job_list = recomputed
        st.session_state.job_list_version += 1
        st.rerun()
    else:
        st.session_state.job_list = recomputed

    if grand_total_seconds > 0:
        st.metric("Grand total estimated time", format_duration(grand_total_seconds))

    st.subheader("All programs")
    st.markdown("Average run time for single part based on historical data")
    st.dataframe(
        summary.rename(columns={
            "Avg_Cycle_Time": "Avg Cycle Time (s)",
            "Avg_Changeover_Time": "Avg Changeover (s)",
            "Run_Count": "Parts Recorded",
        }),
        hide_index=True,
    )

if maintenance.open:
    st.title("Maintenance Dashboard")
    
    st.info("When a task is performed, update the 'Last done' date then click 'Save changes'  \nIf a task needs doing before its due date, tick 'Needs doing' then click 'Save changes'")

    if "maintenance_loaded" not in st.session_state:
        due_now, due_later, past = maintenance_data()

        st.session_state.maintenance_due = due_now
        st.session_state.maintenance_later = due_later
        st.session_state.maintenance_past = past
        st.session_state.maintenance_loaded = True

    due_now = st.session_state.maintenance_due
    due_later = st.session_state.maintenance_later
    past = st.session_state.maintenance_past

    editable_due = pd.DataFrame()
    editable_later = pd.DataFrame()
    editable_past = pd.DataFrame()

    st.subheader("Tasks Due")
    if due_now.empty:
        st.success("No tasks due.")
    else:
        editable_due = st.data_editor(
            due_now,
            num_rows="dynamic",
            column_order = ["Task", "Last done", "Next due", "Or When", "Needs doing", "Action"],
            column_config={
                "Last done": st.column_config.DateColumn(
                    "Last done",
                    format="YYYY-MM-DD",
                ),
                "Next due": st.column_config.DateColumn(
                    "Next due",
                    format="YYYY-MM-DD",
                    disabled=True,
                ),
            },
            key="maintenance_due_table",
        )

    st.subheader("Upcoming Tasks")
    if due_later.empty:
        st.info("No upcoming tasks.")
    else:
        editable_later = st.data_editor(
            due_later,
            num_rows="dynamic",
            column_order = ["Task", "Last done", "Next due", "Or When", "Needs doing", "Action"],
            column_config={
                "Last done": st.column_config.DateColumn(
                    "Last done",
                    format="YYYY-MM-DD",
                ),
                "Next due": st.column_config.DateColumn(
                    "Next due",
                    format="YYYY-MM-DD",
                    disabled=True,
                ),
            },
            key="maintenance_upcoming_table",
        )

    st.subheader("Past Tasks")
    if past.empty:
        st.info("No past tasks.")
    else:
        editable_past = st.data_editor(
            past,
            num_rows="dynamic",
            column_order = ["Task", "Last done", "Next due", "Or When", "Needs doing", "Action"],
            column_config={
                "Last done": st.column_config.DateColumn(
                    "Last done",
                    format="YYYY-MM-DD",
                    required=True,
                ),
                "Next due": st.column_config.DateColumn(
                    "Next due",
                    format="YYYY-MM-DD",
                    disabled=True,
                ),
                
            },
            key="maintenance_past_table",
        )


    if st.button("Save changes", type="primary"):
        save_changes(editable_due, editable_later, editable_past)
        # Clear the cached maintenance tables
        st.session_state.pop("maintenance_loaded", None)
        st.session_state.pop("maintenance_due", None)
        st.session_state.pop("maintenance_later", None)
        st.session_state.pop("maintenance_past", None)
        st.rerun()

        """

        


    

        

        