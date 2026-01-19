import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client
import re
from datetime import datetime
import pytz

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Controle Financeiro", layout="wide")

# --- CONEXÃO COM SUPABASE ---
# Vamos pegar as chaves dos "Segredos" do Streamlit (configuraremos no proximo passo)
# Se der erro aqui agora, é normal, pois ainda não configuramos as chaves.
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except:
    st.warning("Configure as chaves no .streamlit/secrets.toml")
    st.stop()

# --- FUNÇÕES DE LIMPEZA (REGEX) ---
def extrair_valor_loja(texto, banco):
    # Padrão genérico para dinheiro BR: R$ 1.234,56 ou 1234,56
    padrao_valor = r'R\$\s?([\d\.]+,\d{2})' 
    
    valor = 0.0
    loja = "Desconhecido"
    
    # Tenta encontrar o valor
    match_valor = re.search(padrao_valor, texto)
    if match_valor:
        valor_str = match_valor.group(1).replace('.', '').replace(',', '.')
        valor = float(valor_str)
    
    # Tenta limpar o nome da loja (Lógica simples: pega o que sobra ou posições fixas)
    # Isso pode ser melhorado com IA depois. Por enquanto, limpamos termos comuns.
    texto_limpo = texto.lower()
    termos_banco = ["compra aprovada", "compra de", "no cartao", "final", "bradesco", "inter", "r$", match_valor.group(0).lower() if match_valor else ""]
    
    for termo in termos_banco:
        texto_limpo = texto_limpo.replace(termo, "")
    
    loja = texto_limpo.strip().title()
    if len(loja) < 2: loja = "Outros"
        
    return valor, loja

# --- INTERFACE: BARRA LATERAL (LANÇAR DINHEIRO) ---
with st.sidebar:
    st.header("💸 Lançar Manual (Dinheiro)")
    with st.form("form_dinheiro"):
        valor_manual = st.number_input("Valor (R$)", min_value=0.0, step=0.10)
        loja_manual = st.text_input("Onde gastou?")
        categoria_manual = st.selectbox("Categoria", ["Alimentação", "Transporte", "Lazer", "Contas", "Outros"])
        submit = st.form_submit_button("Salvar Gasto")
        
        if submit:
            dados = {
                "banco": "Dinheiro",
                "mensagem_notificacao": f"Gasto manual em {loja_manual}",
                "valor": valor_manual,
                "categoria": categoria_manual,
                "data_hora": datetime.now().isoformat()
            }
            supabase.table("transacoes").insert(dados).execute()
            st.success("Salvo!")
            st.rerun()

# --- CARREGAR DADOS ---
response = supabase.table("transacoes").select("*").order("data_hora", desc=True).execute()
df = pd.DataFrame(response.data)

if not df.empty:
    # Processamento dos dados
    # Se o valor for 0 (veio do MacroDroid), tentamos extrair do texto
    valores_reais = []
    lojas_reais = []
    
    for index, row in df.iterrows():
        if row['banco'] != "Dinheiro" and (row['valor'] == 0 or row['valor'] is None):
            v, l = extrair_valor_loja(row['mensagem_notificacao'], row['banco'])
            valores_reais.append(v)
            lojas_reais.append(l)
        else:
            valores_reais.append(row['valor'])
            lojas_reais.append(row['mensagem_notificacao']) # Ou uma coluna loja se criar
            
    df['valor_final'] = valores_reais
    df['loja_final'] = lojas_reais
    
    # Converter data
    df['data_hora'] = pd.to_datetime(df['data_hora'])

    # --- DASHBOARD ---
    st.title("💰 Controle Financeiro em Tempo Real")
    
    # Métricas
    total = df['valor_final'].sum()
    col1, col2 = st.columns(2)
    col1.metric("Total Gasto", f"R$ {total:,.2f}")
    col2.metric("Última Transação", f"{df['data_hora'].iloc[0].strftime('%d/%m %H:%M')}")
    
    # Gráfico
    fig = px.bar(df, x='loja_final', y='valor_final', color='banco', title="Gastos por Local")
    st.plotly_chart(fig, use_container_width=True)
    
    # Tabela Detalhada
    st.subheader("Histórico")
    st.dataframe(df[['data_hora', 'banco', 'loja_final', 'valor_final']])

else:
    st.info("Nenhuma transação encontrada ainda.")