import streamlit as st
import pandas as pd
import plotly.express as px
import io
import os

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="ENAMED Analytics P360", layout="wide")

st.title("🩺 ENAMED: Inteligência de Dados By Paciente 360")
st.markdown("---")

# 2. FUNÇÃO RESILIENTE PARA CARREGAMENTO (CHUMBADO + UPLOAD)
def carregar_dados(uploaded_file, default_path, is_excel=False):
    """
    Tenta carregar o arquivo do upload. Se não houver, tenta o arquivo local (chumbado).
    """
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
        # Limpa linhas totalmente vazias
        df = df.dropna(how='all')
        # CORREÇÃO: Aplica upper nos nomes das colunas de forma segura
        df.columns = [str(c).strip().upper() for c in df.columns]
    return df

# 3. BARRA LATERAL (UPLOADS E FILTROS)
with st.sidebar:
    st.header("📂 Gestão de Dados")
    st.info("O sistema carrega a base padrão do GitHub. Use abaixo para substituir os dados.")
    
    u_alunos = st.file_uploader("Substituir Alunos (CSV)", type="csv")
    u_gab = st.file_uploader("Substituir Gabarito (CSV)", type="csv")
    u_mapa = st.file_uploader("Substituir Mapeamento (Excel)", type=["xlsx"])
    
    st.divider()
    st.header("🎯 Filtros")
    apenas_p360 = st.checkbox("Filtrar apenas IES P360", value=False)

# 4. EXECUÇÃO DO CARREGAMENTO
df_alunos_raw = carregar_dados(u_alunos, "base_alunos.csv")
df_gab_raw = carregar_dados(u_gab, "base_gabarito.csv")
df_mapa_raw = carregar_dados(u_mapa, "base_mapeamento.xlsx", is_excel=True)

if df_alunos_raw is not None and df_gab_raw is not None and df_mapa_raw is not None:
    try:
        with st.spinner('Sincronizando dados e especialidades...'):
            # Identificação das colunas principais
            col_ies = [c for c in df_alunos_raw.columns if 'IES_NOME' in c or 'NO_IES' in c][0]
            col_cad = [c for c in df_alunos_raw.columns if 'CADERNO' in c][0]
            col_p360 = [c for c in df_alunos_raw.columns if 'P360' in c][0]

            # --- MELT ALUNOS ---
            q_aluno = [c for c in df_alunos_raw.columns if 'DS_VT_ESC_OBJ' in c]
            df_long = df_alunos_raw.melt(id_vars=[col_ies, col_cad, col_p360], value_vars=q_aluno, var_name='Q', value_name='RESPOSTA')
            # Extração de número da questão (evita erro de NaN para Int)
            df_long['NU_QUESTAO'] = pd.to_numeric(df_long['Q'].str.extract(r'(\d+)')[0], errors='coerce')

            # --- MELT GABARITO ---
            q_gab = [c for c in df_gab_raw.columns if 'DS_VT_GAB_OBJ' in c]
            df_gab_l = df_gab_raw.melt(id_vars=[col_cad], value_vars=q_gab, var_name='G', value_name='GABARITO')
            df_gab_l['NU_QUESTAO'] = pd.to_numeric(df_gab_l['G'].str.extract(r'(\d+)')[0], errors='coerce')

            # --- LIMPEZA DE NULOS ANTES DA CONVERSÃO ---
            df_mapa_raw['NU_QUESTAO'] = pd.to_numeric(df_mapa_raw['NU_QUESTAO'], errors='coerce')
            df_mapa_raw[col_cad] = pd.to_numeric(df_mapa_raw[col_cad], errors='coerce')
            
            df_long = df_long.dropna(subset=['NU_QUESTAO', col_cad])
            df_gab_l = df_gab_l.dropna(subset=['NU_QUESTAO', col_cad])
            df_mapa_raw = df_mapa_raw.dropna(subset=['NU_QUESTAO', col_cad])

            # Conversão para Inteiro
            df_long[['NU_QUESTAO', col_cad]] = df_long[['NU_QUESTAO', col_cad]].astype(int)
            df_gab_l[['NU_QUESTAO', col_cad]] = df_gab_l[['NU_QUESTAO', col_cad]].astype(int)
            df_mapa_raw[['NU_QUESTAO', col_cad]] = df_mapa_raw[['NU_QUESTAO', col_cad]].astype(int)

            # --- CRUZAMENTO (MERGES) ---
            df = pd.merge(df_long, df_gab_l[[col_cad, 'NU_QUESTAO', 'GABARITO']], on=[col_cad, 'NU_QUESTAO'])
            df = pd.merge(df, df_mapa_raw, on=[col_cad, 'NU_QUESTAO'], how='left')
            
            # --- CÁLCULO DE ACERTO (CORREÇÃO .STR.UPPER) ---
            df['RESPOSTA'] = df['RESPOSTA'].astype(str).str.strip().str.upper()
            df['GABARITO'] = df['GABARITO'].astype(str).str.strip().str.upper()
            
            df['ACERTO'] = ((df['RESPOSTA'] == df['GABARITO']) | 
                            (df['GABARITO'] == 'ANULADA')).astype(int)

        # Filtro P360
        if apenas_p360:
            df = df[df[col_p360].astype(str).str.upper().str.contains('S|Y|1|TRUE', na=False)]

        # --- DASHBOARD ---
        ies_lista = sorted(df[col_ies].unique())
        ies_sel = st.selectbox("Selecione a Instituição para Diagnóstico:", ies_lista)

        # Métricas
        m_ies = df[df[col_ies] == ies_sel]['ACERTO'].mean()
        m_nac = df['ACERTO'].mean()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Média da IES", f"{m_ies:.1%}")
        c2.metric("Média Comparativa", f"{m_nac:.1%}")
        c3.metric("Diferença (Gap)", f"{m_ies - m_nac:+.1%}")

        # --- MATRIZES DE PRIORIZAÇÃO ---
        st.header("🎯 Temas Prioritários")
        
        # Agrupamento para os gráficos
        df_peso = df_mapa_raw.groupby(['GRANDE_AREA', 'SUBESPECIALIDADE'])['NU_QUESTAO'].nunique().reset_index(name='Qtd')
        res_nac = df.groupby(['GRANDE_AREA', 'SUBESPECIALIDADE'])['ACERTO'].mean().reset_index(name='Nac')
        res_ies = df[df[col_ies] == ies_sel].groupby(['GRANDE_AREA', 'SUBESPECIALIDADE'])['ACERTO'].mean().reset_index(name='IES')
        
        scatter_data = pd.merge(pd.merge(res_ies, res_nac, on=['GRANDE_AREA', 'SUBESPECIALIDADE']), df_peso, on=['GRANDE_AREA', 'SUBESPECIALIDADE'])
        scatter_data['Dif'] = (scatter_data['IES'] - scatter_data['Nac']) * 100

        for area in sorted(scatter_data['GRANDE_AREA'].unique()):
            with st.expander(f"Grande Área: {area}", expanded=True):
                fig = px.scatter(
                    scatter_data[scatter_data['GRANDE_AREA'] == area], 
                    x='Qtd', y='Dif', size='Qtd', color='Dif',
                    hover_name='SUBESPECIALIDADE', 
                    color_continuous_scale='RdYlGn', 
                    range_color=[-25, 25],
                    labels={'Qtd': 'Nº de Questões', 'Dif': 'Diferença (pp)'}
                )
                fig.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.3)
                st.plotly_chart(fig, use_container_width=True)

        # --- EXPORTAÇÃO ---
        st.divider()
        st.header("📥 Relatório para Download")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Planilha 1: Todas as questões detalhadas
            det_nac = df.groupby(['CO_CADERNO', 'NU_QUESTAO', 'GRANDE_AREA', 'SUBESPECIALIDADE'])['ACERTO'].mean().reset_index(name='Brasil_%')
            det_ies = df[df[col_ies] == ies_sel].groupby(['CO_CADERNO', 'NU_QUESTAO'])['ACERTO'].mean().reset_index(name='IES_%')
            pd.merge(det_nac, det_ies, on=['CO_CADERNO', 'NU_QUESTAO']).to_excel(writer, index=False, sheet_name='Geral_Questoes')
            # Planilha 2: Resumo de Especialidades
            scatter_data.to_excel(writer, index=False, sheet_name='Resumo_Especialidades')
        
        st.download_button(
            label="🚀 Baixar Relatório Completo (Excel)",
            data=output.getvalue(),
            file_name=f"Relatorio_ENAMED_{ies_sel}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"Ocorreu um erro no processamento: {e}")
else:
    st.warning("Aguardando bases de dados. Certifique-se de que os arquivos 'base_alunos.csv', 'base_gabarito.csv' e 'base_mapeamento.xlsx' estão na mesma pasta do código.")
