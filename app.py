import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client, Client
import re
from datetime import datetime, timedelta
import pytz

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão Financeira Pro", layout="wide", page_icon="💰")

# --- 2. CONEXÃO COM SUPABASE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except:
    st.error("Erro de Conexão: Verifique o arquivo .streamlit/secrets.toml")
    st.stop()

# --- 3. FUNÇÕES DE LÓGICA (CÉREBRO) ---

def carregar_dados():
    """Busca TODOS os dados do banco"""
    response = supabase.table("transacoes").select("*").order("data_hora", desc=True).execute()
    return pd.DataFrame(response.data)

def processar_transacao(row):
    """Lê a mensagem suja e transforma em dados limpos"""
    texto = row['mensagem_notificacao']
    banco = row['banco']
    valor_bd = row['valor'] # Valor que veio do banco (se houver)
    
    # Se já tiver valor no banco (lançamento manual), usa ele.
    if valor_bd and valor_bd > 0:
        # Se for manual, tentamos descobrir o tipo pela mensagem que salvamos
        tipo = "Entrada" if "Recebido" in texto else "Saída"
        # O nome da loja/descrição vem do texto também
        descricao = texto.replace("Recebido R$", "").replace("Pago R$", "").split("referente a")[-1].strip()
        return valor_bd, descricao, tipo

    # --- LÓGICA PARA NOTIFICAÇÕES AUTOMÁTICAS ---
    
    # 1. Extrair Valor via Regex (R$ 1.200,50 ou 50,00)
    match_valor = re.search(r'R\$\s?([\d\.]+,\d{2})', texto)
    valor = 0.0
    if match_valor:
        valor_str = match_valor.group(1).replace('.', '').replace(',', '.')
        valor = float(valor_str)
    
    # 2. Definir Tipo (Entrada ou Saída)
    texto_lower = texto.lower()
    termos_entrada = ["recebido", "recebida", "crédito", "estorno", "devolvido", "pix recebido", "depósito", "transferência recebida"]
    tipo = "Saída" # Padrão
    
    for termo in termos_entrada:
        if termo in texto_lower:
            tipo = "Entrada"
            break
            
    # 3. Limpar Descrição (Nome da Loja/Pessoa)
    # Removemos termos comuns de banco para sobrar só o nome
    termos_lixo = [
        "compra aprovada", "compra de", "compra no cartão", "final", "bradesco", "inter", "nubank", 
        "r$", "pix enviado", "pix recebido", "transferência realizada", "transferência recebida",
        match_valor.group(0).lower() if match_valor else ""
    ]
    
    desc_limpa = texto_lower
    for lixo in termos_lixo:
        desc_limpa = desc_limpa.replace(lixo, "")
    
    descricao = desc_limpa.strip().title()
    if len(descricao) < 2: descricao = "Outros / Não Identificado"
    
    return valor, descricao, tipo

# --- 4. INTERFACE LATERAL (FILTROS E INPUT) ---
with st.sidebar:
    st.title("🎛️ Controle")
    
    # --- FILTRO DE DATA ---
    st.markdown("### 📅 Período")
    mes_atual = datetime.now().month
    ano_atual = datetime.now().year
    
    # Seletores de Mês e Ano
    col_mes, col_ano = st.columns(2)
    mes_selecionado = col_mes.selectbox("Mês", range(1, 13), index=mes_atual-1)
    ano_selecionado = col_ano.number_input("Ano", min_value=2024, max_value=2030, value=ano_atual)
    
    st.divider()
    
    # --- INPUT MANUAL ---
    st.markdown("### 📝 Lançamento Manual")
    with st.form("form_manual"):
        tipo_input = st.radio("Tipo", ["Saída 🔴", "Entrada 🟢"], horizontal=True)
        valor_input = st.number_input("Valor (R$)", min_value=0.0, step=1.00, format="%.2f")
        desc_input = st.text_input("Descrição (O que é?)")
        cat_input = st.selectbox("Categoria", ["Alimentação", "Transporte", "Casa", "Lazer", "Serviços", "Outros"])
        
        btn_salvar = st.form_submit_button("💾 Salvar Lançamento", use_container_width=True)
        
        if btn_salvar and valor_input > 0:
            # Formata mensagem fake para manter padrão
            prefixo = "Recebido" if "Entrada" in tipo_input else "Pago"
            msg_fake = f"{prefixo} R$ {valor_input} referente a {desc_input}"
            
            dados = {
                "banco": "Carteira/Manual",
                "mensagem_notificacao": msg_fake,
                "valor": valor_input,
                "categoria": cat_input,
                "data_hora": datetime.now().isoformat()
            }
            try:
                supabase.table("transacoes").insert(dados).execute()
                st.toast("Salvo com sucesso!", icon="✅")
                st.rerun() # Recarrega a página
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

# --- 5. PROCESSAMENTO DE DADOS (PANDAS) ---
df_raw = carregar_dados()

if not df_raw.empty:
    # Converter data para datetime
    df_raw['data_hora'] = pd.to_datetime(df_raw['data_hora'])
    
    # Aplicar Filtro de Data (Mês e Ano selecionados)
    df_filtrado = df_raw[
        (df_raw['data_hora'].dt.month == mes_selecionado) & 
        (df_raw['data_hora'].dt.year == ano_selecionado)
    ].copy()
    
    if not df_filtrado.empty:
        # Processar linha a linha para limpar dados
        dados_processados = []
        for idx, row in df_filtrado.iterrows():
            v, d, t = processar_transacao(row)
            dados_processados.append({
                "Data": row['data_hora'],
                "Descrição": d,
                "Valor": v,
                "Tipo": t,
                "Banco": row['banco']
            })
        
        df_final = pd.DataFrame(dados_processados)
        
        # --- 6. O DASHBOARD (GRÁFICOS) ---
        
        st.header(f"Resumo Financeiro - {mes_selecionado}/{ano_selecionado}")
        
        # KPIs (Números Grandes)
        total_entradas = df_final[df_final['Tipo'] == 'Entrada']['Valor'].sum()
        total_saidas = df_final[df_final['Tipo'] == 'Saída']['Valor'].sum()
        saldo = total_entradas - total_saidas
        
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("🟢 Total Recebido", f"R$ {total_entradas:,.2f}")
        kpi2.metric("🔴 Total Gasto", f"R$ {total_saidas:,.2f}")
        kpi3.metric("💰 Saldo do Mês", f"R$ {saldo:,.2f}", delta_color="normal")
        
        st.markdown("---")
        
        # ÁREA DE GRÁFICOS
        g1, g2 = st.columns([1, 1])
        
        with g1:
            st.subheader("Onde estou gastando? (Saídas)")
            df_saidas = df_final[df_final['Tipo'] == 'Saída']
            if not df_saidas.empty:
                # Agrupar por descrição para somar gastos repetidos no mesmo lugar
                df_saidas_agrupado = df_saidas.groupby("Descrição")["Valor"].sum().reset_index()
                fig_saida = px.bar(
                    df_saidas_agrupado, 
                    x='Valor', 
                    y='Descrição', 
                    orientation='h',
                    color='Valor',
                    color_continuous_scale='Reds'
                )
                st.plotly_chart(fig_saida, use_container_width=True)
            else:
                st.info("Nenhuma saída neste mês.")
                
        with g2:
            st.subheader("Fontes de Renda (Entradas)")
            df_entradas = df_final[df_final['Tipo'] == 'Entrada']
            if not df_entradas.empty:
                fig_entrada = px.pie(
                    df_entradas, 
                    values='Valor', 
                    names='Descrição', 
                    hole=0.4,
                    color_discrete_sequence=px.colors.sequential.Greens_r
                )
                st.plotly_chart(fig_entrada, use_container_width=True)
            else:
                st.info("Nenhuma entrada neste mês.")

        # HISTÓRICO COMPLETO
        st.markdown("### 📜 Extrato Detalhado")
        
        # Ordenar e formatar para exibição bonita
        df_display = df_final.sort_values(by="Data", ascending=False)
        
        # Colorir tabela (truque visual do Pandas)
        def color_negative_red(val):
            color = 'red' if val == "Saída" else 'green'
            return f'color: {color}'

        st.dataframe(
            df_display.style.format({"Valor": "R$ {:.2f}"}),
            use_container_width=True,
            height=400
        )

    else:
        st.warning(f"Não há dados registrados para o mês {mes_selecionado}/{ano_selecionado}.")
        st.info("Tente mudar o mês no menu lateral ou faça um lançamento manual.")

else:
    st.info("Seu banco de dados está vazio. Aguardando a primeira notificação chegar...")