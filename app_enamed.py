import streamlit as st
import pandas as pd
import plotly.express as px
import io
import os

# 1. CONFIGURAÇÃO INICIAL
st.set_page_config(page_title="ENAMED Analytics P360", layout="wide")
st.title("🩺 ENAMED: Inteligência de Dados By Paciente 360")
st.markdown("---")

# 2. FUNÇÃO DE CARREGAMENTO COM SUPORTE A PARQUET
@st.cache_data(show_spinner="Carregando arquivos...")
def carregar_dados_otimizado(uploaded_file, default_path, is_excel=False):
    df = None
    # 1. Prioriza Upload
    if uploaded_file is not None:
        if is_excel: df = pd.read_excel(uploaded_file)
        elif uploaded_file.name.endswith('.parquet'): df = pd.read_parquet(uploaded_file)
        else: df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding='utf-8-sig')
    
    # 2. Se não houver upload, tenta arquivo local (priorizando parquet)
    elif os.path.exists(default_path):
        # Tenta achar a versão parquet do arquivo padrão se não for excel
        path_parquet = default_path.replace('.csv', '.parquet')
        if not is_excel and os.path.exists(path_parquet):
            df = pd.read_parquet(path_parquet)
        elif is_excel:
            df = pd.read_excel(default_path)
        else:
            df = pd.read_csv(default_path, sep=None, engine='python', encoding='utf-8-sig')
    
    if df is not None:
        df = df.dropna(how='all')
        df.columns = [str(c).strip().upper() for c in df.columns]
    return df

# 3. FUNÇÃO DE PROCESSAMENTO PESADO CACHEADA (A "GRANDE VACINA")
@st.cache_data(show_spinner="Executando cruzamentos pedagógicos complexos...")
def processar_base_consolidada(df_alunos, df_gab, df_mapa):
    # Identificação de colunas
    col_ies = [c for c in df_alunos.columns if 'IES_NOME' in c or 'NO_IES' in c][0]
    col_cad = [c for c in df_alunos.columns if 'CADERNO' in c][0]
    col_p360 = [c for c in df_alunos.columns if 'P360' in c][0]

    # Normalização de tipos
    for d in [df_alunos, df_gab, df_mapa]:
        d[col_cad] = pd.to_numeric(d[col_cad], errors='coerce').fillna(0).astype(int)

    # Melt Alunos
    q_aluno = [c for c in df_alunos.columns if 'DS_VT_ESC_OBJ' in c]
    df_long = df_alunos.melt(id_vars=[col_ies, col_cad, col_p360], value_vars=q_aluno, var_name='Q', value_name='RESPOSTA')
    df_long['NU_QUESTAO'] = pd.to_numeric(df_long['Q'].str.extract(r'(\d+)')[0], errors='coerce')

    # Melt Gabarito
    q_gab = [c for c in df_gab.columns if 'DS_VT_GAB_OBJ' in c]
    df_gab_l = df_gab.melt(id_vars=[col_cad], value_vars=q_gab, var_name='G', value_name='GABARITO')
    df_gab_l['NU_QUESTAO'] = pd.to_numeric(df_gab_l['G'].str.extract(r'(\d+)')[0], errors='coerce')

    # Merge Final
    df_m = pd.merge(df_long.dropna(subset=['NU_QUESTAO']), df_gab_l.dropna(subset=['NU_QUESTAO']), on=[col_cad, 'NU_QUESTAO'])
    df_m = pd.merge(df_m, df_mapa.dropna(subset=['NU_QUESTAO']), on=[col_cad, 'NU_QUESTAO'], how='left')

    # Cálculos e Padronização
    df_m['RESPOSTA'] = df_m['RESPOSTA'].astype(str).str.strip().str.upper()
    df_m['GABARITO'] = df_m['GABARITO'].astype(str).str.strip().str.upper()
    df_m['ACERTO'] = ((df_m['RESPOSTA'] == df_m['GABARITO']) | (df_m['GABARITO'] == 'ANULADA')).astype(int)
    df_m['GRANDE_AREA'] = df_m['GRANDE_AREA'].fillna('NÃO MAPEADO').astype(str).str.upper()
    df_m['SUBESPECIALIDADE'] = df_m['SUBESPECIALIDADE'].fillna('GERAL').astype(str).str.upper()
    df_m['DIAGNOSTICO'] = df_m['DIAGNOSTICO'].fillna('-').astype(str).str.upper()

    return df_m, col_ies, col_cad, col_p360, df_gab_l

# 4. BARRA LATERAL
with st.sidebar:
    st.header("📂 Gestão de Dados")
    u_alunos = st.file_uploader("Trocar Alunos", type=["csv", "parquet"])
    u_gab = st.file_uploader("Trocar Gabarito", type=["csv", "parquet"])
    u_mapa = st.file_uploader("Trocar Mapeamento", type=["xlsx"])
    st.divider()
    apenas_p360 = st.checkbox("Média Nacional apenas P360", value=False)

# 5. EXECUÇÃO DO FLUXO
df_a_raw = carregar_dados_otimizado(u_alunos, "base_alunos.csv")
df_g_raw = carregar_dados_otimizado(u_gab, "base_gabarito.csv")
df_m_raw = carregar_dados_otimizado(u_mapa, "base_mapeamento.xlsx", is_excel=True)

if df_a_raw is not None and df_g_raw is not None and df_m_raw is not None:
    # Chama o processamento pesado com CACHE
    df, col_ies, col_cad, col_p360, df_gab_l = processar_base_consolidada(df_a_raw, df_g_raw, df_m_raw)

    # --- INTERFACE PRINCIPAL ---
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        ies_sel = st.selectbox("🏥 Instituição:", sorted(df[col_ies].unique()))
    with col_t2:
        c_list = sorted(df[col_cad].unique())
        cad_sel = st.multiselect("📚 Cadernos:", options=c_list, default=c_list)

    # Filtros Dinâmicos Rápidos
    df_f = df[(df[col_ies] == ies_sel) & (df[col_cad].isin(cad_sel))]
    df_n = df[df[col_cad].isin(cad_sel)]
    if apenas_p360:
        df_n = df_n[df_n[col_p360].astype(str).str.upper().str.contains('S|Y|1|TRUE', na=False)]

    # KPIs
    m_ies, m_comp = df_f['ACERTO'].mean(), df_n['ACERTO'].mean()
    c1, c2, c3 = st.columns(3)
    c1.metric("Média IES", f"{m_ies:.1%}")
    c2.metric("Média Comparativa", f"{m_comp:.1%}")
    c3.metric("Gap (pp)", f"{(m_ies - m_comp)*100:+.1f} pp")

    # --- TABELA DE GAPS ---
    st.header("🚩 Top 10 Lacunas Críticas (Diagnósticos)")
    tab_data = df_f.groupby(['GRANDE_AREA', 'SUBESPECIALIDADE', 'DIAGNOSTICO']).agg({'ACERTO': 'mean'}).rename(columns={'ACERTO': 'IES'}).reset_index()
    n_data = df_n.groupby(['GRANDE_AREA', 'SUBESPECIALIDADE', 'DIAGNOSTICO'])['ACERTO'].mean().reset_index(name='Nacional')
    tab_data = pd.merge(tab_data, n_data, on=['GRANDE_AREA', 'SUBESPECIALIDADE', 'DIAGNOSTICO'])
    tab_data['Diferença'] = (tab_data['IES'] - tab_data['Nacional']) * 100

    st.table(tab_data.sort_values('Diferença').head(10).style.format({'IES': '{:.1%}', 'Nacional': '{:.1%}', 'Diferença': '{:+.1f} pp'}))

    # --- SCATTER PLOTS (AGRUPADOS POR SUBESPECIALIDADE) ---
    st.header("🎯 Matrizes de Priorização")
    df_bubble = df_f.groupby(['GRANDE_AREA', 'SUBESPECIALIDADE']).agg({
        'ACERTO': 'mean', 'NU_QUESTAO': 'nunique',
        'DIAGNOSTICO': lambda x: '<br>• '.join(sorted([d for d in x.unique() if d != '-']))
    }).reset_index()
    n_bubble = df_n.groupby(['GRANDE_AREA', 'SUBESPECIALIDADE'])['ACERTO'].mean().reset_index(name='Nacional')
    viz_data = pd.merge(df_bubble, n_bubble, on=['GRANDE_AREA', 'SUBESPECIALIDADE'])
    viz_data['Diferença'] = (viz_data['ACERTO'] - viz_data['Nacional']) * 100

    for area in sorted(viz_data['GRANDE_AREA'].unique()):
        if area != 'NÃO MAPEADO':
            with st.expander(f"Grande Área: {area}", expanded=True):
                fig = px.scatter(viz_data[viz_data['GRANDE_AREA'] == area], x='NU_QUESTAO', y='Diferença', size='NU_QUESTAO', color='Diferença',
                                 hover_name='SUBESPECIALIDADE', hover_data={'DIAGNOSTICO': True},
                                 color_continuous_scale='RdYlGn', range_color=[-30, 30],
                                 labels={'NU_QUESTAO': 'Nº Questões', 'Diferença': 'Gap (pp)'})
                fig.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.3)
                st.plotly_chart(fig, width='stretch')

    # --- EXPORTAÇÃO ---
    st.divider()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_f.to_excel(writer, index=False, sheet_name='Bruto_Filtrado')
        tab_data.to_excel(writer, index=False, sheet_name='Gaps_Diagnosticos')
    st.download_button("🚀 Baixar Auditoria", output.getvalue(), f"ENAMED_{ies_sel}.xlsx")

else:
    st.warning("Aguardando carregamento das bases.")
