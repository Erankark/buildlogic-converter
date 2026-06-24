import streamlit as st
import pandas as pd
import numpy as np
import io
import os
import plotly.express as px

# Set up the web page
st.set_page_config(page_title="Harwyn Timesheet Hub", page_icon="🏗️", layout="wide")

st.title("🏗️ Harwyn Timesheet Hub")

# --- AUTOMATIC REFERENCE DATA LOADING (Global) ---
ref_file_path = 'reference_data.xlsx'

if not os.path.exists(ref_file_path):
    st.error("⚠️ Master Data missing! Please upload 'reference_data.xlsx' to your GitHub repository.")
    st.stop() 

try:
    ref = pd.read_excel(ref_file_path, sheet_name='Ref')
    employee_ref = ref.dropna(subset=['Accounting System Code'])
    emp_code_dict = dict(zip(employee_ref['Accounting System Code'], employee_ref['Unnamed: 1']))
    emp_rate_dict = dict(zip(employee_ref['Accounting System Code'], employee_ref['Unnamed: 2']))
    emp_tax_dict = dict(zip(employee_ref['Accounting System Code'], employee_ref['Unnamed: 4']))

    activity_ref = ref.dropna(subset=['Reference Code Column'])
    act_trade_dict = dict(zip(activity_ref['Reference Code Column'].astype(str).str.zfill(5), activity_ref['Unnamed: 7']))
    act_cost_dict = dict(zip(activity_ref['Reference Code Column'].astype(str).str.zfill(5), activity_ref['Unnamed: 8']))
except Exception as e:
    st.error(f"⚠️ Error reading the Reference Data: {e}")
    st.stop()

# --- CREATE TABS ---
tab1, tab2 = st.tabs(["📤 Buildlogic Export", "📊 Labour Dashboard"])

# ==========================================
# TAB 1: THE STRICT BUILDLOGIC EXPORTER
# ==========================================
with tab1:
    st.markdown("### Daily Buildlogic Converter")
    st.markdown("Upload your **daily** Dashpivot CSV here to format it for Buildlogic.")
    
    export_file = st.file_uploader("Upload Daily CSV", type=["csv"], key="export_uploader")
    
    if export_file:
        with st.spinner('Preparing Buildlogic export...'):
            try:
                dp = pd.read_csv(export_file)
                # Drop rows that are completely empty
                dp = dp.dropna(how='all')
                bl = pd.DataFrame(index=dp.index)

                # Duplicate Form Logic
                counts = dp.groupby('Form Number').cumcount() + 1
                bl['Form Number'] = dp['Form Number'].astype(str)
                bl.loc[dp.duplicated('Form Number', keep=False), 'Form Number'] = bl['Form Number'] + '.' + counts.astype(str)

                bl['Companyname'] = dp['Created by']
                
                # Date Formatting
                dp['Date'] = pd.to_datetime(dp['Date'], errors='coerce')
                bl['TimeCostDate'] = dp['Date'].dt.strftime('%Y-%m-%d')
                
                # Lunch Break Deduction
                dp['Hours - Ordinary Hours'] = pd.to_numeric(dp['Hours - Ordinary Hours'], errors='coerce').fillna(0)
                max_hour_idx = dp.groupby(['Created by', 'Date'])['Hours - Ordinary Hours'].idxmax().dropna()
                hours_at_idx = dp.loc[max_hour_idx, 'Hours - Ordinary Hours']
                valid_idx = hours_at_idx[hours_at_idx >= 0.5].index
                dp.loc[valid_idx, 'Hours - Ordinary Hours'] -= 0.5
                bl['Hours'] = dp['Hours - Ordinary Hours']

                # Job Number Extraction
                bl['JobNumber'] = dp['Hours - Project'].astype(str).str.extract(r'HWYN(\d{4})', expand=False)
                
                # --- BULLETPROOF EXTRACTION LOGIC ---
                def parse_activity(val):
                    val = str(val)
                    if ' - ' in val:
                        code, desc = val.split(' - ', 1)
                        return code.strip(), desc.strip()
                    return '', val.strip()

                parsed_activities = dp['Hours - Activity'].apply(parse_activity)
                activity_codes = parsed_activities.apply(lambda x: x[0])
                
                bl['Description'] = parsed_activities.apply(lambda x: x[1])
                bl['ReferenceCode'] = pd.to_numeric(activity_codes, errors='coerce')

                # Lookups
                bl['REVIEW_NOTES'] = ""
                bl['AccountingSystemCode'] = bl['Companyname'].map(emp_code_dict).fillna('MISSING')
                base_rates = pd.to_numeric(bl['Companyname'].map(emp_rate_dict), errors='coerce')
                bl['TaxCode'] = bl['Companyname'].map(emp_tax_dict).fillna('MISSING')
                
                bl['Trade'] = activity_codes.str.zfill(5).map(act_trade_dict)
                bl['CostCode'] = activity_codes.str.zfill(5).map(act_cost_dict)

                # Rule 1: Factory Override
                is_factory = dp['Hours - Project'].astype(str).str.contains(r'HWYN000[01]', case=False, na=False)
                bl.loc[is_factory, 'JobNumber'] = '0001'
                bl.loc[is_factory, 'CostCode'] = 'LA'

                # Rule 3: 4-Digit Text Enforcer
                def format_job(val):
                    val = str(val).split('.')[0] 
                    if val.lower() == 'nan' or val == 'None' or val == '':
                        return ''
                    return val.zfill(4) 
                bl['JobNumber'] = bl['JobNumber'].apply(format_job)

                # Overtime
                is_weekend = dp['Date'].dt.dayofweek >= 5
                bl['Rate'] = np.where(is_weekend, base_rates * 1.5, base_rates)
                
                # Flagging
                bl.loc[is_weekend, 'REVIEW_NOTES'] += "[OVERTIME] "
                bl.loc[bl['AccountingSystemCode'] == 'MISSING', 'REVIEW_NOTES'] += "[MISSING EMPLOYEE] "
                bl.loc[bl['ReferenceCode'].isna(), 'REVIEW_NOTES'] += "[MISSING ACTIVITY CODE] "

                # Rule 2: Absent Filter
                is_absent = bl['Description'].astype(str).str.contains('absent', case=False, na=False)
                bl.loc[is_absent, 'REVIEW_NOTES'] += "[ABSENT] "

                bl['total'] = bl['Hours'] * bl['Rate']

                cols = ['Form Number', 'AccountingSystemCode', 'Companyname', 'TimeCostDate', 
                        'JobNumber', 'Trade', 'CostCode', 'ReferenceCode', 'Description', 
                        'Hours', 'Rate', 'TaxCode', 'total', 'REVIEW_NOTES']
                bl = bl[cols]

                # Sorting Absent rows to bottom
                bl['is_absent_sort'] = is_absent
                bl = bl.sort_values(by='is_absent_sort', kind='mergesort').drop(columns=['is_absent_sort'])

                # Export File
                csv_buffer = io.StringIO()
                bl.to_csv(csv_buffer, index=False)
                csv_data = csv_buffer.getvalue()

                st.success("✅ Conversion successful! Ready for Buildlogic.")
                st.download_button("⬇️ Download Buildlogic CSV", data=csv_data, file_name="Buildlogic_Import.csv", mime="text/csv")
                st.dataframe(bl.head(10))

            except Exception as e:
                st.error(f"Export Tool Error: {e}")

# ==========================================
# TAB 2: THE LABOUR DASHBOARD
# ==========================================
with tab2:
    st.markdown("### Historical Analytics Dashboard")
    st.markdown("Upload bulk, monthly, or yearly Dashpivot CSVs here to analyze labour trends.")
    
    dash_file = st.file_uploader("Upload Analytics CSV", type=["csv"], key="dash_uploader")
    
    if dash_file:
        try:
            dash = pd.read_csv(dash_file)
            
            # --- DATA CLEANING (Fixes Date Filter crashes) ---
            dash = dash.dropna(how='all') 
            dash = dash.dropna(subset=['Date']) 
            dash['Date'] = pd.to_datetime(dash['Date'], errors='coerce').dt.date
            dash = dash.dropna(subset=['Date']) 
            
            dash['Hours - Ordinary Hours'] = pd.to_numeric(dash['Hours - Ordinary Hours'], errors='coerce').fillna(0)
            
            # Apply lunch deduction
            max_hour_idx = dash.groupby(['Created by', 'Date'])['Hours - Ordinary Hours'].idxmax().dropna()
            valid_idx = dash.loc[max_hour_idx, 'Hours - Ordinary Hours'][dash.loc[max_hour_idx, 'Hours - Ordinary Hours'] >= 0.5].index
            dash.loc[valid_idx, 'Hours - Ordinary Hours'] -= 0.5

            # Calculate Strict 7am - 3pm Overtime
            def calculate_standard_hours(row):
                try:
                    s_h, s_m = map(int, str(row['Hours - Start Time']).split(':'))
                    e_h, e_m = map(int, str(row['Hours - End Time']).split(':'))
                    start_m = s_h * 60 + s_m
                    end_m = e_h * 60 + e_m
                    
                    std_start = 7 * 60
                    std_end = 15 * 60
                    
                    overlap_start = max(start_m, std_start)
                    overlap_end = min(end_m, std_end)
                    std_mins = max(0, overlap_end - overlap_start)
                    
                    std_hrs = std_mins / 60
                    return min(std_hrs, row['Hours - Ordinary Hours'])
                except:
                    return row['Hours - Ordinary Hours'] 

            dash['Standard Hours'] = dash.apply(calculate_standard_hours, axis=1)
            dash['Overtime Hours'] = dash['Hours - Ordinary Hours'] - dash['Standard Hours']
            dash['Overtime Hours'] = dash['Overtime Hours'].clip(lower=0) 

            # --- THE GLOBAL DATE FILTER ---
            st.divider()
            min_date = dash['Date'].min()
            max_date = dash['Date'].max()
            
            date_selection = st.date_input(
                "📅 Filter by Date Range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date
            )
            
            if len(date_selection) == 2:
                start_date, end_date = date_selection
                dash = dash[(dash['Date'] >= start_date) & (dash['Date'] <= end_date)]
            else:
                st.warning("Please select both a start and an end date to view the dashboard.")
                st.stop()

            # --- GLOBAL COMMAND CENTER ---
            st.header("Global Overview")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Hours Logged", f"{dash['Hours - Ordinary Hours'].sum():.1f}")
            col2.metric("Total Standard Hours (7am-3pm)", f"{dash['Standard Hours'].sum():.1f}")
            col3.metric("Total Overtime Hours", f"{dash['Overtime Hours'].sum():.1f}")

            st.divider()

            # --- NAVIGATION ---
            view_mode = st.radio("Select View Level", ["🏢 Project Deep Dive", "👷 Employee Forensics"], horizontal=True)

            if view_mode == "🏢 Project Deep Dive":
                project_list = dash['Hours - Project'].dropna().unique().tolist()
                selected_project = st.selectbox("Select Project", project_list)
                
                proj_data = dash[dash['Hours - Project'] == selected_project]
                
                # Project Specific Metrics
                p_col1, p_col2, p_col3 = st.columns(3)
                p_col1.metric("Project Total Hours", f"{proj_data['Hours - Ordinary Hours'].sum():.1f}")
                p_col2.metric("Project Standard Hours", f"{proj_data['Standard Hours'].sum():.1f}")
                p_col3.metric("Project Overtime Hours", f"{proj_data['Overtime Hours'].sum():.1f}")
                
                st.divider()
                
                col_a, col_b = st.columns(2)
                with col_a:
                    st.subheader("Hours by Activity")
                    activity_hrs = proj_data.groupby('Hours - Activity')['Hours - Ordinary Hours'].sum().sort_values(ascending=False)
                    st.bar_chart(activity_hrs)
                    
                with col_b:
                    st.subheader("Staff Allocation Matrix")
                    matrix = proj_data.pivot_table(index='Hours - Activity', columns='Created by', values='Hours - Ordinary Hours', aggfunc='sum').fillna(0)
                    st.dataframe(matrix, use_container_width=True)

            elif view_mode == "👷 Employee Forensics":
                employee_list = dash['Created by'].dropna().unique().tolist()
                selected_emp = st.selectbox("Select Employee", employee_list)
                
                emp_data = dash[dash['Created by'] == selected_emp]
                
                e_col1, e_col2, e_col3 = st.columns(3)
                e_col1.metric("Total Hours", f"{emp_data['Hours - Ordinary Hours'].sum():.1f}")
                e_col2.metric("Standard Hours", f"{emp_data['Standard Hours'].sum():.1f}")
                e_col3.metric("Overtime Hours", f"{emp_data['Overtime Hours'].sum():.1f}")
                
                st.divider()
                
                chart_col1, chart_col2 = st.columns(2)
                
                with chart_col1:
                    st.subheader("Time Split by Project")
                    proj_split = emp_data.groupby('Hours - Project', as_index=False)['Hours - Ordinary Hours'].sum()
                    fig1 = px.pie(proj_split, values='Hours - Ordinary Hours', names='Hours - Project', hole=0.4)
                    st.plotly_chart(fig1, use_container_width=True)
                    
                with chart_col2:
                    st.subheader("Time Split by Activity")
                    act_split = emp_data.groupby('Hours - Activity', as_index=False)['Hours - Ordinary Hours'].sum()
                    fig2 = px.pie(act_split, values='Hours - Ordinary Hours', names='Hours - Activity', hole=0.4)
                    st.plotly_chart(fig2, use_container_width=True)

        except Exception as e:
            st.error(f"Dashboard Error: {e}")
