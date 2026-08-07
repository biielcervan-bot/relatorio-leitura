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
                for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
                    try:
                        file.seek(0)
                        temp = pd.read_csv(file, sep=';', encoding=enc)
                        if len(temp.columns) <= 1:
                            file.seek(0)
                            temp = pd.read_csv(file, sep=',', encoding=enc)
                        df_temp = temp
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

            # 1. Regra Fundamental: Filtrar apenas TIPO_ATIVIDADE == 'Leitura'
            if 'TIPO_ATIVIDADE' in df_raw.columns:
                df = df_raw[df_raw['TIPO_ATIVIDADE'].astype(str).str.strip().str.lower() == 'leitura'].copy()
            else:
                df = df_raw.copy()

            if df.empty:
                st.warning("⚠️ Nenhum registro de 'Leitura' encontrado no arquivo enviado. Verifique se a coluna TIPO_ATIVIDADE contém o valor 'Leitura'.")
            else:
                # 2. Tratamento de Datas e Horários (DT_INI_ACAO)
                df['DT_INI_DT'] = pd.to_datetime(df['DT_INI_ACAO'], dayfirst=True, errors='coerce')
                df['DATA_LEITURA'] = df['DT_INI_DT'].dt.strftime('%d/%m/%Y').fillna('Sem Data')
                df['HORA_LEITURA'] = df['DT_INI_DT'].dt.strftime('%H:%M').fillna('N/A')

                # 3. Tratamento da Data Prevista (DAT_PREVISTA)
                if 'DAT_PREVISTA' in df.columns:
                    df['DAT_PREVISTA_DT'] = pd.to_datetime(df['DAT_PREVISTA'], dayfirst=True, errors='coerce')
                    df['DATA_PREVISTA_STR'] = df['DAT_PREVISTA_DT'].dt.strftime('%d/%m/%Y').fillna(df['DAT_PREVISTA'].astype(str))
                else:
                    df['DATA_PREVISTA_STR'] = 'Não Informada'

                # 4. Tratamento dos Impedimentos (IND_STATUS_VISITA e COD_NOTA_VISITA)
                def limpa_nota_codigo(val):
                    if pd.isna(val):
                        return ""
                    s = str(val).strip()
                    if s.endswith('.0'):
                        s = s[:-2]
                    return s

                df['NOTA_COD_STR'] = df['COD_NOTA_VISITA'].apply(limpa_nota_codigo) if 'COD_NOTA_VISITA' in df.columns else ""
                df['STATUS_VISITA_STR'] = df['IND_STATUS_VISITA'].astype(str).str.strip() if 'IND_STATUS_VISITA' in df.columns else ""

                # Flag de Impedimento
                is_impedimento = df['STATUS_VISITA_STR'] == 'Impedimento de Leitura'
                df['IMP_FAM_1'] = is_impedimento & df['NOTA_COD_STR'].str.startswith('1')
                df['IMP_FAM_2'] = is_impedimento & df['NOTA_COD_STR'].str.startswith('2')

                # Padronização das colunas categóricas para evitar erros
                colunas_texto = [
                    'NOM_BASE_OPERACIONAL', 'NOM_MUNICIPIO', 'LOTE', 
                    'LOCALIZACAO', 'NOM_UNIDADE_LEITURA', 'IND_TIPO', 
                    'COD_AGENTE', 'AGENTE'
                ]
                for col in colunas_texto:
                    if col in df.columns:
                        df[col] = df[col].astype(str).str.strip().replace({'nan': 'N/A', '': 'N/A'})
                    else:
                        df[col] = 'N/A'

                # Barra Lateral - Filtros Interativos
                st.sidebar.header("🎯 Filtros")

                bases_disp = sorted([x for x in df['NOM_BASE_OPERACIONAL'].unique() if x != 'N/A'])
                filtro_base = st.sidebar.multiselect("Base Operacional", options=bases_disp, default=bases_disp)

                municipios_disp = sorted([x for x in df['NOM_MUNICIPIO'].unique() if x != 'N/A'])
                filtro_municipio = st.sidebar.multiselect("Município", options=municipios_disp, default=municipios_disp)

                lotes_disp = sorted([x for x in df['LOTE'].unique() if x != 'N/A'])
                filtro_lote = st.sidebar.multiselect("Lote", options=lotes_disp, default=lotes_disp)

                localizacao_disp = sorted([x for x in df['LOCALIZACAO'].unique() if x != 'N/A'])
                filtro_localizacao = st.sidebar.multiselect("Localização", options=localizacao_disp, default=localizacao_disp)

                unidades_disp = sorted([x for x in df['NOM_UNIDADE_LEITURA'].unique() if x != 'N/A'])
                filtro_unidade = st.sidebar.multiselect("Unidade de Leitura", options=unidades_disp, default=unidades_disp)

                agentes_disp = sorted([x for x in df['AGENTE'].unique() if x != 'N/A'])
                filtro_agente = st.sidebar.multiselect("Agente", options=agentes_disp, default=agentes_disp)

                tipo_disp = sorted([x for x in df['IND_TIPO'].unique() if x != 'N/A'])
                filtro_tipo = st.sidebar.multiselect("Tipo de Leitura (IND_TIPO)", options=tipo_disp, default=tipo_disp)

                datas_disp = sorted([x for x in df['DATA_LEITURA'].unique() if x != 'N/A'])
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
                    # Métricas Rápidas
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("Total de Leituras", len(df_filtrado))
                    c2.metric("Agentes Ativos", df_filtrado['AGENTE'].nunique())
                    c3.metric("Imp. Família 1", int(df_filtrado['IMP_FAM_1'].sum()))
                    c4.metric("Imp. Família 2", int(df_filtrado['IMP_FAM_2'].sum()))
                    c5.metric("Unid. de Leitura", df_filtrado['NOM_UNIDADE_LEITURA'].nunique())

                    st.markdown("---")

                    # Funções de Apoio para Horários
                    def min_hora(series):
                        valid = series.dropna()
                        return valid.min().strftime('%H:%M') if not valid.empty else "N/A"

                    def max_hora(series):
                        valid = series.dropna()
                        return valid.max().strftime('%H:%M') if not valid.empty else "N/A"

                    # 5. Agrupamento Detalhado Conforme Solicitado
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
                    ]).agg(
                        TOTAL_LEITURAS=('DT_INI_DT', 'count'),
                        HORARIO_INICIAL=('DT_INI_DT', min_hora),
                        HORARIO_FINAL=('DT_INI_DT', max_hora),
                        IMPEDIMENTOS_FAM_1=('IMP_FAM_1', 'sum'),
                        IMPEDIMENTOS_FAM_2=('IMP_FAM_2', 'sum')
                    ).reset_index()

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
                        '1ª Leitura (Início)',
                        'Última Leitura (Fim)',
                        'Impedimento Família 1',
                        'Impedimento Família 2'
                    ]

                    # Visualizações em Gráficos
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
                    st.subheader("📋 Tabela Resumo da Produção por Agente, Lote e Unidade de Leitura")
                    st.dataframe(df_resumo, use_container_width=True)

                    # Exportação para Excel
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
