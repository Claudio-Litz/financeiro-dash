import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client
import re
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gestão Financeira Pro", layout="wide", page_icon="💰")

# --- CONEXÃO ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except:
    st.error("Erro de Conexão: Verifique os secrets.")
    st.stop()

# --- FUNÇÕES AUXILIARES ---

def carregar_categorias():
    """Busca a lista de categorias do banco de dados"""
    try:
        response = supabase.table("categorias").select("nome").execute()
        # Transforma em uma lista simples: ['Alimentação', 'Transporte', ...]
        lista = [item['nome'] for item in response.data]
        return sorted(lista)
    except:
        return ["Geral", "Alimentação", "Transporte"] # Fallback se der erro

def adicionar_categoria(nova_cat):
    """Salva uma nova categoria no banco"""
    try:
        supabase.table("categorias").insert({"nome": nova_cat}).execute()
        return True
    except:
        return False

def categorizar_automatico(descricao):
    """
    Tenta adivinhar a categoria baseada em palavras-chave.
    Você pode adicionar mais regras aqui com o tempo.
    """
    desc_lower = descricao.lower()
    
    regras = {
        "Transporte": ["uber", "99", "posto", "gasolina", "estacionamento"],
        "Alimentação": ["ifood", "restaurante", "mercado", "padaria", "zédelivery", "burger", "pizza"],
        "Lazer": ["netflix", "spotify", "cinema", "steam", "jogos"],
        "Saúde": ["farmácia", "drogaria", "médico", "exame"],
        "Moradia": ["luz", "agua", "internet", "aluguel", "condominio"]
    }
    
    for categoria, palavras in regras.items():
        for palavra in palavras:
            if palavra in desc_lower:
                return categoria
                
    return "Geral" # Se não achar nada

def processar_dados(df_raw):
    """Limpa e organiza os dados para exibição"""
    dados_processados = []
    
    for idx, row in df_raw.iterrows():
        texto = row['mensagem_notificacao']
        banco = row['banco']
        
        # 1. Determina Valor
        valor = row['valor']
        if valor == 0 or valor is None:
            # Tenta extrair do texto se vier zerado do MacroDroid
            match_valor = re.search(r'R\$\s?([\d\.]+,\d{2})', texto)
            if match_valor:
                v_str = match_valor.group(1).replace('.', '').replace(',', '.')
                valor = float(v_str)
            else:
                valor = 0.0

        # 2. Determina Tipo (Entrada/Saída) e Descrição
        texto_lower = texto.lower()
        tipo = "Saída"
        if any(x in texto_lower for x in ["recebido", "crédito", "estorno", "depósito"]):
            tipo = "Entrada"
        
        # Limpeza da descrição
        termos_lixo = ["compra aprovada", "compra de", "r$", "bradesco", "inter", "pix enviado", "transacao"]
        desc_limpa = texto_lower
        for t in termos_lixo:
            desc_limpa = desc_limpa.replace(t, "")
        descricao = desc_limpa.strip().title()
        if len(descricao) < 2: descricao = "Não Identificado"

        # 3. Determina Categoria
        # Se já tiver categoria salva no banco (input manual), usa ela.
        # Se não tiver (automático), tenta adivinhar.
        categoria_bd = row.get('categoria') 
        if categoria_bd and categoria_bd != "null": 
            categoria = categoria_bd
        else:
            categoria = categorizar_automatico(descricao)

        dados_processados.append({
            "Data": pd.to_datetime(row['data_hora']),
            "Descrição": descricao,
            "Valor": valor,
            "Tipo": tipo,
            "Categoria": categoria,
            "Banco": banco
        })
        
    return pd.DataFrame(dados_processados)

# --- BARRA LATERAL ---
with st.sidebar:
    st.title("🎛️ Painel de Controle")
    
    # 1. Seletor de Data
    mes_atual = datetime.now().month
    mes = st.selectbox("Mês", range(1, 13), index=mes_atual-1)
    ano = st.number_input("Ano", value=datetime.now().year)
    st.divider()
    
    # 2. Gestão de Categorias
    st.markdown("### 🏷️ Categorias")
    lista_categorias = carregar_categorias()
    
    with st.expander("Adicionar Nova Categoria"):
        nova_cat_nome = st.text_input("Nome da nova categoria")
        if st.button("Salvar Categoria"):
            if nova_cat_nome and nova_cat_nome not in lista_categorias:
                if adicionar_categoria(nova_cat_nome):
                    st.success("Adicionada!")
                    st.rerun()
                else:
                    st.error("Erro ao salvar")
            else:
                st.warning("Nome inválido ou já existe")

    st.divider()

    # 3. Lançamento Manual
    st.markdown("### 📝 Novo Gasto/Ganho")
    with st.form("manual"):
        f_tipo = st.radio("Tipo", ["Saída", "Entrada"], horizontal=True)
        f_valor = st.number_input("Valor", min_value=0.0, step=0.1)
        f_cat = st.selectbox("Categoria", lista_categorias)
        f_desc = st.text_input("Descrição (Opcional)")
        
        if st.form_submit_button("Lançar"):
            msg_fake = f"{'Recebido' if f_tipo == 'Entrada' else 'Gasto'} manual referente a {f_desc}"
            supabase.table("transacoes").insert({
                "banco": "Carteira",
                "mensagem_notificacao": msg_fake,
                "valor": f_valor,
                "categoria": f_cat,
                "data_hora": datetime.now().isoformat()
            }).execute()
            st.success("Lançado!")
            st.rerun()

# --- CORPO DO DASHBOARD ---
# Busca dados brutos
df_raw = pd.DataFrame(supabase.table("transacoes").select("*").order("data_hora", desc=True).execute().data)

if not df_raw.empty:
    # Processa (Limpa e Categoriza)
    df = processar_dados(df_raw)
    
    # Filtra por Data
    df = df[
        (df['Data'].dt.month == mes) & 
        (df['Data'].dt.year == ano)
    ]
    
    if not df.empty:
        # --- CÁLCULOS TOTAIS ---
        entradas = df[df['Tipo']=='Entrada']['Valor'].sum()
        saidas = df[df['Tipo']=='Saída']['Valor'].sum()
        saldo = entradas - saidas
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Entradas", f"R$ {entradas:,.2f}")
        c2.metric("Saídas (Gastos)", f"R$ {saidas:,.2f}", delta_color="inverse")
        c3.metric("Saldo", f"R$ {saldo:,.2f}")
        
        st.divider()
        
        # --- GRÁFICOS POR CATEGORIA ---
        g1, g2 = st.columns(2)
        
        with g1:
            st.subheader("Gastos por Categoria")
            df_saida = df[df['Tipo']=='Saída']
            if not df_saida.empty:
                # Agrupa por CATEGORIA (não mais por descrição)
                df_cat = df_saida.groupby("Categoria")["Valor"].sum().reset_index()
                fig = px.pie(df_cat, values='Valor', names='Categoria', hole=0.5)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sem gastos no período.")
                
        with g2:
            st.subheader("Ranking de Despesas")
            if not df_saida.empty:
                df_cat = df_saida.groupby("Categoria")["Valor"].sum().reset_index().sort_values("Valor")
                fig = px.bar(df_cat, x="Valor", y="Categoria", orientation='h')
                st.plotly_chart(fig, use_container_width=True)
        
        # --- TABELA FINAL ---
        st.subheader("Extrato Detalhado")
        st.dataframe(
            df[['Data', 'Categoria', 'Descrição', 'Valor', 'Tipo', 'Banco']].sort_values('Data', ascending=False),
            use_container_width=True
        )
        
    else:
        st.warning("Nada encontrado neste mês.")
else:
    st.info("Banco de dados vazio.")