import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="Painel de Performance - Alta Carga", layout="wide")
st.title("⚡ Painel Operacional (Modo de Alta Performance - Datas Corrigidas)")
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
                for sep in [';', ',', '\t']:
                    for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
                        try:
                            file.seek(0)
                            df_temp = pd.read_csv(file, sep=sep, encoding=enc, engine='pyarrow')
                            if len(df_temp.columns) > 1:
                                break
                        except Exception:
                            try:
                                file.seek(0)
                                df_temp = pd.read_csv(file, sep=sep, encoding=enc, low_memory=False)
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
            with st.spinner("🚀 Processando grande volume de dados e corrigindo datas..."):
                df = pd.concat(lista_dfs, ignore_index=True)

                # 1. NORMALIZAÇÃO RÁPIDA DE COLUNAS
                df.columns = df.columns.astype(str).str.strip().str.upper()

                def buscar_coluna_exata(opcoes):
                    for op in opcoes:
                        if op in df.columns:
                            return op
                    return None

                col_cod_agente = buscar_coluna_exata(['COD_AGENTE', 'CODIGO_AGENTE', 'COD_LEITOR'])
                col_nome_agente = buscar_coluna_exata(['AGENTE', 'NOM_AGENTE', 'NOME_AGENTE', 'NOME_LEITOR'])
                col_dt_ini = buscar_coluna_exata(['DT_INI_ACAO', 'DATA_LEITURA', 'DT_INICIO'])
                col_dt_prev = buscar_coluna_exata(['DAT_PREVISTA', 'DATA_PREVISTA'])
                col_nota_vis = buscar_coluna_exata(['COD_NOTA_VISITA', 'NOTA_VISITA'])
                col_nota_rev = buscar_coluna_exata(['COD_NOTA_REVISITA', 'NOTA_REVISITA'])
                col_nota_ger = buscar_coluna_exata(['COD_NOTA', 'NOTA'])
                col_foto = buscar_coluna_exata(['QTD_FOTO'])

                # 2. ASSOCIANDO CÓDIGO E NOME DO AGENTE
                if col_cod_agente:
                    codigos = df[col_cod_agente].fillna('0').astype(str).str.replace(r'\.0$', '', regex=True)
                else:
                    codigos = pd.Series(['N/A'] * len(df))

                if col_nome_agente:
                    nomes = df[col_nome_agente].fillna('N/A').astype(str).str.strip()
                else:
                    nomes = pd.Series(['N/A'] * len(df))

                df['COD_AGENTE_STD'] = codigos
                df['AGENTE_STD'] = nomes
                df['AGENTE_COMPLETO'] = (codigos + " - " + nomes).astype('category')

                # 3. CONVERSÃO INTELIGENTE DE DATAS (SEM CONFUNDIR JULHO COM MARÇO)
                def converter_data_inteligente(col_name):
                    if not col_name or col_name not in df.columns:
                        return pd.Series(['Sem Data'] * len(df), dtype='category'), pd.Series([pd.NaT] * len(df))
                    
                    s_str = df[col_name].astype(str).str.strip()
                    dt_series = pd.Series(pd.NaT, index=df.index)

                    # Passo A: Formatos ISO (YYYY-MM-DD HH:MM:SS ou YYYY-MM-DD)
                    mask_iso = s_str.str.match(r'^\d{4}-\d{2}-\d{2}')
                    if mask_iso.any():
                        dt_series[mask_iso] = pd.to_datetime(s_str[mask_iso], errors='coerce')

                    # Passo B: Formatos BR (DD/MM/YYYY HH:MM:SS ou DD/MM/YYYY)
                    mask_br = s_str.str.match(r'^\d{2}/\d{2}/\d{4}')
                    if mask_br.any():
                        dt_series[mask_br] = pd.to_datetime(s_str[mask_br], dayfirst=True, errors='coerce')

                    # Passo C: Fallback para quaisquer formatos restantes
                    mask_restante = dt_series.isna() & (s_str != 'nan') & (s_str != 'N/A')
                    if mask_restante.any():
                        dt_series[mask_restante] = pd.to_datetime(s_str[mask_restante], errors='coerce', format='mixed')

                    # Formatação final brasileira fixa DD/MM/AAAA
                    str_series = dt_series.dt.strftime('%d/%m/%Y').fillna('Sem Data').astype('category')
                    return str_series, dt_series

                df['DATA_LEITURA'], df['DT_INI_DT'] = converter_data_inteligente(col_dt_ini)
                df['DATA_PREVISTA_STR'], _ = converter_data_inteligente(col_dt_prev)

                # 4. CLASSIFICAÇÃO DE IMPEDIMENTOS
                def limpa_serie_nota(col_name):
                    if not col_name or col_name not in df.columns:
                        return pd.Series([''] * len(df))
                    return df[col_name].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True)

                s_vis = limpa_serie_nota(col_nota_vis)
                s_rev = limpa_serie_nota(col_nota_rev)
                s_ger = limpa_serie_nota(col_nota_ger)

                df['IMP_GRUPO_1'] = (s_vis.str.startswith('1') | s_rev.str.startswith('1') | s_ger.str.startswith('1')).astype('int8')
                df['IMP_GRUPO_2'] = (s_vis.str.startswith('2') | s_rev.str.startswith('2') | s_ger.str.startswith('2')).astype('int8')

                if col_foto and col_foto in df.columns:
                    df['QTD_FOTO_NUM'] = pd.to_numeric(df[col_foto], errors='coerce').fillna(0).astype('int32')
                else:
                    df['QTD_FOTO_NUM'] = 0

                # Outras Colunas Organizacionais
                for col_std, opcoes in {
                    'NOM_BASE_OPERACIONAL': ['NOM_BASE_OPERACIONAL', 'BASE'],
                    'NOM_MUNICIPIO': ['NOM_MUNICIPIO', 'MUNICIPIO'],
                    'LOTE': ['LOTE'],
                    'LOCALIZACAO': ['LOCALIZACAO'],
                    'NOM_UNIDADE_LEITURA': ['NOM_UNIDADE_LEITURA', 'UNIDADE_LEITURA'],
                    'IND_TIPO': ['IND_TIPO', 'TIPO_LEITURA']
                }.items():
                    c = buscar_coluna_exata(opcoes)
                    if c:
                        df[col_std] = df[c].fillna('N/A').astype(str).astype('category')
                    else:
                        df[col_std] = pd.Series(['N/A'] * len(df), dtype='category')

            # 5. FILTROS NA SIDEBAR
            st.sidebar.header("🎯 Filtros")

            def criar_multiselect(label, col_name):
                opcoes = sorted([x for x in df[col_name].cat.categories if str(x) not in ['nan', 'N/A', 'Sem Data']])
                if not opcoes:
                    opcoes = sorted([x for x in df[col_name].unique() if str(x) not in ['nan', 'N/A']])
                return st.sidebar.multiselect(label, options=opcoes, default=opcoes)

            f_base = criar_multiselect("Base Operacional", 'NOM_BASE_OPERACIONAL')
            f_mun = criar_multiselect("Município", 'NOM_MUNICIPIO')
            f_lote = criar_multiselect("Lote", 'LOTE')
            f_agente = criar_multiselect("Agente", 'AGENTE_COMPLETO')
            f_data = criar_multiselect("Data da Leitura", 'DATA_LEITURA')

            # Filtragem Rápida
            df_filtrado = df[
                (df['NOM_BASE_OPERACIONAL'].isin(f_base)) &
                (df['NOM_MUNICIPIO'].isin(f_mun)) &
                (df['LOTE'].isin(f_lote)) &
                (df['AGENTE_COMPLETO'].isin(f_agente)) &
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
                c1.metric("Total Leituras", f"{tot_leituras:,}".replace(",", "."))
                c2.metric("Imp. Grupo 1", f"{tot_g1:,}".replace(",", "."))
                c3.metric("Imp. Grupo 2", f"{tot_g2:,}".replace(",", "."))
                c4.metric("Total Impedimentos", f"{tot_impedimentos:,}".replace(",", "."))
                c5.metric("✅ Leituras Limpas", f"{leituras_limpas:,}".replace(",", "."))
                c6.metric("📸 Total Fotos", f"{tot_fotos:,}".replace(",", "."))

                st.markdown("---")

                def hora_min_max(s, tipo):
                    v = s.dropna()
                    if v.empty: return "N/A"
                    res = v.min() if tipo == 'min' else v.max()
                    return res.strftime('%H:%M') if pd.notna(res) else "N/A"

                # 7. TABELA RESUMO (GROUPBY ULTRARRÁPIDO)
                df_resumo = df_filtrado.groupby([
                    'DATA_LEITURA', 'DATA_PREVISTA_STR', 'NOM_BASE_OPERACIONAL',
                    'NOM_MUNICIPIO', 'LOTE', 'COD_AGENTE_STD', 'AGENTE_STD'
                ], as_index=False, observed=True).agg(
                    TOTAL_LEITURAS=('AGENTE_STD', 'count'),
                    IMP_GRUPO_1=('IMP_GRUPO_1', 'sum'),
                    IMP_GRUPO_2=('IMP_GRUPO_2', 'sum'),
                    TOTAL_FOTOS=('QTD_FOTO_NUM', 'sum'),
                    HORA_INI=('DT_INI_DT', lambda x: hora_min_max(x, 'min')),
                    HORA_FIM=('DT_INI_DT', lambda x: hora_min_max(x, 'max'))
                )

                df_resumo['TOTAL_IMPEDIMENTOS'] = df_resumo['IMP_GRUPO_1'] + df_resumo['IMP_GRUPO_2']
                df_resumo['LEITURAS_LIMPAS'] = df_resumo['TOTAL_LEITURAS'] - df_resumo['TOTAL_IMPEDIMENTOS']

                df_resumo.columns = [
                    'Data Realização', 'Data Prevista', 'Base Operacional',
                    'Município', 'Lote', 'Código Agente', 'Nome Agente',
                    'Total Leituras', 'Imp. Grupo 1', 'Imp. Grupo 2',
                    'Total Fotos', '1ª Leitura', 'Última Leitura',
                    'Total Impedimentos', '✅ Leituras Limpas'
                ]

                st.subheader("📋 Tabela Resumo Consolidada")
                st.dataframe(df_resumo, use_container_width=True)

                # Exportação Excel
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_resumo.to_excel(writer, index=False, sheet_name='Resumo')

                st.download_button(
                    label="📥 Baixar Excel Consolidado",
                    data=buffer.getvalue(),
                    file_name="resumo_leituras_limpas.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    except Exception as e:
        st.error(f"Erro ao processar: {e}")
else:
    st.info("👆 Faça o upload da planilha para processar.")
