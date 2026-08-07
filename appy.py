import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="Painel Operacional de Leituras", layout="wide")
st.title("📊 Painel de Controle de Leituras, Lotes e Impedimentos")
st.markdown("---")

# Upload de múltiplos arquivos
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
                # Tenta diferentes codificações e separadores sem descartar linhas
                for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
                    try:
                        file.seek(0)
                        df_temp = pd.read_csv(file, sep=';', encoding=enc)
                        if len(df_temp.columns) <= 1:
                            file.seek(0)
                            df_temp = pd.read_csv(file, sep=',', encoding=enc)
                        break
                    except Exception:
                        continue
            else:
                df_temp = pd.read_excel(file)

            if df_temp is not None:
                lista_dfs.append(df_temp)

        if lista_dfs:
            df_raw = pd.concat(lista_dfs, ignore_index=True)
            df_raw.columns = df_raw.columns.str.strip()

            # 🧹 Limpeza de quebras de linha e espaços nas colunas de texto
            for col in df_raw.columns:
                if df_raw[col].dtype == 'object':
                    df_raw[col] = (
                        df_raw[col]
                        .astype(str)
                        .str.replace(r'[\r\n]+', ' ', regex=True)
                        .str.replace(r'\s+', ' ', regex=True)
                        .str.strip()
                    )

            total_linhas_brutas = len(df_raw)

            # 1. Filtro do TIPO_ATIVIDADE (Considera variações de 'leitura')
            if 'TIPO_ATIVIDADE' in df_raw.columns:
                mask_leitura = df_raw['TIPO_ATIVIDADE'].fillna('').str.lower().str.contains('leitura', na=False)
                df = df_raw[mask_leitura].copy()
            else:
                df = df_raw.copy()

            total_linhas_processadas = len(df)
            descartadas = total_linhas_brutas - total_linhas_processadas

            # Diagnóstico de Carga
            st.info(
                f"ℹ️ **Diagnóstico de Carga de Dados:** "
                f"Foram identificadas **{total_linhas_brutas} linhas** no arquivo. "
                f"**{total_linhas_processadas} leituras** foram processadas. "
                f"({descartadas} eventos de sistema foram desconsiderados)."
            )

            if df.empty:
                st.warning("⚠️ Nenhum registro contendo 'Leitura' foi encontrado na coluna TIPO_ATIVIDADE.")
            else:
                # 2. Tratamento de Datas e Horários
                df['DT_INI_DT'] = pd.to_datetime(df['DT_INI_ACAO'], dayfirst=True, errors='coerce')
                df['DATA_LEITURA'] = df['DT_INI_DT'].dt.strftime('%d/%m/%Y').fillna('Sem Data')
                df['HORA_LEITURA'] = df['DT_INI_DT'].dt.strftime('%H:%M').fillna('N/A')

                # 3. Tratamento da Data Prevista
                if 'DAT_PREVISTA' in df.columns:
                    df['DAT_PREVISTA_DT'] = pd.to_datetime(df['DAT_PREVISTA'], dayfirst=True, errors='coerce')
                    df['DATA_PREVISTA_STR'] = df['DAT_PREVISTA_DT'].dt.strftime('%d/%m/%Y').fillna(df['DAT_PREVISTA'].astype(str))
                else:
                    df['DATA_PREVISTA_STR'] = 'Não Informada'

                # 4. Tratamento dos Impedimentos
                def limpa_nota_codigo(val):
                    if pd.isna(val) or str(val).strip() in ['nan', 'None', '']:
                        return ""
                    s = str(val).strip()
                    if s.endswith('.0'):
                        s = s[:-2]
                    return s

                df['NOTA_COD_STR'] = df['COD_NOTA_VISITA'].apply(limpa_nota_codigo) if 'COD_NOTA_VISITA' in df.columns else ""
                df['STATUS_VISITA_STR'] = df['IND_STATUS_VISITA'].astype(str).str.strip() if 'IND_STATUS_VISITA' in df.columns else ""

                is_impedimento = df['STATUS_VISITA_STR'] == 'Impedimento de Leitura'
                df['IMP_FAM_1'] = is_impedimento & df['NOTA_COD_STR'].str.startswith('1')
                df['IMP_FAM_2'] = is_impedimento & df['NOTA_COD_STR'].str.startswith('2')

                # Preenchimento de colunas categóricas para evitar que fiquem NaN
                colunas_texto = [
                    'NOM_BASE_OPERACIONAL', 'NOM_MUNICIPIO', 'LOTE', 
                    'LOCALIZACAO', 'NOM_UNIDADE_LEITURA', 'IND_TIPO', 
                    'COD_AGENTE', 'AGENTE'
                ]
                for col in colunas_texto:
                    if col in df.columns:
                        df[col] = df[col].fillna('N/A').replace({'nan': 'N/A', '': 'N/A', 'None': 'N/A'})
                    else:
                        df[col] = 'N/A'

                # Barra Lateral - Filtros
                st.sidebar.header("🎯 Filtros")

                bases_disp = sorted([x for x in df['NOM_BASE_OPERACIONAL'].unique()])
                filtro_base = st.sidebar.multiselect("Base Operacional", options=bases_disp, default=bases_disp)

                municipios_disp = sorted([x for x in df['NOM_MUNICIPIO'].unique()])
                filtro_municipio = st.sidebar.multiselect("Município", options=municipios_disp, default=municipios_disp)

                lotes_disp = sorted([x for x in df['LOTE'].unique()])
                filtro_lote = st.sidebar.multiselect("Lote", options=lotes_disp, default=lotes_disp)

                localizacao_disp = sorted([x for x in df['LOCALIZACAO'].unique()])
                filtro_localizacao = st.sidebar.multiselect("Localização", options=localizacao_disp, default=localizacao_disp)

                unidades_disp = sorted([x for x in df['NOM_UNIDADE_LEITURA'].unique()])
                filtro_unidade = st.sidebar.multiselect("Unidade de Leitura", options=unidades_disp, default=unidades_disp)

                agentes_disp = sorted([x for x in df['AGENTE'].unique()])
                filtro_agente = st.sidebar.multiselect("Agente", options=agentes_disp, default=agentes_disp)

                tipo_disp = sorted([x for x in df['IND_TIPO'].unique()])
                filtro_tipo = st.sidebar.multiselect("Tipo de Leitura (IND_TIPO)", options=tipo_disp, default=tipo_disp)

                datas_disp = sorted([x for x in df['DATA_LEITURA'].unique()])
                filtro_data = st.sidebar.multiselect("Data da Leitura", options=datas_disp, default=datas_disp)

                # Aplicação dos Filtros
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
                    st.warning("Nenhum registro encontrado com os filtros selecionados.")
                else:
                    # Métricas Principais
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

                    # ⚠️ AGRUPAMENTO COM dropna=False PARA NÃO PERDER LINHAS NULAS
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
                        TOTAL_LEITURAS=('DT_INI_DT', 'count'),
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

                    # Gráficos
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

                    # Botão para Download
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
