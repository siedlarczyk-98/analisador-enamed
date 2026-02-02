import streamlit as st
import pandas as pd
import plotly.express as px
import io
import os

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="ENAMED Analytics Pro", layout="wide")

st.title("🩺 ENAMED: Inteligência Pedagógica Médica")
st.markdown("---")

# 2. FUNÇÃO PARA CARREGAMENTO HÍBRIDO (CHUMBADO + UPLOAD)
def carregar_recurso(uploaded_file, default_path, is_excel=False):
    if uploaded_file is not None:
        if is_excel:
            return pd.read_excel(uploaded_file).dropna(how='all')
        return pd.read_csv(uploaded_file, sep=None, engine='python', encoding='utf-8-sig').dropna(how='all')
    
    if os.path.exists(default_path):
        if is_excel:
            return pd.read_excel(default_path).dropna(how='all')
        return pd.read_csv(default_path, sep=None, engine='python', encoding='utf-8-sig').dropna(how='all')
    
    return None

# 3. BARRA LATERAL (UPLOADS E FILTROS)
with st.sidebar:
    st.header("📂 Gestão de Dados")
    st.info("O sistema carrega a base padrão automaticamente. Use os campos abaixo apenas se desejar trocar os dados.")
    
    u_alunos = st.file_uploader("Substituir Alunos (CSV)", type="csv")
    u_gab = st.file_uploader("Substituir Gabarito (CSV)", type="csv")
    u_mapa = st.file_uploader("Substituir Mapeamento (Excel)", type=["xlsx"])
    
    st.divider()
    st.header("🎯 Filtros")
    apenas_p360 = st.checkbox("Filtrar apenas IES P360", value=False)

# 4. CARREGAMENTO DOS DADOS
df_alunos_raw = carregar_recurso(u_alunos, "base_alunos.csv")
df_gab_raw = carregar_recurso(u_gab, "base_gabarito.csv")
df_mapa_raw = carregar_recurso(u_mapa, "base_mapeamento.xlsx", is_excel=True)

if df_alunos_raw is not None and df_gab_raw is not None and df_mapa_raw is not None:
    try:
        # --- LIMPEZA E PADRONIZAÇÃO ---
        for d in [df_alunos_raw, df_gab_raw, df_mapa_raw]:
            d.columns = d.columns.str.strip().str.upper()

        with st.spinner('Sincronizando cadernos e áreas...'):
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

            # Tratamento de NaNs (Vacina contra erros de integer)
            df_mapa_raw['NU_QUESTAO'] = pd.to_numeric(df_mapa_raw['NU_QUESTAO'], errors='coerce')
            df_mapa_raw[col_cad] = pd.to_numeric(df_mapa_raw[col_cad], errors='coerce')
            
            df_long = df_long.dropna(subset=['NU_QUESTAO', col_cad])
            df_gab_l = df_gab_l.dropna(subset=['NU_QUESTAO', col_cad])
            df_mapa_raw = df_mapa_raw.dropna(subset=['NU_QUESTAO', col_cad])

            # Conversão Segura
            df_long[['NU_QUESTAO', col_cad]] = df_long[['NU_QUESTAO', col_cad]].astype(int)
            df_gab_l[['NU_QUESTAO', col_cad]] = df_gab_l[['NU_QUESTAO', col_cad]].astype(int)
            df_mapa_raw[['NU_QUESTAO', col_cad]] = df_mapa_raw[['NU_QUESTAO', col_cad]].astype(int)

            # --- MERGES ---
            df = pd.merge(df_long, df_gab_l[[col_cad, 'NU_QUESTAO', 'GABARITO']], on=[col_cad, 'NU_QUESTAO'])
            df = pd.merge(df, df_mapa_raw, on=[col_cad, 'NU_QUESTAO'], how='left')
            
            # Acerto
            df['ACERTO'] = ((df['RESPOSTA'].astype(str).str.strip().upper() == df['GABARITO'].astype(str).str.strip().upper()) | 
                            (df['GABARITO'].astype(str).str.upper() == 'ANULADA')).astype(int)

        if apenas_p360:
            df = df[df[col_p360].astype(str).str.upper().str.contains('S|Y|1|TRUE', na=False)]

        # --- INTERFACE ---
        ies_sel = st.selectbox("Selecione a Instituição:", sorted(df[col_ies].unique()))

        # Cálculo de Médias
        df_peso = df_mapa_raw.groupby(['GRANDE_AREA', 'SUBESPECIALIDADE'])['NU_QUESTAO'].nunique().reset_index(name='Qtd')
        res_nac = df.groupby(['GRANDE_AREA', 'SUBESPECIALIDADE'])['ACERTO'].mean().reset_index(name='Nac')
        res_ies = df[df[col_ies] == ies_sel].groupby(['GRANDE_AREA', 'SUBESPECIALIDADE'])['ACERTO'].mean().reset_index(name='IES')
        
        scatter_data = pd.merge(pd.merge(res_ies, res_nac, on=['GRANDE_AREA', 'SUBESPECIALIDADE']), df_peso, on=['GRANDE_AREA', 'SUBESPECIALIDADE'])
        scatter_data['Dif'] = (scatter_data['IES'] - scatter_data['Nac']) * 100

        # Métrica Principal
        m_ies = df[df[col_ies] == ies_sel]['ACERTO'].mean()
        m_nac = df['ACERTO'].mean()
        st.metric("Desempenho Geral da IES", f"{m_ies:.1%}", f"{m_ies - m_nac:+.1%}")

        # GRÁFICOS POR ÁREA
        st.header("🎯 Matrizes de Priorização")
        for area in sorted(scatter_data['GRANDE_AREA'].unique()):
            with st.expander(f"Grande Área: {area}"):
                fig = px.scatter(scatter_data[scatter_data['GRANDE_AREA'] == area], x='Qtd', y='Dif', size='Qtd', color='Dif',
                                 hover_name='SUBESPECIALIDADE', color_continuous_scale='RdYlGn', range_color=[-25, 25])
                fig.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.3)
                st.plotly_chart(fig, use_container_width=True)

        # EXPORTAÇÃO EXCEL
        st.divider()
        det_nac = df.groupby(['CO_CADERNO', 'NU_QUESTAO', 'GRANDE_AREA', 'SUBESPECIALIDADE'])['ACERTO'].mean().reset_index(name='Brasil_%')
        det_ies = df[df[col_ies] == ies_sel].groupby(['CO_CADERNO', 'NU_QUESTAO'])['ACERTO'].mean().reset_index(name='IES_%')
        df_excel = pd.merge(det_nac, det_ies, on=['CO_CADERNO', 'NU_QUESTAO']).sort_values(['CO_CADERNO', 'NU_QUESTAO'])
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_excel.to_excel(writer, index=False, sheet_name='Geral_Questoes')
            scatter_data.to_excel(writer, index=False, sheet_name='Por_Especialidade')
        
        st.download_button("🚀 Baixar Relatório Full (Excel)", output.getvalue(), f"ENAMED_{ies_sel}.xlsx")

    except Exception as e:
        st.error(f"Erro no processamento: {e}")
else:
    st.warning("⚠️ Bases não encontradas. Certifique-se de que os arquivos base_alunos.csv, base_gabarito.csv e base_mapeamento.xlsx estão no repositório.")
