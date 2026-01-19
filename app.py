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

def categorizar_automatico(descricao):
    desc_lower = descricao.lower()
    regras = {
        "Transporte": ["uber", "99", "posto", "gasolina", "estacionamento", "ipiranga", "shell"],
        "Alimentação": ["ifood", "restaurante", "mercado", "padaria", "zédelivery", "burger", "pizza", "atacadão", "assai", "carrefour"],
        "Lazer": ["netflix", "spotify", "cinema", "steam", "jogos", "bar"],
        "Saúde": ["farmácia", "drogaria", "médico", "exame", "hospital"],
        "Moradia": ["luz", "agua", "internet", "aluguel", "condominio", "claro", "vivo", "tim"]
    }
    for categoria, palavras in regras.items():
        for palavra in palavras:
            if palavra in desc_lower:
                return categoria
    return "Geral"

def processar_dados(df_raw):
    dados_processados = []
    for idx, row in df_raw.iterrows():
        texto = row['mensagem_notificacao']
        
        # Valor
        valor = row['valor']
        if valor == 0 or valor is None:
            match_valor = re.search(r'R\$\s?([\d\.]+,\d{2})', texto)
            if match_valor:
                valor = float(match_valor.group(1).replace('.', '').replace(',', '.'))
            else:
                valor = 0.0

        # Tipo
        tipo = "Saída"
        if any(x in texto.lower() for x in ["recebido", "crédito", "estorno", "depósito"]):
            tipo = "Entrada"
        
        # Descrição Limpa
        termos_lixo = ["compra aprovada", "compra de", "r$", "bradesco", "inter", "pix enviado", "transacao", "no cartao"]
        desc_limpa = texto.lower()
        for t in termos_lixo:
            desc_limpa = desc_limpa.replace(t, "")
        descricao = desc_limpa.strip().title()
        if len(descricao) < 2: descricao = "Não Identificado"

        # Categoria (Prioridade: Banco > Automático)
        cat = row.get('categoria')
        if not cat or cat == "null":
            cat = categorizar_automatico(descricao)

        dados_processados.append({
            "id": row['id'], # Importante para deletar/editar
            "Data": pd.to_datetime(row['data_hora']),
            "Descrição": descricao,
            "Valor": valor,
            "Tipo": tipo,
            "Categoria": cat,
            "Banco": row['banco']
        })
    return pd.DataFrame(dados_processados)

# --- SIDEBAR ---
with st.sidebar:
    st.title("🎛️ Controle")
    mes = st.selectbox("Mês", range(1, 13), index=datetime.now().month-1)
    ano = st.number_input("Ano", value=datetime.now().year)
    lista_categorias = carregar_categorias()
    
    st.divider()
    with st.expander("➕ Adicionar Categoria"):
        nova_cat = st.text_input("Nome")
        if st.button("Criar"):
            supabase.table("categorias").insert({"nome": nova_cat}).execute()
            st.rerun()

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

if not df_raw_bd.empty:
    df_clean = processar_dados(df_raw_bd)
    df_mes = df_clean[(df_clean['Data'].dt.month == mes) & (df_clean['Data'].dt.year == ano)].copy()

    if not df_mes.empty:
        # 1. KPIs
        entradas = df_mes[df_mes['Tipo']=='Entrada']['Valor'].sum()
        saidas = df_mes[df_mes['Tipo']=='Saída']['Valor'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Entradas", f"R$ {entradas:,.2f}")
        c2.metric("Saídas", f"R$ {saidas:,.2f}")
        c3.metric("Saldo", f"R$ {entradas - saidas:,.2f}")
        
        st.divider()

        # 2. Gráficos
        g1, g2 = st.columns(2)
        with g1:
            st.caption("Gastos por Categoria")
            fig = px.pie(df_mes[df_mes['Tipo']=='Saída'], values='Valor', names='Categoria', hole=0.5)
            st.plotly_chart(fig, use_container_width=True)
        with g2:
            st.caption("Evolução Diária")
            diario = df_mes.groupby(df_mes['Data'].dt.date)['Valor'].sum().reset_index()
            fig2 = px.bar(diario, x='Data', y='Valor')
            st.plotly_chart(fig2, use_container_width=True)

        # 3. ÁREA DE EDIÇÃO E EXCLUSÃO (A LIXEIRA INTELIGENTE)
        st.subheader("📋 Extrato Interativo (Edite aqui)")
        st.info("Para editar a categoria, clique duas vezes na célula. Para excluir, selecione as linhas e clique no botão abaixo.")
        
        # Prepara o dataframe para edição (esconde ID mas usa ele)
        df_editor = df_mes[['id', 'Data', 'Descrição', 'Valor', 'Tipo', 'Categoria', 'Banco']].copy()
        
        edicao = st.data_editor(
            df_editor,
            column_config={
                "id": None, # Esconde o ID visualmente
                "Categoria": st.column_config.SelectboxColumn("Categoria", options=lista_categorias, required=True),
                "Data": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY HH:mm")
            },
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic", # Permite deletar/adicionar
            key="editor_dados"
        )
        
        # BOTÃO PARA EXPORTAR
        csv = df_mes.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Relatório (Excel/CSV)", data=csv, file_name="financas.csv", mime="text/csv")

        # LÓGICA DE SALVAR EDIÇÕES
        # Isso detecta se você deletou uma linha na tabela visual
        if len(edicao) < len(df_editor):
            # Descobre qual ID sumiu
            ids_originais = set(df_editor['id'])
            ids_novos = set(edicao['id'])
            ids_deletados = ids_originais - ids_novos
            
            if ids_deletados:
                for id_del in ids_deletados:
                    supabase.table("transacoes").delete().eq("id", id_del).execute()
                st.toast("Transação excluída!", icon="🗑️")
                st.rerun()

        # LÓGICA PARA ATUALIZAR CATEGORIA
        # Se mudou categoria na tabela, salva no banco
        # (Comparação simples para ver se algo mudou)
        # Nota: Em apps complexos fazemos diff, aqui vamos simplificar:
        # Se clicar num botão "Salvar Alterações de Categoria" é mais seguro
        
        with st.expander("Ferramentas Avançadas"):
            st.write("Se você mudou categorias na tabela acima, clique aqui para salvar no banco permanentemente:")
            if st.button("💾 Salvar Alterações de Categoria"):
                for index, row in edicao.iterrows():
                    # Atualiza categoria baseada no ID
                    supabase.table("transacoes").update({"categoria": row['Categoria']}).eq("id", row['id']).execute()
                st.success("Categorias atualizadas no banco!")
                st.rerun()

    else:
        st.warning("Sem dados neste mês.")
else:
    st.info("Banco vazio.")