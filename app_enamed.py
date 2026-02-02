import streamlit as st
import pandas as pd
import plotly.express as px
import io
import os

# 1. CONFIGURAÇÃO
st.set_page_config(page_title="ENAMED Analytics P360", layout="wide")
st.title("🩺 ENAMED: Inteligência de Dados By Paciente 360")
st.markdown("---")

# 2. VACINA DE RAM (CACHE)
@st.cache_data(show_spinner="Carregando base de dados...")
def carregar_dados(uploaded_file, default_path, is_excel=False):
    df = None
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file) if is_excel else pd.read_csv(uploaded_file, sep=None, engine='python', encoding='utf-8-sig')
    elif os.path.exists(default_path):
        df = pd.read_excel(default_path) if is_excel else pd.read_csv(default_path, sep=None, engine='python', encoding='utf-8-sig')
    
    if df is not None:
        df = df.dropna(how='all')
        df.columns = [str(c).strip().upper() for c in df.columns]
    return df

# 3. BARRA LATERAL (UPLOADS E CADERNOS)
with st.sidebar:
    st.header("📂 Gestão de Dados")
    u_alunos = st.file_uploader("Trocar Alunos (CSV)", type="csv")
    u_gab = st.file_uploader("Trocar Gabarito (CSV)", type="csv")
    u_mapa = st.file_uploader("Trocar Mapeamento (Excel)", type=["xlsx"])
    
    st.divider()
    st.header("🎯 Filtros")
    apenas_p360 = st.checkbox("Filtrar apenas IES P360", value=False)

# 4. CARREGAMENTO E PROCESSAMENTO
df_alunos_raw = carregar_dados(u_alunos, "base_alunos.csv")
df_gab_raw = carregar_dados(u_gab, "base_gabarito.csv")
df_mapa_raw = carregar_dados(u_mapa, "base_mapeamento.xlsx", is_excel=True)

if df_alunos_raw is not None and df_gab_raw is not None and df_mapa_raw is not None:
    try:
        # Identificação de colunas
        col_ies = [c for c in df_alunos_raw.columns if 'IES_NOME' in c or 'NO_IES' in c][0]
        col_cad = [c for c in df_alunos_raw.columns if 'CADERNO' in c][0]
        col_p360 = [c for c in df_alunos_raw.columns if 'P360' in c][0]

        # Melt Alunos
        q_aluno = [c for c in df_alunos_raw.columns if 'DS_VT_ESC_OBJ' in c]
        df_long = df_alunos_raw.melt(id_vars=[col_ies, col_cad, col_p360], value_vars=q_aluno, var_name='Q', value_name='RESPOSTA')
        df_long['NU_QUESTAO'] = pd.to_numeric(df_long['Q'].str.extract(r'(\d+)')[0], errors='coerce')

        # Melt Gabarito
        q_gab = [c for c in df_gab_raw.columns if 'DS_VT_GAB_OBJ' in c]
        df_gab_l = df_gab_raw.melt(id_vars=[col_cad], value_vars=q_gab, var_name='G', value_name='GABARITO')
        df_gab_l['NU_QUESTAO'] = pd.to_numeric(df_gab_l['G'].str.extract(r'(\d+)')[0], errors='coerce')

        # Sincronização de Tipos
        df_mapa_raw['NU_QUESTAO'] = pd.to_numeric(df_mapa_raw['NU_QUESTAO'], errors='coerce')
        df_mapa_raw[col_cad] = pd.to_numeric(df_mapa_raw[col_cad], errors='coerce')
        
        # Merge Principal
        df = pd.merge(df_long.dropna(subset=['NU_QUESTAO', col_cad]), 
                      df_gab_l.dropna(subset=['NU_QUESTAO', col_cad]), on=[col_cad, 'NU_QUESTAO'])
        df = pd.merge(df, df_mapa_raw.dropna(subset=['NU_QUESTAO', col_cad]), on=[col_cad, 'NU_QUESTAO'], how='left')

        # Limpeza Pedagógica
        df['GRANDE_AREA'] = df['GRANDE_AREA'].fillna('NÃO MAPEADO').astype(str).str.upper()
        df['SUBESPECIALIDADE'] = df['SUBESPECIALIDADE'].fillna('GERAL').astype(str).str.upper()
        df['ACERTO'] = ((df['RESPOSTA'].astype(str).str.strip().str.upper() == df['GABARITO'].astype(str).str.strip().str.upper()) | 
                        (df['GABARITO'].astype(str).str.upper() == 'ANULADA')).astype(int)

        # --- INTERFACE ÁREA PRINCIPAL ---
        c_filt1, c_filt2 = st.columns([2, 1])
        with c_filt1:
            ies_sel = st.selectbox("🏥 Selecione a Instituição para Diagnóstico:", sorted(df[col_ies].unique()))
        with c_filt2:
            lista_cadernos = sorted(df[col_cad].unique())
            cadernos_sel = st.multiselect("📚 Cadernos:", options=lista_cadernos, default=lista_cadernos)

        # Aplicação dos Filtros
        df_f = df[(df[col_ies] == ies_sel) & (df[col_cad].isin(cadernos_sel))]
        df_nac = df[df[col_cad].isin(cadernos_sel)]
        if apenas_p360:
            df_nac = df_nac[df_nac[col_p360].astype(str).str.upper().str.contains('S|Y|1|TRUE', na=False)]

        # Métricas
        m_ies = df_f['ACERTO'].mean()
        m_comp = df_nac['ACERTO'].mean()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Média da IES", f"{m_ies:.1%}")
        m2.metric("Média Nacional/Filtro", f"{m_comp:.1%}")
        m3.metric("Diferença (Gap)", f"{(m_ies - m_comp)*100:+.1f} pp")

        # --- TABELA DE GAPS ---
        st.header("🚩 Top 10 Lacunas Críticas (Geral)")
        res_ies = df_f.groupby(['GRANDE_AREA', 'SUBESPECIALIDADE'])['ACERTO'].mean().reset_index(name='IES')
        res_nac = df_nac.groupby(['GRANDE_AREA', 'SUBESPECIALIDADE'])['ACERTO'].mean().reset_index(name='Nacional')
        
        scatter_data = pd.merge(res_ies, res_nac, on=['GRANDE_AREA', 'SUBESPECIALIDADE'])
        scatter_data['Diferença'] = (scatter_data['IES'] - scatter_data['Nacional']) * 100
        
        # Adicionar o Peso (Qtd de questões) para o gráfico
        df_peso = df_mapa_raw[df_mapa_raw[col_cad].isin(cadernos_sel)].groupby(['GRANDE_AREA', 'SUBESPECIALIDADE'])['NU_QUESTAO'].nunique().reset_index(name='Qtd')
        scatter_data = pd.merge(scatter_data, df_peso, on=['GRANDE_AREA', 'SUBESPECIALIDADE'], how='left').fillna(0)

        st.table(scatter_data.sort_values('Diferença').head(10).style.format({
            'IES': '{:.1%}', 'Nacional': '{:.1%}', 'Diferença': '{:+.1f} pp'
        }))

        # --- SCATTER PLOTS ---
        st.header("🎯 Temas Prioritários por Área")
        for area in sorted(scatter_data['GRANDE_AREA'].unique()):
            if area != 'NÃO MAPEADO':
                with st.expander(f"Grande Área: {area}", expanded=True):
                    fig = px.scatter(
                        scatter_data[scatter_data['GRANDE_AREA'] == area], 
                        x='Qtd', y='Diferença', size='Qtd', color='Diferença',
                        hover_name='SUBESPECIALIDADE', color_continuous_scale='RdYlGn', range_color=[-25, 25],
                        labels={'Qtd': 'Nº de Questões', 'Diferença': 'Diferença (pp)'}
                    )
                    fig.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.3)
                    st.plotly_chart(fig, width='stretch')

        # --- EXPORTAÇÃO ---
        st.divider()
        st.header("📥 Relatório Extraível")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            scatter_data.to_excel(writer, index=False, sheet_name='Gaps_Especialidades')
        st.download_button("🚀 Baixar Relatório Completo (Excel)", output.getvalue(), f"ENAMED_{ies_sel}.xlsx")

    except Exception as e:
        st.error(f"Erro no processamento: {e}")
else:
    st.warning("Aguardando bases de dados (base_alunos.csv, base_gabarito.csv, base_mapeamento.xlsx).")
