import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="Painel Operacional de Leituras", layout="wide")
st.title("📊 Painel de Controle de Leituras, Lotes e Impedimentos")
st.markdown("---")

# Upload de múltiplos arquivos (.csv ou .xlsx)
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
                # Testa encodings para garantir leitura sem perda de caracteres
                for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
                    try:
                        file.seek(0)
                        # Engine python flexível para ler campos entre aspas com quebras de linha
                        df_temp = pd.read_csv(file, sep=None, encoding=enc, engine='python')
                        break
                    except Exception:
                        continue
            else:
                df_temp = pd.read_excel(file)

            if df_temp is not None:
                lista_dfs.append(df_temp)

        if lista_dfs:
            df_raw = pd.concat(lista_dfs, ignore_index=True)
            
            # 1. TRATAMENTO DE CABEÇALHOS (Nomes das colunas)
            df_raw.columns = (
                df_raw.columns.astype(str)
                .str.strip()
                .str.replace(r'[\r\n]+', ' ', regex=True)
                .str.replace(r'\s+', ' ', regex=True)
            )

            # 2. TRATAMENTO DE TEXTO EM TODAS AS COLUNAS
            for col in df_raw.columns:
                if df_raw[col].dtype == 'object':
                    df_raw[col] = (
                        df_raw[col]
                        .fillna('N/A')
                        .astype(str)
                        .str.replace(r'[\r\n]+', ' ', regex=True) # Remove Enter / Quebras de linha
                        .str.replace(r'\s+', ' ', regex=True)     # Remove múltiplos espaços
                        .str.strip()                              # Remove espaços nas pontas
                    )
                    # Normaliza textos de nulos
                    df_raw[col] = df_raw[col].replace({'nan': 'N/A', 'None': 'N/A', '<NA>': 'N/A', '': 'N/A'})

            total_linhas_brutas = len(df_raw)

            # 3. FILTRO DO TIPO_ATIVIDADE (Mantém apenas atividades de Leitura)
            if 'TIPO_ATIVIDADE' in df_raw.columns:
                mask_leitura = df_raw['TIPO_ATIVIDADE'].astype(str).str.lower().str.contains('leitura', na=False)
                df = df_raw[mask_leitura].copy()
            else:
                df = df_raw.copy()

            total_linhas_processadas = len(df)
            descartadas = total_linhas_brutas - total_linhas_processadas

            # Diagnóstico visual de carga
            st.info(
                f"ℹ️ **Diagnóstico de Carga de Dados:** "
                f"Foram identificadas **{total_linhas_brutas} linhas** no arquivo. "
                f"**{total_linhas_processadas} leituras** foram processadas. "
                f"({descartadas} eventos de início de turno/sistema foram desconsiderados)."
            )

            if df.empty:
                st.warning("⚠️ Nenhum registro contendo 'Leitura' foi encontrado na coluna TIPO_ATIVIDADE.")
            else:
                # 4. TRATAMENTO DE DATAS E HORÁRIOS
                if 'DT_INI_ACAO' in df.columns:
                    df['DT_INI_DT'] = pd.to_datetime(df['DT_INI_ACAO'], dayfirst=True, errors='coerce')
                    df['DATA_LEITURA'] = df['DT_INI_DT'].dt.strftime('%d/%m/%Y').fillna('Sem Data')
                else:
                    df['DT_INI_DT'] = pd.NaT
                    df['DATA_LEITURA'] = 'Sem Data'

                if 'DAT_PREVISTA' in df.columns:
                    df['DAT_PREVISTA_DT'] = pd.to_datetime(df['DAT_PREVISTA'], dayfirst=True, errors='coerce')
                    df['DATA_PREVISTA_STR'] = df['DAT_PREVISTA_DT'].dt.strftime('%d/%m/%Y').fillna(df['DAT_PREVISTA'].astype(str))
                else:
                    df['DATA_PREVISTA_STR'] = 'Não Informada'

                # 5. TRATAMENTO DE IMPEDIMENTOS
                def limpa_nota_codigo(val):
                    if pd.isna(val) or str(val).strip() in ['nan', 'None', '', 'N/A']:
                        return ""
                    s = str(val).strip()
                    if s.endswith('.0'):
                        s = s[:-2]
                    return s

                df['NOTA_COD_STR'] = df['COD_NOTA_VISITA'].apply(limpa_nota_codigo) if 'COD_NOTA_VISITA' in df.columns else ""
                df['STATUS_VISITA_STR'] = df['IND_STATUS_VISITA'].astype(str).str.strip() if 'IND_STATUS_VISITA' in df.columns else ""

                is_impedimento = df['STATUS_VISITA_STR'].str.lower() == 'impedimento de leitura'
                df['IMP_FAM_1'] = is_impedimento & df['NOTA_COD_STR'].str.startswith('1')
                df['IMP_FAM_2'] = is_impedimento & df['NOTA_COD_STR'].str.startswith('2')

                # Garantia de presença das colunas categóricas
                colunas_chave = [
                    'NOM_BASE_OPERACIONAL', 'NOM_MUNICIPIO', 'LOTE', 
                    'LOCALIZACAO', 'NOM_UNIDADE_LEITURA', 'IND_TIPO', 
                    'COD_AGENTE', 'AGENTE'
                ]
                for col in colunas_chave:
                    if col not in df.columns:
                        df[col] = 'N/A'

                # 6. FILTROS NA BARRA LATERAL (SIDEBAR)
                st.sidebar.header("🎯 Filtros")

                def criar_filtro_multiselect(label, col_name):
                    opcoes = sorted([x for x in df[col_name].unique() if str(x) != 'nan'])
                    return st.sidebar.multiselect(label, options=opcoes, default=opcoes)

                filtro_base = criar_filtro_multiselect("Base Operacional", 'NOM_BASE_OPERACIONAL')
                filtro_municipio = criar_filtro_multiselect("Município", 'NOM_MUNICIPIO')
                filtro_lote = criar_filtro_multiselect("Lote", 'LOTE')
                filtro_localizacao = criar_filtro_multiselect("Localização", 'LOCALIZACAO')
                filtro_unidade = criar_filtro_multiselect("Unidade de Leitura", 'NOM_UNIDADE_LEITURA')
                filtro_agente = criar_filtro_multiselect("Agente", 'AGENTE')
                filtro_tipo = criar_filtro_multiselect("Tipo de Leitura (IND_TIPO)", 'IND_TIPO')
                filtro_data = criar_filtro_multiselect("Data da Leitura", 'DATA_LEITURA')

                # Aplicação dos Filtros Selecionados
                df_filtrado = df[
                    (df['NOM_BASE_OPERACIONAL'].isin(filtro_base)) &
                    (df['NOM_MUNICIPIO'].isin(filtro_municipio)) &
                    (df['LOTE'].isin(filtro_lote)) &
                    (df['LOCALIZACAO'].isin(filtro_localizacao)) &
                    (df['NOM_UNIDADE_LEITURA'].isin(filtro_unidade)) &
                    (df['AGENTE'].isin(filtro_agente)) &
                    (df['IND_TIPO'].isin(filtro_tipo)) &
                    (df['DATA_LEITURA'].isin(filtro_data))
                ]

                if df_filtrado.empty:
                    st.warning("⚠️ Nenhum registro encontrado com os filtros selecionados.")
                else:
                    # 7. MÉTRICAS CARDINAIS
                    total_geral = len(df_filtrado)
                    imp_fam1 = int(df_filtrado['IMP_FAM_1'].sum())
                    imp_fam2 = int(df_filtrado['IMP_FAM_2'].sum())
                    total_impedimentos = imp_fam1 + imp_fam2
                    leituras_sem_imp = total_geral - total_impedimentos

                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("Total de Leituras", total_geral)
                    c2.metric("Leituras sem Impedimento", leituras_sem_imp)
                    c3.metric("Imp. Família 1", imp_fam1)
                    c4.metric("Imp. Família 2", imp_fam2)
                    c5.metric("Agentes Ativos", df_filtrado['AGENTE'].nunique())

                    st.markdown("---")

                    def min_hora(series):
                        valid = series.dropna()
                        return valid.min().strftime('%H:%M') if not valid.empty else "N/A"

                    def max_hora(series):
                        valid = series.dropna()
                        return valid.max().strftime('%H:%M') if not valid.empty else "N/A"

                    # 8. TABELA RESUMO (dropna=False impede perda de dados)
                    df_resumo = df_filtrado.groupby([
                        'DATA_LEITURA',
                        'DATA_PREVISTA_STR',
                        'NOM_BASE_OPERACIONAL',
                        'NOM_MUNICIPIO',
                        'LOTE',
                        'LOCALIZACAO',
                        'NOM_UNIDADE_LEITURA',
                        'IND_TIPO',
                        'COD_AGENTE',
                        'AGENTE'
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
                        'DATA_LEITURA',
                        'DATA_PREVISTA_STR',
                        'NOM_BASE_OPERACIONAL',
                        'NOM_MUNICIPIO',
                        'LOTE',
                        'LOCALIZACAO',
                        'NOM_UNIDADE_LEITURA',
                        'IND_TIPO',
                        'COD_AGENTE',
                        'AGENTE',
                        'TOTAL_LEITURAS',
                        'LEITURAS_SEM_IMPEDIMENTO',
                        'HORARIO_INICIAL',
                        'HORARIO_FINAL',
                        'IMPEDIMENTOS_FAM_1',
                        'IMPEDIMENTOS_FAM_2'
                    ]]

                    df_resumo.columns = [
                        'Data Realização',
                        'Data Prevista',
                        'Base Operacional',
                        'Município',
                        'Lote',
                        'Localização',
                        'Unidade de Leitura',
                        'Tipo (Passe/Repasse)',
                        'Código Agente',
                        'Nome Agente',
                        'Total de Leituras',
                        'Leituras sem Impedimento',
                        '1ª Leitura (Início)',
                        'Última Leitura (Fim)',
                        'Impedimento Família 1',
                        'Impedimento Família 2'
                    ]

                    # 9. GRÁFICOS INTERATIVOS
                    col_g1, col_g2 = st.columns(2)

                    with col_g1:
                        st.subheader("🏙️ Leituras por Município")
                        df_mun = df_filtrado.groupby('NOM_MUNICIPIO').size().reset_index(name='Qtd Leituras')
                        fig_mun = px.bar(df_mun, x='NOM_MUNICIPIO', y='Qtd Leituras', text_auto=True, color_discrete_sequence=['#1f77b4'])
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

                    # 10. BOTÃO DE DOWNLOAD EXCEL
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_resumo.to_excel(writer, index=False, sheet_name='Resumo Leituras e Lotes')

                    st.download_button(
                        label="📥 Baixar Planilha Tratada (Excel)",
                        data=buffer.getvalue(),
                        file_name="resumo_leituras_lotes_impedimentos.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os arquivos: {e}")
else:
    st.info("👆 Por favor, envie uma ou mais planilhas para iniciar a análise.")
