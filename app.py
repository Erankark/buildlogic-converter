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
