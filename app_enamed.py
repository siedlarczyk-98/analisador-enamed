import streamlit as st
import pandas as pd
import plotly.express as px
import io
import os

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="ENAMED Analytics P360", layout="wide")

st.title("🩺 ENAMED: Inteligência de Dados By Paciente 360")
st.markdown("---")

# 2. FUNÇÃO COM CACHE
@st.cache_data(show_spinner="A processar base de dados...")
def carregar_dados(uploaded_file, default_path, is_excel=False):
    df = None
    if uploaded_file is not None:
        if is_excel:
            df = pd.read_excel(uploaded_file)
        else:
            df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding='utf-8-sig')
    elif os.path.exists(default_path):
        if is_excel:
            df = pd.read_excel(default_path)
        else:
            df = pd.read_csv(default_path, sep=None, engine='python', encoding='utf-8-sig')
    
    if df is not None:
        df = df.dropna(how='all')
        df.columns = [str(c).strip().upper() for c in df.columns]
    return df

# 3. BARRA LATERAL (UPLOADS E FILTROS INICIAIS)
with st.sidebar:
    st.header("📂 Gestão de Dados")
    u_alunos = st.file_uploader("Substituir Alunos (CSV)", type="csv")
    u_gab = st.file_uploader("Substituir Gabarito (CSV)", type="csv")
    u_mapa = st.file_uploader("Substituir Mapeamento (Excel)", type=["xlsx"])
    
    st.divider()
    st.header("🎯 Filtros Globais")
    apenas_p360 = st.checkbox("Filtrar apenas IES P360", value=False)

# 4. CARREGAMENTO
df_alunos_raw = carregar_dados(u_alunos, "base_alunos.csv")
df_gab_raw = carregar_dados(u_gab, "base_gabarito.csv")
df_mapa_raw = carregar_dados(u_mapa, "base_mapeamento.xlsx", is_excel=True)

if df_alunos_raw is not None and df_gab_raw is not None and df_mapa_raw is not None:
    try:
        # --- PROCESSAMENTO INICIAL ---
        col_ies = [c for c in df_alunos_raw.columns if 'IES_NOME' in c or 'NO_IES' in c][0]
        col_cad = [c for c in df_alunos_raw.columns if 'CADERNO' in c][0]
        col_p360 = [c for c in df_alunos_raw.columns if 'P360' in c][0]

        # Melt Alunos e Gabarito (Lógica de 2 Cadernos)
        q_aluno = [c for c in df_alunos_raw.columns if 'DS_VT_ESC_OBJ' in c]
        df_long = df_alunos_raw.melt(id_vars=[col_ies, col_cad, col_p360], value_vars=q_aluno, var_name='Q', value_name='RESPOSTA')
        df_long['NU_QUESTAO'] = pd.to_numeric(df_long['Q'].str.extract(r'(\d+)')[0], errors='coerce')

        q_gab = [c for c in df_gab_raw.columns if 'DS_VT_GAB_OBJ' in c]
        df_gab_l = df_gab_raw.melt(id_vars=[col_cad], value_vars=q_gab, var_name='G', value_name='GABARITO')
        df_gab_l['NU_QUESTAO'] = pd.to_numeric(df_gab_l['G'].str.extract(r'(\d+)')[0], errors='coerce')

        # Limpeza e Merges
        df_long = df_long.dropna(subset=['NU_QUESTAO', col_cad])
        df_gab_l = df_gab_l.dropna(subset=['NU_QUESTAO', col_cad])
        df_mapa_raw['NU_QUESTAO'] = pd.to_numeric(df_mapa_raw['NU_QUESTAO'], errors='coerce')
        df_mapa_raw[col_cad] = pd.to_numeric(df_mapa_raw[col_cad], errors='coerce')
        df_mapa_raw = df_mapa_raw.dropna(subset=['NU_QUESTAO', col_cad])

        df = pd.merge(df_long, df_gab_l[[col_cad, 'NU_QUESTAO', 'GABARITO']], on=[col_cad, 'NU_QUESTAO'])
        df = pd.merge(df, df_mapa_raw, on=[col_cad, 'NU_QUESTAO'], how='left')
        
        # Padronização Pedagógica
        df['GRANDE_AREA'] = df['GRANDE_AREA'].fillna('NÃO MAPEADO').astype(str).str.upper()
        df['SUBESPECIALIDADE'] = df['SUBESPECIALIDADE'].fillna('GERAL').astype(str).str.upper()
        df['ACERTO'] = ((df['RESPOSTA'].astype(str).str.strip().str.upper() == df['GABARITO'].astype(str).str.strip().str.upper()) | 
                        (df['GABARITO'].astype(str).str.upper() == 'ANULADA')).astype(int)

        # --- APLICAÇÃO DOS FILTROS DINÂMICOS NA SIDEBAR ---
        with st.sidebar:
            st.divider()
            # Filtro por Cadernos (Multiselect)
            lista_cadernos = sorted(df[col_cad].unique())
            cadernos_sel = st.multiselect("Selecionar Cadernos", options=lista_cadernos, default=lista_cadernos)
            
            # Seleção da IES (Movida para a sidebar para facilitar)
            lista_ies = sorted(df[col_ies].unique())
            ies_sel = st.selectbox("Instituição para Diagnóstico", lista_ies)

        # APLICAÇÃO REAL DOS FILTROS NO DATAFRAME
        df_filtrado = df[df[col_cad].isin(cadernos_sel)]
        if apenas_p360:
            df_filtrado = df_filtrado[df_filtrado[col_p360].astype(str).str.upper().str.contains('S|Y|1|TRUE', na=False)]

        # --- DASHBOARD (Baseado no df_filtrado) ---
        m_ies = df_filtrado[df_filtrado[col_ies] == ies_sel]['ACERTO'].mean()
        m_nac = df_filtrado['ACERTO'].mean()
        
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Média IES (Cad: {cadernos_sel})", f"{m_ies:.1%}")
        c2.metric("Média Comparativa", f"{m_nac:.1%}")
        c3.metric("Diferença (pp)", f"{(m_ies - m_nac)*100:+.1f} pp")

        # TABELA DE GAPS
        st.header("🚩 Top 10 Lacunas Críticas (Geral)")
        res_nac = df_filtrado.groupby(['GRANDE_AREA', 'SUBESPECIALIDADE'])['ACERTO'].mean().reset_index(name='Nacional')
        res_ies = df_filtrado[df_filtrado[col_ies] == ies_sel].groupby(['GRANDE_AREA', 'SUBESPECIALIDADE'])['ACERTO'].mean().reset_index(name='IES')
        final_table = pd.merge(res_ies, res_nac, on=['GRANDE_AREA', 'SUBESPECIALIDADE'])
        final_table['Diferença'] = (final_table['IES'] - final_table['Nacional']) * 100
        
        st.table(final_table.sort_values('Diferença').head(10).style.format({
            'IES': '{:.1%}', 'Nacional': '{:.1%}', 'Diferença': '{:+.1f} pp'
        }))

        # MATRIZES DE PRIORIZAÇÃO
        st.header("🎯 Temas Prioritários por Área")
        df_peso = df_mapa_raw[df_mapa_raw[col_cad].isin(cadernos_sel)].groupby(['GRANDE_AREA', 'SUBESPECIALIDADE'])['NU_QUESTAO'].nunique().reset_index(name='Qtd')
        scatter_data = pd.merge(final_table, df_peso, on=['GRANDE_AREA', 'SUBESPECIALIDADE'])

        for area in sorted(scatter_data['GRANDE_AREA'].unique()):
            with st.expander(f"Área Médica: {area}", expanded=True):
                fig = px.scatter(scatter_data[scatter_data['GRANDE_AREA'] == area], 
                                 x='Qtd', y='Diferença', size='Qtd', color='Diferença',
                                 hover_name='SUBESPECIALIDADE', color_continuous_scale='RdYlGn', range_color=[-25, 25])
                fig.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.3)
                st.plotly_chart(fig, width='stretch')

        # EXPORTAÇÃO (Também respeita o filtro de caderno)
        st.divider()
        st.header("📥 Relatório Extraível")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            det_nac = df_filtrado.groupby(['CO_CADERNO', 'NU_QUESTAO', 'GRANDE_AREA', 'SUBESPECIALIDADE'])['ACERTO'].mean().reset_index(name='Brasil_%')
            det_ies = df_filtrado[df_filtrado[col_ies] == ies_sel].groupby(['CO_CADERNO', 'NU_QUESTAO'])['ACERTO'].mean().reset_index(name='IES_%')
            pd.merge(det_nac, det_ies, on=['CO_CADERNO', 'NU_QUESTAO']).to_excel(writer, index=False, sheet_name='Detalhamento_Questoes')
            scatter_data.to_excel(writer, index=False, sheet_name='Gaps_Especialidades')
        
        st.download_button("🚀 Baixar Relatório (Excel)", output.getvalue(), f"Relatorio_ENAMED_Cadernos_{cadernos_sel}.xlsx")

    except Exception as e:
        st.error(f"Erro no processamento: {e}")
