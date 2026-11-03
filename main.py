import streamlit as st
from PIL import Image
from views import visualizacao_obstacles

# =============================================================================
# CONFIGURAÇÃO DA PÁGINA
# =============================================================================
# Carrega o ícone da aba do navegador
icon = Image.open("assets/icone_omnifisio.png")

st.set_page_config(
    page_title="OmniFisio",
    page_icon=icon,
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# CABEÇALHO
# =============================================================================
def _logo_do_tema() -> str:
    """Logo para o tema ativo (claro ou escuro). Se o tema não puder ser detectado, usa a escura."""
    try:
        tipo = st.context.theme.type
    except Exception:
        tipo = None
    return ("assets/omnifisio_logo_claro.png" if tipo == "light"
            else "assets/omnifisio_logo_escuro.png")


st.image(_logo_do_tema(), width=300)

# =============================================================================
# NAVEGAÇÃO POR ABAS
# =============================================================================
abas = st.tabs([
    "🏠 Início",
    "🦵 Membros Inferiores",
])

# -----------------------------------------------------------------------
# ABA 1 — Início
# -----------------------------------------------------------------------
with abas[0]:
    st.markdown(
        "Este sistema traduz dados cinemáticos brutos capturados por visão "
        "computacional em indicadores objetivos do **progresso terapêutico**, auxiliando na tomada de decisão clínica."
    )
    st.markdown(
        """
        ### 📋 Como usar

        1. Acesse a aba correspondente ao tipo de análise desejada.
        2. Configure os **parâmetros clínicos** na barra lateral (limiares de ângulo,
           modo de análise).
        3. Faça o upload do(s) arquivo(s) exportados do software
           nos formatos **.CSV**, **.XLSX** ou **.XLSM**.
        4. Os resultados são gerados automaticamente.

        ---

        ### 📌 Abas disponíveis

        | Aba | Descrição |
        |---|---|
        | 🦵 Membros Inferiores | Análise da marcha estacionária: flexão de joelho (amplitude e picos), evolução entre sessões e compensação dos ombros |

        ---

        ### ⚠️ Atenção
        Este dashboard é uma ferramenta de **suporte à decisão** e não substitui
        a avaliação do profissional de saúde.
        """
    )

# -----------------------------------------------------------------------
# ABA 2 — Membros Inferiores (Obstacles) — foco do TCC
# -----------------------------------------------------------------------
with abas[1]:
    visualizacao_obstacles.carregar()