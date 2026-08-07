import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="Painel Operacional de Leituras", layout="wide")
st.title("📊 Painel de Controle de Leituras, Lotes e Impedimentos")
st.markdown("---")

uploaded_files = st.file_uploader(
    "Faça o upload das planilhas (.csv ou .xlsx)", 
    type=["csv", "xlsx"], 
    accept_multiple_files=True
)

if uploaded_files:
    try:
        lista_dfs = []
        
        for file in uploaded_files:
            df_temp = None
            if file.name.endswith('.csv'):
                # Tenta diferentes delimitadores e codificações
                for sep in [';', ',', '\t']:
                    for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
                        try:
                            file.seek(0)
                            df_temp = pd.read_csv(file, sep=sep, encoding=enc, engine='python')
                            if len(df_temp.columns) > 1:
                                break
                        except Exception:
                            continue
                    if df_temp is not None and len(df_temp.columns) > 1:
                        break
            else:
                df_temp = pd.read_excel(file)

            if df_temp is not None:
                lista_dfs.append(df_temp)

        if lista_dfs:
            df_raw = pd.concat(lista_dfs, ignore_index=True)

            # 1. REMOÇÃO DE CARACTERES INVISÍVEIS (\xa0) NOS CABEÇALHOS
            df_raw.columns = (
                df_raw.columns.astype(str)
                .str.replace('\xa0', ' ', regex=False)
                .str.replace(r'[\r\n]+', ' ', regex=True)
                .str.replace(r'\s+', ' ', regex=True)
                .str.strip()
                .str.upper() # Padroniza para maiúsculas
            )

            # 2. HIGIENIZAÇÃO DE TODAS AS CÉLULAS DE TEXTO
            for col in df_raw.columns:
                if df_raw[col].dtype == 'object':
                    df_raw[col] = (
                        df_raw[col]
                        .fillna('N/A')
                        .astype(str)
                        .str.replace('\xa0', ' ', regex=False) # Limpa espaço invisível do Excel
                        .str.replace(r'[\r\n]+', ' ', regex=True)
                        .str.replace(r'\s+', ' ', regex=True)
                        .str.strip()
                    )
                    df_raw[col] = df_raw[col].replace({'nan': 'N/A', 'None': 'N/A', '<NA>': 'N/A', '': 'N/A'})

            # Função auxiliar para localizar colunas de forma flexível
            def buscar_coluna(termos_busca, colunas_df):
                for termo in termos_busca:
                    for col in colunas_df:
                        if termo.upper() in col.upper():
                            return col
                return None

            col_tipo_atv = buscar_coluna(['TIPO_ATIVIDADE', 'TIPO ATIVIDADE', 'ATIVIDADE'], df_raw.columns)
            col_dt_ini = buscar_coluna(['DT_INI_ACAO', 'DATA_INICIO', 'DT_INICIO', 'DATA_LEITURA'], df_raw.columns)
            col_dt_prev = buscar_coluna(['DAT_PREVISTA', 'DATA_PREVISTA', 'DT_PREVISTA'], df_raw.columns)
            col_agente = buscar_coluna(['AGENTE', 'NOME_AGENTE', 'NOM_AGENTE'], df_raw.columns)
            col_cod_agente = buscar_coluna(['COD_AGENTE', 'CODIGO_AGENTE'], df_raw.columns)
            col_status = buscar_coluna(['IND_STATUS_VISITA', 'STATUS_VISITA', 'STATUS'], df_raw.columns)
            col_nota = buscar_coluna(['COD_NOTA_VISITA', 'NOTA_VISITA', 'COD_NOTA'], df_raw.columns)

            # 🔍 PAINEL DE DIAGNÓSTICO E INSPEÇÃO (Para identificar qualquer erro no ficheiro)
            with st.expander("🔍 **Clique aqui para ver a Inspeção de Diagnóstico dos Ficheiros**", expanded=False):
                st.write("**Linhas brutas lidas:**", len(df_raw))
                st.write("**Colunas detetadas no ficheiro:**", list(df_raw.columns))
                st.write("**Mapeamento de Colunas:**", {
                    'TIPO_ATIVIDADE': col_tipo_atv,
                    'DT_INI_ACAO': col_dt_ini,
                    'AGENTE': col_agente,
                    'STATUS_VISITA': col_status
                })
                if col_tipo_atv:
                    st.write("**Valores únicos na coluna TIPO_ATIVIDADE:**", df_raw[col_tipo_atv].value_counts().to_dict())
                st.write("**Amostra dos Dados:**")
                st.dataframe(df_raw.head(5))

            total_linhas_brutas = len(df_raw)

            # 3. FILTRAGEM DE LEITURAS
            if col_tipo_atv:
                mask_leitura = df_raw[col_tipo_atv].str.lower().str.contains('leitura', na=False)
                df = df_raw[mask_leitura].copy()
            else:
                df = df_raw.copy()

            total_linhas_processadas = len(df)
            descartadas = total_linhas_brutas - total_linhas_processadas

            st.info(
                f"ℹ️ **Diagnóstico de Carga:** "
                f"Foram identificadas **{total_linhas_brutas} linhas**. "
                f"**{total_linhas_processadas} leituras** foram processadas "
                f"({descartadas} registos de sistema desconsiderados)."
            )

            if df.empty:
                st.warning("⚠️ Nenhum registo contendo 'Leitura' foi localizado. Verifique o painel de inspeção acima.")
            else:
                # 4. TRATAMENTO DE DATAS
                if col_dt_ini:
                    df['DT_INI_DT'] = pd.to_datetime(df[col_dt_ini], dayfirst=True, errors='coerce')
                    df['DATA_LEITURA'] = df['DT_INI_DT'].dt.strftime('%d/%m/%Y').fillna('Sem Data')
                else:
                    df['DT_INI_DT'] = pd.NaT
                    df['DATA_LEITURA'] = 'Sem Data'

                if col_dt_prev:
                    df['DAT_PREVISTA_DT'] = pd.to_datetime(df[col_dt_prev], dayfirst=True, errors='coerce')
                    df['DATA_PREVISTA_STR'] = df['DAT_PREVISTA_DT'].dt.strftime('%d/%m/%Y').fillna(df[col_dt_prev].astype(str))
                else:
                    df['DATA_PREVISTA_STR'] = 'Não Informada'

                # 5. TRATAMENTO DE IMPEDIMENTOS
                def limpa_nota(val):
                    if pd.isna(val) or str(val).strip() in ['nan', 'None', '', 'N/A']:
                        return ""
                    s = str(val).strip()
                    return s[:-2] if s.endswith('.0') else s

                df['NOTA_COD_STR'] = df[col_nota].apply(limpa_nota) if col_nota else ""
                df['STATUS_VISITA_STR'] = df[col_status].astype(str).str.strip() if col_status else ""

                is_impedimento = df['STATUS_VISITA_STR'].str.lower() == 'impedimento de leitura'
                df['IMP_FAM_1'] = is_impedimento & df['NOTA_COD_STR'].str.startswith('1')
                df['IMP_FAM_2'] = is_impedimento & df['NOTA_COD_STR'].str.startswith('2')

                # Garantia de colunas essenciais
                colunas_mapeadas = {
                    'NOM_BASE_OPERACIONAL': buscar_coluna(['NOM_BASE_OPERACIONAL', 'BASE'], df.columns),
                    'NOM_MUNICIPIO': buscar_coluna(['NOM_MUNICIPIO', 'MUNICIPIO'], df.columns),
                    'LOTE': buscar_coluna(['LOTE'], df.columns),
                    'LOCALIZACAO': buscar_coluna(['LOCALIZACAO'], df.columns),
                    'NOM_UNIDADE_LEITURA': buscar_coluna(['NOM_UNIDADE_LEITURA', 'UNIDADE_LEITURA'], df.columns),
                    'IND_TIPO': buscar_coluna(['IND_TIPO', 'TIPO_LEITURA'], df.columns),
                    'COD_AGENTE': col_cod_agente if col_cod_agente else 'N/A',
                    'AGENTE': col_agente if col_agente else 'N/A'
                }

                for col_std, col_orig in colunas_mapeadas.items():
                    if col_orig and col_orig in df.columns:
                        df[col_std] = df[col_orig]
                    else:
                        df[col_std] = 'N/A'

                # 6. FILTROS NA SIDEBAR
                st.sidebar.header("🎯 Filtros")

                def criar_multiselect(label, col):
                    opcoes = sorted([x for x in df[col].unique() if str(x) != 'nan'])
                    return st.sidebar.multiselect(label, options=opcoes, default=opcoes)

                f_base = criar_multiselect("Base Operacional", 'NOM_BASE_OPERACIONAL')
                f_mun = criar_multiselect("Município", 'NOM_MUNICIPIO')
                f_lote = criar_multiselect("Lote", 'LOTE')
                f_loc = criar_multiselect("Localização", 'LOCALIZACAO')
                f_unid = criar_multiselect("Unidade de Leitura", 'NOM_UNIDADE_LEITURA')
                f_agente = criar_multiselect("Agente", 'AGENTE')
                f_tipo = criar_multiselect("Tipo de Leitura", 'IND_TIPO')
                f_data = criar_multiselect("Data da Leitura", 'DATA_LEITURA')

                df_filtrado = df[
                    (df['NOM_BASE_OPERACIONAL'].isin(f_base)) &
                    (df['NOM_MUNICIPIO'].isin(f_mun)) &
                    (df['LOTE'].isin(f_lote)) &
                    (df['LOCALIZACAO'].isin(f_loc)) &
                    (df['NOM_UNIDADE_LEITURA'].isin(f_unid)) &
                    (df['AGENTE'].isin(f_agente)) &
                    (df['IND_TIPO'].isin(f_tipo)) &
                    (df['DATA_LEITURA'].isin(f_data))
                ]

                if df_filtrado.empty:
                    st.warning("⚠️ Nenhum registo encontrado com os filtros selecionados.")
                else:
                    # 7. MÉTRICAS
                    total_geral = len(df_filtrado)
                    imp_fam1 = int(df_filtrado['IMP_FAM_1'].sum())
                    imp_fam2 = int(df_filtrado['IMP_FAM_2'].sum())
                    leituras_sem_imp = total_geral - (imp_fam1 + imp_fam2)

                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("Total de Leituras", total_geral)
                    c2.metric("Sem Impedimento", leituras_sem_imp)
                    c3.metric("Imp. Família 1", imp_fam1)
                    c4.metric("Imp. Família 2", imp_fam2)
                    c5.metric("Agentes Ativos", df_filtrado['AGENTE'].nunique())

                    st.markdown("---")

                    def min_hora(series):
                        v = series.dropna()
                        return v.min().strftime('%H:%M') if not v.empty else "N/A"

                    def max_hora(series):
                        v = series.dropna()
                        return v.max().strftime('%H:%M') if not v.empty else "N/A"

                    # 8. TABELA RESUMO (dropna=False)
                    df_resumo = df_filtrado.groupby([
                        'DATA_LEITURA', 'DATA_PREVISTA_STR', 'NOM_BASE_OPERACIONAL',
                        'NOM_MUNICIPIO', 'LOTE', 'LOCALIZACAO', 'NOM_UNIDADE_LEITURA',
                        'IND_TIPO', 'COD_AGENTE', 'AGENTE'
                    ], dropna=False).agg(
                        TOTAL_LEITURAS=('AGENTE', 'count'),
                        HORARIO_INICIAL=('DT_INI_DT', min_hora),
                        HORARIO_FINAL=('DT_INI_DT', max_hora),
                        IMPEDIMENTOS_FAM_1=('IMP_FAM_1', 'sum'),
                        IMPEDIMENTOS_FAM_2=('IMP_FAM_2', 'sum')
                    ).reset_index()

                    df_resumo['LEITURAS_SEM_IMPEDIMENTO'] = df_resumo['TOTAL_LEITURAS'] - (
                        df_resumo['IMPEDIMENTOS_FAM_1'] + df_resumo['IMPEDIMENTOS_FAM_2']
                    )

                    df_resumo = df_resumo[[
                        'DATA_LEITURA', 'DATA_PREVISTA_STR', 'NOM_BASE_OPERACIONAL',
                        'NOM_MUNICIPIO', 'LOTE', 'LOCALIZACAO', 'NOM_UNIDADE_LEITURA',
                        'IND_TIPO', 'COD_AGENTE', 'AGENTE', 'TOTAL_LEITURAS',
                        'LEITURAS_SEM_IMPEDIMENTO', 'HORARIO_INICIAL', 'HORARIO_FINAL',
                        'IMPEDIMENTOS_FAM_1', 'IMPEDIMENTOS_FAM_2'
                    ]]

                    df_resumo.columns = [
                        'Data Realização', 'Data Prevista', 'Base Operacional',
                        'Município', 'Lote', 'Localização', 'Unidade de Leitura',
                        'Tipo (Passe/Repasse)', 'Código Agente', 'Nome Agente',
                        'Total de Leituras', 'Leituras sem Impedimento',
                        '1ª Leitura (Início)', 'Última Leitura (Fim)',
                        'Impedimento Família 1', 'Impedimento Família 2'
                    ]

                    # 9. GRÁFICOS
                    col_g1, col_g2 = st.columns(2)
                    with col_g1:
                        st.subheader("🏙️ Leituras por Município")
                        df_mun = df_filtrado.groupby('NOM_MUNICIPIO').size().reset_index(name='Qtd Leituras')
                        fig_mun = px.bar(df_mun, x='NOM_MUNICIPIO', y='Qtd Leituras', text_auto=True)
                        st.plotly_chart(fig_mun, use_container_width=True)

                    with col_g2:
                        st.subheader("⚠️ Impedimentos por Agente")
                        df_imp = df_filtrado.groupby('AGENTE')[['IMP_FAM_1', 'IMP_FAM_2']].sum().reset_index()
                        df_imp.columns = ['Agente', 'Família 1', 'Família 2']
                        fig_imp = px.bar(df_imp, x='Agente', y=['Família 1', 'Família 2'], barmode='group', text_auto=True)
                        st.plotly_chart(fig_imp, use_container_width=True)

                    st.markdown("---")
                    st.subheader("📋 Tabela Resumo da Produção")
                    st.dataframe(df_resumo, use_container_width=True)

                    # Exportação Excel
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_resumo.to_excel(writer, index=False, sheet_name='Resumo Leituras')

                    st.download_button(
                        label="📥 Baixar Planilha Tratada (Excel)",
                        data=buffer.getvalue(),
                        file_name="resumo_leituras_tratado.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

    except Exception as e:
        st.error(f"Erro ao processar ficheiros: {e}")
else:
    st.info("👆 Faça o upload da planilha para iniciar.")
