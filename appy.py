import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="Painel de Qualidade e Produção de Leituras", layout="wide")
st.title("📊 Painel de Controle de Produção e Faixas de Leitura")
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

            # 1. TRATAMENTO DE NOMES DE COLUNAS (Espaços ocultos, Enter, \xa0)
            df_raw.columns = (
                df_raw.columns.astype(str)
                .str.replace('\xa0', ' ', regex=False)
                .str.replace(r'[\r\n]+', ' ', regex=True)
                .str.replace(r'\s+', ' ', regex=True)
                .str.strip()
            )

            # 2. TRATAMENTO DE TEXTOS EM TODAS AS CÉLULAS
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

            total_linhas_brutas = len(df_raw)

            # 3. FILTRAGEM DE LEITURAS
            if 'TIPO_ATIVIDADE' in df_raw.columns:
                mask_leitura = df_raw['TIPO_ATIVIDADE'].astype(str).str.lower().str.contains('leitura', na=False)
                df = df_raw[mask_leitura].copy()
            else:
                df = df_raw.copy()

            total_linhas_processadas = len(df)
            st.info(f"ℹ️ **Carga de Dados:** {total_linhas_brutas} linhas carregadas | {total_linhas_processadas} leituras processadas.")

            if df.empty:
                st.warning("⚠️ Nenhum registro contendo 'Leitura' foi localizado.")
            else:
                # 4. TRATAMENTO DE DATAS E HORÁRIOS
                if 'DT_INI_ACAO' in df.columns:
                    df['DT_INI_DT'] = pd.to_datetime(df['DT_INI_ACAO'], errors='coerce')
                    df['DATA_LEITURA'] = df['DT_INI_DT'].dt.strftime('%d/%m/%Y').fillna('Sem Data')
                else:
                    df['DT_INI_DT'] = pd.NaT
                    df['DATA_LEITURA'] = 'Sem Data'

                if 'DAT_PREVISTA' in df.columns:
                    df['DAT_PREVISTA_DT'] = pd.to_datetime(df['DAT_PREVISTA'], errors='coerce')
                    df['DATA_PREVISTA_STR'] = df['DAT_PREVISTA_DT'].dt.strftime('%d/%m/%Y').fillna(df['DAT_PREVISTA'].astype(str))
                else:
                    df['DATA_PREVISTA_STR'] = 'Não Informada'

                # 5. CLASSIFICAÇÃO DAS FAIXAS DE LEITURA (VERDE, AMARELA, VERMELHA)
                status_str = df['IND_STATUS_VISITA'].astype(str) if 'IND_STATUS_VISITA' in df.columns else st.Series([""] * len(df))
                
                df['FAIXA_VERDE'] = status_str.str.contains('verde', case=False, na=False)
                df['FAIXA_AMARELA'] = status_str.str.contains('amarela', case=False, na=False)
                df['FAIXA_VERMELHA'] = status_str.str.contains('vermelha', case=False, na=False)

                # Garantia de presença de QTD_FOTO
                if 'QTD_FOTO' in df.columns:
                    df['QTD_FOTO_NUM'] = pd.to_numeric(df['QTD_FOTO'], errors='coerce').fillna(0).astype(int)
                else:
                    df['QTD_FOTO_NUM'] = 0

                # Colunas de Agrupamento Essenciais
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

                # Aplicando os filtros
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
                    st.warning("⚠️ Nenhum registro encontrado com os filtros selecionados.")
                else:
                    # 7. CARDS DE MÉTRICAS PRINCIPAIS
                    tot_leituras = len(df_filtrado)
                    tot_verde = int(df_filtrado['FAIXA_VERDE'].sum())
                    tot_amarela = int(df_filtrado['FAIXA_AMARELA'].sum())
                    tot_vermelha = int(df_filtrado['FAIXA_VERMELHA'].sum())
                    tot_fotos = int(df_filtrado['QTD_FOTO_NUM'].sum())

                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Total de Leituras", tot_leituras)
                    m2.metric("🟢 Faixa Verde", tot_verde)
                    m3.metric("🟡 Faixa Amarela", tot_amarela)
                    m4.metric("🔴 Faixa Vermelha", tot_vermelha)
                    m5.metric("📸 Total de Fotos", tot_fotos)

                    st.markdown("---")

                    def min_hora(series):
                        valid = series.dropna()
                        return valid.min().strftime('%H:%M') if not valid.empty else "N/A"

                    def max_hora(series):
                        valid = series.dropna()
                        return valid.max().strftime('%H:%M') if not valid.empty else "N/A"

                    # 8. TABELA RESUMO DA PRODUÇÃO
                    df_resumo = df_filtrado.groupby([
                        'DATA_LEITURA', 'DATA_PREVISTA_STR', 'NOM_BASE_OPERACIONAL',
                        'NOM_MUNICIPIO', 'LOTE', 'LOCALIZACAO', 'NOM_UNIDADE_LEITURA',
                        'IND_TIPO', 'COD_AGENTE', 'AGENTE'
                    ], dropna=False).agg(
                        TOTAL_LEITURAS=('AGENTE', 'count'),
                        FAIXA_VERDE=('FAIXA_VERDE', 'sum'),
                        FAIXA_AMARELA=('FAIXA_AMARELA', 'sum'),
                        FAIXA_VERMELHA=('FAIXA_VERMELHA', 'sum'),
                        TOTAL_FOTOS=('QTD_FOTO_NUM', 'sum'),
                        HORARIO_INICIAL=('DT_INI_DT', min_hora),
                        HORARIO_FINAL=('DT_INI_DT', max_hora)
                    ).reset_index()

                    df_resumo.columns = [
                        'Data Realização', 'Data Prevista', 'Base Operacional',
                        'Município', 'Lote', 'Localização', 'Unidade de Leitura',
                        'Tipo (Passe/Repasse)', 'Código Agente', 'Nome Agente',
                        'Total de Leituras', '🟢 Faixa Verde', '🟡 Faixa Amarela',
                        '🔴 Faixa Vermelha', 'Total Fotos', '1ª Leitura (Início)',
                        'Última Leitura (Fim)'
                    ]

                    # 9. GRÁFICOS VISUAIS
                    col_g1, col_g2 = st.columns(2)

                    with col_g1:
                        st.subheader("📊 Produção por Agente")
                        df_agente_graf = df_filtrado.groupby('AGENTE').size().reset_index(name='Qtd Leituras')
                        fig_agente = px.bar(df_agente_graf, x='AGENTE', y='Qtd Leituras', text_auto=True, color_discrete_sequence=['#2ca02c'])
                        st.plotly_chart(fig_agente, use_container_width=True)

                    with col_g2:
                        st.subheader("🎨 Distribuição das Faixas de Leitura")
                        df_faixas = pd.DataFrame({
                            'Faixa': ['Verde', 'Amarela', 'Vermelha'],
                            'Quantidade': [tot_verde, tot_amarela, tot_vermelha]
                        })
                        fig_faixas = px.pie(
                            df_faixas, names='Faixa', values='Quantidade',
                            color='Faixa',
                            color_discrete_map={'Verde': '#2ca02c', 'Amarela': '#ff7f0e', 'Vermelha': '#d62728'},
                            hole=0.4
                        )
                        st.plotly_chart(fig_faixas, use_container_width=True)

                    st.markdown("---")
                    st.subheader("📋 Tabela Resumo Tratada")
                    st.dataframe(df_resumo, use_container_width=True)

                    # Exportação Excel
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_resumo.to_excel(writer, index=False, sheet_name='Resumo Producao Leituras')

                    st.download_button(
                        label="📥 Baixar Planilha Tratada (Excel)",
                        data=buffer.getvalue(),
                        file_name="resumo_producao_faixas_leituras.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os arquivos: {e}")
else:
    st.info("👆 Por favor, envie uma ou mais planilhas para iniciar a análise.")
