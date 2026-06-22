import streamlit as st
import pandas as pd
import numpy as np
import io
import os

# Set up the web page
st.set_page_config(page_title="Dashpivot to Buildlogic", page_icon="🏗️", layout="centered")

st.title("🏗️ Dashpivot to Buildlogic")
st.markdown("Drop your **raw Dashpivot CSV** export below to instantly format it for Buildlogic.")

# --- AUTOMATIC REFERENCE DATA LOADING ---
ref_file_path = 'reference_data.xlsx'

# Check if the file exists in the GitHub repo
if not os.path.exists(ref_file_path):
    st.error("⚠️ Master Data missing! Please upload 'reference_data.xlsx' to your GitHub repository.")
    st.stop() # Stops the app from running further until the file is found

# Load dictionaries silently in the background
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


# --- UI: THE SINGLE DROP ZONE ---
dp_file = st.file_uploader("Upload Daily CSV", type=["csv"], label_visibility="hidden")

# --- PROCESSING LOGIC ---
if dp_file:
    with st.spinner('Converting data...'):
        try:
            # 1. Load the daily data
            dp = pd.read_csv(dp_file)

            # 2. Process the Data
            bl = pd.DataFrame(index=dp.index)

            # Duplicate Form Logic
            counts = dp.groupby('Form Number').cumcount() + 1
            bl['Form Number'] = dp['Form Number'].astype(str)
            bl.loc[dp.duplicated('Form Number', keep=False), 'Form Number'] = bl['Form Number'] + '.' + counts.astype(str)

            bl['Companyname'] = dp['Created by']
            
            # Format Date
            dp['Date'] = pd.to_datetime(dp['Date'])
            bl['TimeCostDate'] = dp['Date'].dt.strftime('%Y-%m-%d')
            
            # Lunch Break Deduction Logic
            dp['Hours - Ordinary Hours'] = pd.to_numeric(dp['Hours - Ordinary Hours'], errors='coerce').fillna(0)
            max_hour_idx = dp.groupby(['Created by', 'Date'])['Hours - Ordinary Hours'].idxmax().dropna()
            hours_at_idx = dp.loc[max_hour_idx, 'Hours - Ordinary Hours']
            valid_idx = hours_at_idx[hours_at_idx >= 0.5].index
            dp.loc[valid_idx, 'Hours - Ordinary Hours'] -= 0.5
            bl['Hours'] = dp['Hours - Ordinary Hours']

            # Extraction
            bl['JobNumber'] = dp['Hours - Project'].astype(str).str.extract(r'HWYN(\d{4})')
            activity_split = dp['Hours - Activity'].astype(str).str.split(' - ', n=1, expand=True)
            bl['ReferenceCode'] = pd.to_numeric(activity_split[0], errors='coerce')
            bl['Description'] = activity_split[1]

            # Lookups & Overtime
            bl['REVIEW_NOTES'] = ""
            bl['AccountingSystemCode'] = bl['Companyname'].map(emp_code_dict).fillna('MISSING')
            base_rates = pd.to_numeric(bl['Companyname'].map(emp_rate_dict), errors='coerce')
            bl['TaxCode'] = bl['Companyname'].map(emp_tax_dict).fillna('MISSING')
            bl['Trade'] = activity_split[0].str.zfill(5).map(act_trade_dict)
            bl['CostCode'] = activity_split[0].str.zfill(5).map(act_cost_dict)

            is_weekend = dp['Date'].dt.dayofweek >= 5
            bl['Rate'] = np.where(is_weekend, base_rates * 1.5, base_rates)
            
            bl.loc[is_weekend, 'REVIEW_NOTES'] += "[OVERTIME APPLIED] "
            bl.loc[bl['AccountingSystemCode'] == 'MISSING', 'REVIEW_NOTES'] += "[MISSING EMPLOYEE] "

            bl['total'] = bl['Hours'] * bl['Rate']

            # Output Formatting
            cols = ['Form Number', 'AccountingSystemCode', 'Companyname', 'TimeCostDate', 
                    'JobNumber', 'Trade', 'CostCode', 'ReferenceCode', 'Description', 
                    'Hours', 'Rate', 'TaxCode', 'total', 'REVIEW_NOTES']
            bl = bl[cols]

            # 3. Prepare file for download
            csv_buffer = io.StringIO()
            bl.to_csv(csv_buffer, index=False)
            csv_data = csv_buffer.getvalue()

            # --- UI Display ---
            st.success("✅ Conversion successful! Ready for Buildlogic.")
            
            st.write("### Data Preview")
            st.dataframe(bl.head(10))

            st.download_button(
                label="⬇️ Download Buildlogic CSV",
                data=csv_data,
                file_name="Buildlogic_Import_Ready.csv",
                mime="text/csv"
            )

        except Exception as e:
            st.error(f"An error occurred while processing the file: {e}")
