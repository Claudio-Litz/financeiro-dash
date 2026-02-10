# 💰 Smart Finance Hub

An intelligent, full-stack personal finance management application that automates transaction tracking and provides real-time financial insights.

## 🚀 Overview

The **Smart Finance Hub** is designed to bridge the gap between messy bank notifications and organized financial planning. By leveraging a rule-based engine, the application automatically cleans, formats, and categorizes transaction data. It features a dynamic interface for real-time CRUD operations, ensuring your financial records are always accurate and up-to-date.

## ✨ Key Features

* **Automated Categorization Engine:** Uses a custom "Robot" logic that scans transaction descriptions for keywords to assign categories automatically.
* **Interactive Data Editor:** A spreadsheet-like interface that allows users to edit, delete, and update transactions with live synchronization to the database.
* **Real-time Analytics:** Visualizes financial health through dynamic KPIs (Incomes, Expenses, Balance) and interactive charts using Plotly.
* **Smart Data Cleaning:** Utilizes Regular Expressions (Regex) to extract monetary values and identify transaction types (Income vs. Expense) from raw notification strings.
* **Manual Entry & Management:** Dedicated forms for manual transaction logging and custom category creation.

## 🛠️ Tech Stack

* **Frontend Framework:** [Streamlit](https://streamlit.io/)
* **Backend as a Service (BaaS):** [Supabase](https://supabase.com/) (PostgreSQL)
* **Data Manipulation:** Pandas
* **Data Visualization:** Plotly Express
* **Pattern Matching:** Regex (Python `re` module)

## 📋 Database Structure

To run this project, your Supabase instance requires the following tables:
1.  **`transacoes`**: Stores individual financial records (ID, date, description, value, type, category, bank).
2.  **`categorias`**: Stores the list of user-defined spending categories.
3.  **`regras`**: Stores the keyword-to-category mapping for the automation engine.

## 🔧 Installation & Setup

1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/your-username/smart-finance-hub.git](https://github.com/your-username/smart-finance-hub.git)
    cd smart-finance-hub
    ```

2.  **Install Dependencies:**
    ```bash
    pip install streamlit pandas plotly supabase
    ```

3.  **Configure Secrets:**
    Create a `.streamlit/secrets.toml` file with your Supabase credentials:
    ```toml
    SUPABASE_URL = "your_supabase_project_url"
    SUPABASE_KEY = "your_supabase_anon_key"
    ```

4.  **Run the App:**
    ```bash
    streamlit run app.py
    ```
