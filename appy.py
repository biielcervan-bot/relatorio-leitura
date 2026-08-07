import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="Painel Operacional de Leituras e Impedimentos", layout="wide")
st.title("📊 Painel Operacional de Produção e Leituras Limpas")
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
                for sep in [',', ';', '\t']:
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

            # 1. HIGIENIZAÇÃO DAS COLUNAS
            df_raw.columns = (
                df_raw.columns.astype(str)
                .str.replace('\xa0', ' ', regex=False)
                .str.replace(r'[\r\n]+', ' ', regex=True)
                .str.replace(r'\s+', ' ', regex=True)
                .str.strip()
            )

            # 2. HIGIENIZAÇÃO DE TEXTOS NAS CÉLULAS
            for col in df_raw.columns:
                if df_raw[col].dtype == 'object':
                    df_raw[col] = (
                        df_raw[col]
                        .fillna('N/A')
                        .astype(str)
                        .str.replace('\xa0', ' ', regex=False)
                        .str.replace(r'[\r\n]+', ' ', regex=True)
                        .str.replace(r'\s+', ' ', regex=True)
                        .str.strip()
                    )
                    df_raw[col] = df_raw[col].replace({'nan': 'N/A', 'None': 'N/A', '<NA>': 'N/A', '': 'N/A'})

            # Função de Mapeamento Flexível
            def buscar_coluna(termos, colunas):
                for t in termos:
                    for c in colunas:
                        if t.upper() in c.upper():
                            return c
                return None

            col_status = buscar_coluna(['IND_STATUS_VISITA', 'STATUS_VISITA', 'STATUS'], df_raw.columns)
            col_nota_vis = buscar_coluna(['COD_NOTA_VISITA', 'NOTA_VISITA'], df_raw.columns)
            col_nota_rev = buscar_coluna(['COD_NOTA_REVISITA', 'NOTA_REVISITA'], df_raw.columns)
            col_nota_ger = buscar_coluna(['COD_NOTA', 'NOTA'], df_raw.columns)
            col_foto = buscar_coluna(['QTD_FOTO'], df_raw.columns)
            col_dt_ini = buscar_coluna(['DT_INI_ACAO', 'DATA_LEITURA', 'DT_INICIO'], df_raw.columns)
            col_dt_prev = buscar_coluna(['DAT_PREVISTA', 'DATA_PREVISTA'], df_raw.columns)

            df = df_raw.copy()

            # 3. TRATAMENTO E FORMATAÇÃO DE DATAS NO PADRÃO BRASILEIRO (DD/MM/AAAA)
            if col_dt_ini and col_dt_ini in df.columns:
                df['DT_INI_DT'] = pd.to_datetime(df[col_dt_ini], errors='coerce', format='mixed')
                df['DATA_LEITURA'] = df['DT_INI_DT'].dt.strftime('%d/%m/%Y').fillna('Sem Data')
            else:
                df['DT_INI_DT'] = pd.NaT
                df['DATA_LEITURA'] = 'Sem Data'

            if col_dt_prev and col_dt_prev in df.columns:
                dt_prev_parsed = pd.to_datetime(df[col_dt_prev], errors='coerce', format='mixed')
                df['DATA_PREVISTA_STR'] = dt_prev_parsed.dt.strftime('%d/%m/%Y').fillna('Não Informada')
            else:
                df['DATA_PREVISTA_STR'] = 'Não Informada'

            # 4. CLASSIFICAÇÃO DE IMPEDIMENTOS (GRUPO 1 E GRUPO 2)
            def limpa_nota(val):
                if pd.isna(val) or str(val).strip() in ['nan', 'None', '', 'N/A', '0', '0.0']:
                    return ""
                s = str(val).strip()
                return s[:-2] if s.endswith('.0') else s

            def extrair_nota_serie(col_name):
                if col_name and col_name in df.columns:
                    return df[col_name].apply(limpa_nota)
                return pd.Series([""] * len(df))

            nota_vis = extrair_nota_serie(col_nota_vis)
            nota_rev = extrair_nota_serie(col_nota_rev)
            nota_ger = extrair_nota_serie(col_nota_ger)

            # Verificação se o código da nota inicia em 1 (Grupo 1) ou 2 (Grupo 2)
            df['IMP_GRUPO_1'] = (
                nota_vis.str.startswith('1') | 
                nota_rev.str.startswith('1') | 
                nota_ger.str.startswith('1')
            ).astype(int)

            df['IMP_GRUPO_2'] = (
                nota_vis.str.startswith('2') | 
                nota_rev.str.startswith('2') | 
                nota_ger.str.startswith('2')
            ).astype(int)

            # Fotos
            if col_foto and col_foto in df.columns:
                df['QTD_FOTO_NUM'] = pd.to_numeric(df[col_foto], errors='coerce').fillna(0).astype(int)
            else:
                df['QTD_FOTO_NUM'] = 0

            # Mapeamento de Colunas Organizacionais
            colunas_mapeadas = {
                'NOM_BASE_OPERACIONAL': buscar_coluna(['NOM_BASE_OPERACIONAL', 'BASE'], df.columns),
                'NOM_MUNICIPIO': buscar_coluna(['NOM_MUNICIPIO', 'MUNICIPIO'], df.columns),
                'LOTE': buscar_coluna(['LOTE'], df.columns),
                'LOCALIZACAO': buscar_coluna(['LOCALIZACAO'], df.columns),
                'NOM_UNIDADE_LEITURA': buscar_coluna(['NOM_UNIDADE_LEITURA', 'UNIDADE_LEITURA'], df.columns),
                'IND_TIPO': buscar_coluna(['IND_TIPO', 'TIPO_LEITURA'], df.columns),
                'COD_AGENTE': buscar_coluna(['COD_AGENTE', 'CODIGO_AGENTE'], df.columns),
                'AGENTE': buscar_coluna(['AGENTE', 'NOME_AGENTE', 'NOM_AGENTE'], df.columns)
            }

            for col_std, col_orig in colunas_mapeadas.items():
                if col_orig and col_orig in df.columns:
                    df[col_std] = df[col_orig]
                else:
                    df[col_std] = 'N/A'

            # 5. FILTROS NA SIDEBAR
            st.sidebar.header("🎯 Filtros de Exibição")

            def criar_multiselect(label, col_name):
                opcoes = sorted([x for x in df[col_name].unique() if str(x) != 'nan'])
                return st.sidebar.multiselect(label, options=opcoes, default=opcoes)

            f_base = criar_multiselect("Base Operacional", 'NOM_BASE_OPERACIONAL')
            f_mun = criar_multiselect("Município", 'NOM_MUNICIPIO')
            f_lote = criar_multiselect("Lote", 'LOTE')
            f_loc = criar_multiselect("Localização", 'LOCALIZACAO')
            f_unid = criar_multiselect("Unidade de Leitura", 'NOM_UNIDADE_LEITURA')
            f_agente = criar_multiselect("Agente", 'AGENTE')
            f_tipo = criar_multiselect("Tipo de Leitura (P/R)", 'IND_TIPO')
            f_data = criar_multiselect("Data da Leitura", 'DATA_LEITURA')

            # Aplicação dos Filtros
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
                st.warning("⚠️ Nenhum registro encontrado para os filtros selecionados.")
            else:
                # 6. MÉTRICAS CONSOLIDADAS
                tot_leituras = len(df_filtrado)
                tot_g1 = int(df_filtrado['IMP_GRUPO_1'].sum())
                tot_g2 = int(df_filtrado['IMP_GRUPO_2'].sum())
                tot_impedimentos = tot_g1 + tot_g2
                leituras_limpas = tot_leituras - tot_impedimentos
                tot_fotos = int(df_filtrado['QTD_FOTO_NUM'].sum())

                c1, c2, c3, c4, c5, c6 = st.columns(6)
                c1.metric("Total de Leituras", tot_leituras)
                c2.metric("⚠️ Imp. Grupo 1", tot_g1)
                c3.metric("⚠️ Imp. Grupo 2", tot_g2)
                c4.metric("🚫 Total Impedimentos", tot_impedimentos)
                c5.metric("✅ Leituras Limpas", leituras_limpas)
                c6.metric("📸 Total Fotos", tot_fotos)

                st.markdown("---")

                def min_hora(series):
                    v = series.dropna()
                    return v.min().strftime('%H:%M') if not v.empty else "N/A"

                def max_hora(series):
                    v = series.dropna()
                    return v.max().strftime('%H:%M') if not v.empty else "N/A"

                # 7. TABELA RESUMO OPERACIONAL (GROUPBY)
                df_resumo = df_filtrado.groupby([
                    'DATA_LEITURA', 'DATA_PREVISTA_STR', 'NOM_BASE_OPERACIONAL',
                    'NOM_MUNICIPIO', 'LOTE', 'LOCALIZACAO', 'NOM_UNIDADE_LEITURA',
                    'IND_TIPO', 'COD_AGENTE', 'AGENTE'
                ], dropna=False).agg(
                    TOTAL_LEITURAS=('AGENTE', 'count'),
                    IMP_GRUPO_1=('IMP_GRUPO_1', 'sum'),
                    IMP_GRUPO_2=('IMP_GRUPO_2', 'sum'),
                    TOTAL_FOTOS=('QTD_FOTO_NUM', 'sum'),
                    HORARIO_INICIAL=('DT_INI_DT', min_hora),
                    HORARIO_FINAL=('DT_INI_DT', max_hora)
                ).reset_index()

                df_resumo['TOTAL_IMPEDIMENTOS'] = df_resumo['IMP_GRUPO_1'] + df_resumo['IMP_GRUPO_2']
                df_resumo['LEITURAS_LIMPAS'] = df_resumo['TOTAL_LEITURAS'] - df_resumo['TOTAL_IMPEDIMENTOS']

                # Reordenando e renomeando colunas
                df_resumo = df_resumo[[
                    'DATA_LEITURA', 'DATA_PREVISTA_STR', 'NOM_BASE_OPERACIONAL',
                    'NOM_MUNICIPIO', 'LOTE', 'LOCALIZACAO', 'NOM_UNIDADE_LEITURA',
                    'IND_TIPO', 'COD_AGENTE', 'AGENTE',
                    'TOTAL_LEITURAS', 'IMP_GRUPO_1', 'IMP_GRUPO_2', 'TOTAL_IMPEDIMENTOS',
                    'LEITURAS_LIMPAS', 'TOTAL_FOTOS', 'HORARIO_INICIAL', 'HORARIO_FINAL'
                ]]

                df_resumo.columns = [
                    'Data Realização', 'Data Prevista', 'Base Operacional',
                    'Município', 'Lote', 'Localização', 'Unidade de Leitura',
                    'Tipo (Passe/Repasse)', 'Código Agente', 'Nome Agente',
                    'Total de Leituras', 'Imp. Grupo 1', 'Imp. Grupo 2',
                    'Total Impedimentos', '✅ Leituras Limpas',
                    'Total Fotos', '1ª Leitura (Início)', 'Última Leitura (Fim)'
                ]

                # 8. GRÁFICOS VISUAIS
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    st.subheader("📊 Produção por Agente")
                    df_agente_graf = df_filtrado.groupby('AGENTE').size().reset_index(name='Total Leituras')
                    fig_agente = px.bar(df_agente_graf, x='AGENTE', y='Total Leituras', text_auto=True, color_discrete_sequence=['#1f77b4'])
                    st.plotly_chart(fig_agente, use_container_width=True)

                with col_g2:
                    st.subheader("⚡ Proporção: Leituras Limpas vs Impedimentos")
                    df_distrib = pd.DataFrame({
                        'Categoria': ['Leituras Limpas', 'Impedimento Grupo 1', 'Impedimento Grupo 2'],
                        'Quantidade': [leituras_limpas, tot_g1, tot_g2]
                    })
                    df_distrib = df_distrib[df_distrib['Quantidade'] > 0]
                    
                    if not df_distrib.empty:
                        fig_pie = px.pie(
                            df_distrib, names='Categoria', values='Quantidade',
                            color='Categoria',
                            color_discrete_map={
                                'Leituras Limpas': '#2ca02c', 
                                'Impedimento Grupo 1': '#ff7f0e', 
                                'Impedimento Grupo 2': '#d62728'
                            },
                            hole=0.4
                        )
                        st.plotly_chart(fig_pie, use_container_width=True)

                st.markdown("---")
                st.subheader("📋 Tabela Resumo Consolidada")
                st.dataframe(df_resumo, use_container_width=True)

                # Exportação Excel
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_resumo.to_excel(writer, index=False, sheet_name='Resumo Operacional')

                st.download_button(
                    label="📥 Baixar Planilha Consolidada (Excel)",
                    data=buffer.getvalue(),
                    file_name="resumo_leituras_limpas.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    except Exception as e:
        st.error(f"Erro ao processar arquivo: {e}")
else:
    st.info("👆 Faça o upload do arquivo para iniciar a análise.")
