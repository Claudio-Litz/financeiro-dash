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
    st.error("Erro de Conexão: Verifique os secrets (.streamlit/secrets.toml).")
    st.stop()

# --- FUNÇÕES ---

def carregar_categorias():
    """Carrega lista de categorias do banco ou usa padrão."""
    try:
        response = supabase.table("categorias").select("nome").execute()
        lista = [item['nome'] for item in response.data]
        return sorted(lista)
    except:
        return ["Geral", "Alimentação", "Transporte", "Lazer", "Contas"]

def carregar_regras():
    """Carrega regras de categorização automática."""
    try:
        response = supabase.table("regras").select("*").execute()
        return pd.DataFrame(response.data)
    except:
        return pd.DataFrame()

def categorizar_automatico(descricao, df_regras):
    """Aplica as regras salvas pelo usuário."""
    desc_lower = descricao.lower()
    if df_regras.empty:
        return "Geral"
    for index, row in df_regras.iterrows():
        if row['palavra_chave'].lower() in desc_lower:
            return row['categoria']
    return "Geral"

def processar_dados(df_raw, df_regras):
    """Limpa e organiza os dados vindos do Supabase."""
    dados_processados = []
    
    for idx, row in df_raw.iterrows():
        # Pegamos o texto original COMPLETO
        texto_original = row.get('mensagem_notificacao', '')
        valor = row.get('valor', 0.0)
        
        # 1. Valor (Mantemos a lógica de extrair valor se vier zerado)
        if valor == 0 or valor is None:
            match_valor = re.search(r'R\$\s?([\d\.]+,\d{2})', texto_original)
            valor = float(match_valor.group(1).replace('.', '').replace(',', '.')) if match_valor else 0.0

        # 2. Tipo (Mantemos a lógica de identificar Entrada/Saída)
        tipo_banco = row.get('tipo') 
        if tipo_banco and type(tipo_banco) == str:
            tipo = tipo_banco
        else:
            tipo = "Entrada" if any(x in texto_original.lower() for x in ["recebido", "crédito", "estorno", "devolvido"]) else "Saída"
        
        # --- MUDANÇA AQUI (Passo 3) ---
        # Antes tinha um filtro que cortava o texto.
        # Agora usamos o texto_original direto, apenas removendo espaços extras nas pontas.
        descricao = texto_original.strip() 
        
        if not descricao: # Se chegar vazio mesmo assim
            descricao = "Não Identificado"

        # 4. Categoria
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
            "Descrição": descricao, # <--- Agora vai o texto completo
            "Valor": valor,
            "Tipo": tipo,
            "Categoria": cat,
            "Banco": row.get('banco', 'Outros')
        })
    return pd.DataFrame(dados_processados)

# --- SIDEBAR (BARRA LATERAL) ---
with st.sidebar:
    st.title("🎛️ Controle")
    
    # Filtros de Data
    mes = st.selectbox("Mês", range(1, 13), index=datetime.now().month-1)
    ano = st.number_input("Ano", value=datetime.now().year)
    
    st.divider()
    
    # Gestão de Categorias
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

    # Robô de Regras
    with st.expander("🧠 Ensinar o Robô (Regras)"):
        with st.form("nova_regra"):
            p_chave = st.text_input("Se conter a palavra:", placeholder="Ex: ifood").lower()
            cat_alvo = st.selectbox("Categorizar como:", lista_categorias)
            if st.form_submit_button("Salvar Regra"):
                if p_chave:
                    supabase.table("regras").insert({"palavra_chave": p_chave, "categoria": cat_alvo}).execute()
                    st.success("Aprendido!")
                    st.rerun()
        
        df_regras_display = carregar_regras()
        if not df_regras_display.empty:
            st.caption("Regras Ativas:")
            st.dataframe(df_regras_display[['palavra_chave', 'categoria']], hide_index=True)

    st.divider()

    # Lançamento Manual
    st.markdown("### 📝 Lançar Manual")
    with st.form("manual"):
        tipo_manual = st.radio("Tipo", ["Saída", "Entrada"], horizontal=True)
        valor_manual = st.number_input("Valor", min_value=0.0, step=0.1)
        cat_manual = st.selectbox("Categoria", lista_categorias)
        desc_manual = st.text_input("Descrição")
        
        if st.form_submit_button("Lançar"):
            msg = f"{'Recebido' if tipo_manual == 'Entrada' else 'Gasto'} manual referente a {desc_manual}"
            # Aqui salvamos o TIPO explicitamente agora
            supabase.table("transacoes").insert({
                "banco": "Carteira", 
                "mensagem_notificacao": msg, 
                "valor": valor_manual, 
                "categoria": cat_manual,
                "tipo": tipo_manual # <--- NOVO CAMPO
            }).execute()
            st.success("Salvo!")
            st.rerun()

# --- CORPO PRINCIPAL ---
try:
    # Busca dados ordenados
    response = supabase.table("transacoes").select("*").order("data_hora", desc=True).execute()
    df_raw_bd = pd.DataFrame(response.data)
except Exception as e:
    st.error(f"Erro ao buscar dados: {e}")
    df_raw_bd = pd.DataFrame()

df_regras_bd = carregar_regras()

if not df_raw_bd.empty:
    df_clean = processar_dados(df_raw_bd, df_regras_bd)
    df_mes = df_clean[(df_clean['Data'].dt.month == mes) & (df_clean['Data'].dt.year == ano)].copy()

    if not df_mes.empty:
        # KPIs
        entradas = df_mes[df_mes['Tipo']=='Entrada']['Valor'].sum()
        saidas = df_mes[df_mes['Tipo']=='Saída']['Valor'].sum()
        saldo = entradas - saidas
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Entradas", f"R$ {entradas:,.2f}", delta_color="normal")
        c2.metric("Saídas", f"R$ {saidas:,.2f}", delta_color="inverse")
        c3.metric("Saldo", f"R$ {saldo:,.2f}", delta=f"{((saldo/entradas)*100) if entradas > 0 else 0:.1f}%")
        
        st.divider()

        # Botão de refresh forçado
        if st.button("🔄 Atualizar Dados"):
            st.rerun()

        # Gráficos
        g1, g2 = st.columns(2)
        with g1:
            st.caption("Gastos por Categoria")
            dados_pizza = df_mes[df_mes['Tipo']=='Saída']
            if not dados_pizza.empty:
                fig = px.pie(dados_pizza, values='Valor', names='Categoria', hole=0.5, color_discrete_sequence=px.colors.sequential.RdBu)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sem saídas neste mês.")
                
        with g2:
            st.caption("Evolução Diária")
            diario = df_mes.groupby(df_mes['Data'].dt.date)['Valor'].sum().reset_index()
            fig2 = px.bar(diario, x='Data', y='Valor', color_discrete_sequence=['#3182ce'])
            st.plotly_chart(fig2, use_container_width=True)

        # --- TABELA EDITÁVEL (AQUI ESTÁ A MÁGICA) ---
        st.subheader("📋 Extrato Interativo")
        
        df_editor = df_mes[['id', 'Data', 'Descrição', 'Valor', 'Tipo', 'Categoria']].copy()
        
        edicao = st.data_editor(
            df_editor,
            column_config={
                "id": None, # Esconde ID
                "Categoria": st.column_config.SelectboxColumn(
                    "Categoria", 
                    options=lista_categorias, 
                    required=True
                ),
                # Configura o TIPO para ser uma caixa de seleção
                "Tipo": st.column_config.SelectboxColumn(
                    "Tipo",
                    options=["Entrada", "Saída"],
                    required=True
                ),
                "Descrição": st.column_config.TextColumn("Descrição"),
                "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                "Data": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY HH:mm", disabled=True)
            },
            hide_index=True, 
            use_container_width=True, 
            num_rows="dynamic", 
            key="editor_dados"
        )
        
        # Lógica de DELETAR
        if len(edicao) < len(df_editor):
            ids_originais = set(df_editor['id'])
            ids_novos = set(edicao['id'])
            for id_del in (ids_originais - ids_novos):
                supabase.table("transacoes").delete().eq("id", id_del).execute()
            st.toast("Transação excluída!")
            st.rerun()

        # --- ÁREA DE SALVAMENTO ---
        with st.expander("💾 Salvar Alterações", expanded=True):
            st.caption("Edite os itens na tabela acima e clique no botão abaixo para gravar no banco.")
            
            if st.button("Confirmar Alterações na Tabela"):
                progresso = st.progress(0)
                total_linhas = len(edicao)
                
                for index, row in edicao.iterrows():
                    # Pega os dados da linha
                    id_transacao = row['id']
                    
                    # Atualiza TUDO: Categoria, Valor, Descrição e TIPO
                    dados_para_atualizar = {
                        "categoria": row['Categoria'],
                        "valor": row['Valor'],
                        "mensagem_notificacao": row['Descrição'], # Usa a coluna descrição como msg
                        "tipo": row['Tipo'] # <--- Salva o tipo (Entrada/Saída)
                    }
                    
                    # Envia pro Supabase
                    supabase.table("transacoes").update(dados_para_atualizar).eq("id", id_transacao).execute()
                    
                    # Atualiza barra de progresso
                    progresso.progress((index + 1) / total_linhas)
                
                st.success("Dados atualizados com sucesso!")
                st.rerun()

    else:
        st.warning("Nenhuma transação encontrada neste mês.")
else:
    st.info("Banco de dados vazio. Adicione uma transação manual ou aguarde notificações.")