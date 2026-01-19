import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client
import re
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gestão Financeira", layout="wide", page_icon="💰")

# --- CONEXÃO ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except:
    st.error("Erro de Conexão: Verifique os secrets.")
    st.stop()

# --- FUNÇÕES ---

def carregar_categorias():
    try:
        response = supabase.table("categorias").select("nome").execute()
        lista = [item['nome'] for item in response.data]
        return sorted(lista)
    except:
        return ["Geral", "Alimentação", "Transporte", "Lazer", "Contas"]

def carregar_regras():
    try:
        response = supabase.table("regras").select("*").execute()
        return pd.DataFrame(response.data)
    except:
        return pd.DataFrame()

def categorizar_automatico(descricao, df_regras):
    desc_lower = descricao.lower()
    if df_regras.empty:
        return "Geral"
    for index, row in df_regras.iterrows():
        if row['palavra_chave'].lower() in desc_lower:
            return row['categoria']
    return "Geral"

def processar_dados(df_raw, df_regras):
    dados_processados = []
    for idx, row in df_raw.iterrows():
        texto = row['mensagem_notificacao']
        valor = row['valor']
        
        # 1. Valor
        if valor == 0 or valor is None:
            match_valor = re.search(r'R\$\s?([\d\.]+,\d{2})', texto)
            valor = float(match_valor.group(1).replace('.', '').replace(',', '.')) if match_valor else 0.0

        # 2. Tipo
        tipo = "Entrada" if any(x in texto.lower() for x in ["recebido", "crédito", "estorno", "devolvido"]) else "Saída"
        
        # 3. Descrição Limpa (Pix e Banco)
        termos_lixo = [
            "você recebeu um pix de", "voce recebeu um pix de", "pix recebido de", 
            "da instituição", "compra aprovada", "compra de", "r$", 
            "bradesco", "inter", "pix enviado", "transacao", "no cartao", "final"
        ]
        desc_limpa = texto.lower()
        for t in termos_lixo:
            desc_limpa = desc_limpa.replace(t, "")
        
        descricao = desc_limpa.strip().title()
        if len(descricao) < 2: descricao = "Não Identificado"

        # 4. Categoria (Lógica: Robô > Banco > Geral)
        cat_banco = row.get('categoria')
        cat_robo = categorizar_automatico(descricao, df_regras)
        
        if cat_robo != "Geral":
            cat = cat_robo
        elif cat_banco and cat_banco != "null":
            cat = cat_banco
        else:
            cat = "Geral"

        dados_processados.append({
            "id": row['id'],
            "Data": pd.to_datetime(row['data_hora']),
            "Descrição": descricao,
            "Valor": valor,
            "Tipo": tipo,
            "Categoria": cat,
            "Banco": row['banco']
        })
    return pd.DataFrame(dados_processados)

# --- SIDEBAR (BARRA LATERAL) ---
with st.sidebar:
    st.title("🎛️ Controle")
    
    # 1. DATA
    mes = st.selectbox("Mês", range(1, 13), index=datetime.now().month-1)
    ano = st.number_input("Ano", value=datetime.now().year)
    
    st.divider()
    
    # 2. GESTÃO DE CATEGORIAS (AQUI ESTÁ ELA DE VOLTA!)
    st.markdown("### 🏷️ Categorias")
    lista_categorias = carregar_categorias()
    
    with st.expander("➕ Criar Nova Categoria"):
        nova_cat = st.text_input("Nome da nova categoria")
        if st.button("Salvar Categoria"):
            if nova_cat and nova_cat not in lista_categorias:
                supabase.table("categorias").insert({"nome": nova_cat}).execute()
                st.success(f"Categoria '{nova_cat}' criada!")
                st.rerun()
            elif nova_cat in lista_categorias:
                st.warning("Essa categoria já existe.")

    # 3. ENSINAR ROBÔ
    with st.expander("🧠 Ensinar o Robô (Regras)"):
        with st.form("nova_regra"):
            p_chave = st.text_input("Se conter a palavra:", placeholder="Ex: claudio").lower()
            cat_alvo = st.selectbox("Categorizar como:", lista_categorias)
            if st.form_submit_button("Salvar Regra"):
                if p_chave:
                    supabase.table("regras").insert({"palavra_chave": p_chave, "categoria": cat_alvo}).execute()
                    st.success("Aprendido!")
                    st.rerun()
        
        # Listar Regras
        df_regras_display = carregar_regras()
        if not df_regras_display.empty:
            st.caption("Regras Ativas:")
            st.dataframe(df_regras_display[['palavra_chave', 'categoria']], hide_index=True)

    st.divider()

    # 4. LANÇAMENTO MANUAL
    st.markdown("### 📝 Lançar Manual")
    with st.form("manual"):
        tipo = st.radio("Tipo", ["Saída", "Entrada"], horizontal=True)
        valor = st.number_input("Valor", min_value=0.0, step=0.1)
        cat = st.selectbox("Categoria", lista_categorias)
        desc = st.text_input("Descrição")
        if st.form_submit_button("Lançar"):
            msg = f"{'Recebido' if tipo == 'Entrada' else 'Gasto'} manual referente a {desc}"
            supabase.table("transacoes").insert({
                "banco": "Carteira", "mensagem_notificacao": msg, "valor": valor, "categoria": cat
            }).execute()
            st.success("Salvo!")
            st.rerun()

# --- CORPO PRINCIPAL ---
df_raw_bd = pd.DataFrame(supabase.table("transacoes").select("*").order("data_hora", desc=True).execute().data)
df_regras_bd = carregar_regras()

if not df_raw_bd.empty:
    df_clean = processar_dados(df_raw_bd, df_regras_bd)
    df_mes = df_clean[(df_clean['Data'].dt.month == mes) & (df_clean['Data'].dt.year == ano)].copy()

    if not df_mes.empty:
        # KPIs
        entradas = df_mes[df_mes['Tipo']=='Entrada']['Valor'].sum()
        saidas = df_mes[df_mes['Tipo']=='Saída']['Valor'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Entradas", f"R$ {entradas:,.2f}")
        c2.metric("Saídas", f"R$ {saidas:,.2f}")
        c3.metric("Saldo", f"R$ {entradas - saidas:,.2f}")
        
        st.divider()

        # Botão para atualizar regras
        if st.button("🔄 Reaplicar Regras em Tudo"):
            st.rerun()

        # Gráficos
        g1, g2 = st.columns(2)
        with g1:
            st.caption("Gastos por Categoria")
            if not df_mes[df_mes['Tipo']=='Saída'].empty:
                fig = px.pie(df_mes[df_mes['Tipo']=='Saída'], values='Valor', names='Categoria', hole=0.5)
                st.plotly_chart(fig, use_container_width=True)
        with g2:
            st.caption("Evolução Diária")
            diario = df_mes.groupby(df_mes['Data'].dt.date)['Valor'].sum().reset_index()
            fig2 = px.bar(diario, x='Data', y='Valor')
            st.plotly_chart(fig2, use_container_width=True)

        # Tabela Editável
        st.subheader("📋 Extrato Interativo")
        df_editor = df_mes[['id', 'Data', 'Descrição', 'Valor', 'Tipo', 'Categoria', 'Banco']].copy()
        
        edicao = st.data_editor(
            df_editor,
            column_config={
                "id": None,
                "Categoria": st.column_config.SelectboxColumn("Categoria", options=lista_categorias, required=True),
                "Data": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY HH:mm")
            },
            hide_index=True, use_container_width=True, num_rows="dynamic", key="editor_dados"
        )
        
        # Deletar
        if len(edicao) < len(df_editor):
            ids_originais = set(df_editor['id'])
            ids_novos = set(edicao['id'])
            for id_del in (ids_originais - ids_novos):
                supabase.table("transacoes").delete().eq("id", id_del).execute()
            st.toast("Item deletado!")
            st.rerun()

        # Salvar Alterações de Categoria
        with st.expander("Ferramentas Avançadas"):
            if st.button("💾 Salvar Alterações Manuais de Categoria"):
                for index, row in edicao.iterrows():
                    supabase.table("transacoes").update({"categoria": row['Categoria']}).eq("id", row['id']).execute()
                st.success("Atualizado!")
                st.rerun()

    else:
        st.warning("Sem dados no mês.")
else:
    st.info("Banco vazio.")