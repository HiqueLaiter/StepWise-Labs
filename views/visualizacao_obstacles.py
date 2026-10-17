import math

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils.processamento import (
    carregar_arquivo,
    calcular_fps,
    gerar_resumo_sessao,
    picos_para_dataframe,
    tem_ombros,
    construir_relatorio,
    construir_relatorio_comparacao,
    tabela_resumo_lados,
    tabela_ombros,
    tabela_comparativa,
    relatorio_para_json,
    relatorio_para_excel,
    COL_JOELHO_ESQ, COL_JOELHO_DIR,
    COL_OMBRO_ESQ,  COL_OMBRO_DIR,
    COL_TEMPO,
)

COR_ESQ = '#3A86FF'
COR_DIR = '#FB5607'

MODO_UNICA_BI  = "Sessão única — Bilateral"
MODO_UNICA_UNI = "Sessão única — Unilateral"
MODO_COMP_BI   = "Comparação (Início vs Final) — Bilateral"
MODO_COMP_UNI  = "Comparação (Início vs Final) — Unilateral"

NOME_LADO = {'joelho_esq': 'Esquerdo', 'joelho_dir': 'Direito'}


# =============================================================================
# ABA DE DESCRIÇÃO DAS MÉTRICAS
# =============================================================================

def _aba_metricas_info():
    """Explica ao fisioterapeuta cada métrica, sua relevância e interpretação."""
    st.markdown("## 📖 Guia das métricas")
    st.markdown(
        "Esta seção explica cada indicador calculado pelo dashboard, "
        "para que o profissional de saúde possa interpretar os resultados com segurança."
    )

    with st.expander("🧬 O que são Métricas Biomecânicas?", expanded=True):
        st.markdown(
            """
            **Métricas biomecânicas** são indicadores numéricos extraídos do movimento do paciente
            que permitem avaliar a **qualidade e eficiência** da marcha de forma objetiva.

            Na prática clínica tradicional, a avaliação do movimento depende da observação visual
            do terapeuta — subjetiva e variável entre profissionais. As métricas transformam esse
            julgamento em **dados mensuráveis e reproduzíveis**, facilitando o acompanhamento da
            evolução e a comunicação entre a equipe de saúde.

            O foco analítico é a **flexão do joelho**. O dashboard calcula amplitude de movimento,
            simetria bilateral, suavidade motora (Jerk) e consistência temporal, além de exibir a
            oscilação dos ombros como indicador de compensação postural.
            """
        )

    with st.expander("⏱️ Tempo de execução da sessão", expanded=False):
        st.markdown(
            """
            **O que é:** a duração total da sessão (em segundos).

            **Por que importa:** referência rápida para comparar o tempo gasto entre sessões.
            Junto com o número de picos, ajuda a diferenciar poucos movimentos rápidos de
            movimentos com mais pausas ou lentidão (fadiga, dor, condicionamento motor).
            """
        )

    with st.expander("📏 Amplitude de movimento (média e máxima)", expanded=False):
        st.markdown(
            """
            **O que é:** resume o ângulo de flexão do joelho durante **toda a sessão**:

            - **Amplitude máxima:** maior ângulo atingido em qualquer instante.
            - **Amplitude média:** ângulo médio ao longo da sessão.

            **Por que importa:** indicador rápido de capacidade articular, mesmo quando poucos
            picos são detectados.
            """
        )

    with st.expander("⚖️ Índice de Simetria de Robinson (SI)", expanded=False):
        st.markdown(
            """
            **O que é:** compara a amplitude média dos picos de flexão do joelho dos dois lados:

            $$SI = \\frac{2 \\cdot |X_{dir} - X_{esq}|}{X_{dir} + X_{esq}} \\times 100\\%$$

            onde $X$ é a amplitude média dos picos de flexão do joelho.

            **Como interpretar:** **0% = simetria perfeita**; quanto maior o valor, maior a
            assimetria entre os membros. A fórmula é simétrica por construção, portanto **não
            indica qual lado** é menos ativo — consulte as amplitudes de cada lado para isso.
            Não é calculado se algum lado não tiver picos detectados.
            """
        )

    with st.expander("〰️ Suavidade motora — Jerk RMS", expanded=False):
        st.markdown(
            """
            **O que é:** raiz da média dos quadrados da **terceira derivada** do ângulo do joelho
            em relação ao tempo (graus/s³). Valores **menores** indicam movimento mais suave.

            **Cuidados metodológicos aplicados:**
            - A terceira derivada amplifica ruído, então o cálculo ocorre **apenas após** filtro
              passa-baixa antirruído e **normalização temporal** (reamostragem para taxa comum,
              tornando comparáveis KinesiOS e Brainn_XR);
            - O RMS considera **somente as janelas dos picos de movimento ativo**, ignorando os
              repousos entre repetições, que diluiriam a medida.
            """
        )

    with st.expander("🕐 Consistência temporal", expanded=False):
        st.markdown(
            """
            **O que é:** o **Coeficiente de Variação (CV%)** das durações dos picos
            (desvio padrão ÷ média × 100).

            | CV% | Interpretação |
            |---|---|
            | < 15% | Ritmo muito consistente — boa regularidade motora |
            | 15% a 30% | Variabilidade moderada — aceitável em reabilitação |
            | > 30% | **Alta irregularidade** — pode indicar fadiga, dor ou déficit de controle motor |
            """
        )

    with st.expander("📌 Picos de flexão detectados", expanded=False):
        st.markdown(
            """
            Cada "pico" é um intervalo em que o ângulo do joelho ultrapassou o **limiar clínico**
            definido na barra lateral.

            | Campo | Descrição |
            |---|---|
            | Amplitude (°) | Maior ângulo atingido durante o movimento |
            | Tempo do pico (s) | Instante em que a amplitude máxima ocorreu |
            | Duração (s) | Tempo acima do limiar |
            | Início (s) / Fim (s) | Momentos em que o movimento cruzou o limiar |

            Eventos com menos de 5 frames contínuos são ignorados (filtro anti-ruído).
            """
        )

    with st.expander("🙆 Compensação postural / oscilação dos ombros", expanded=False):
        st.markdown(
            """
            Mostra a série temporal dos ombros durante o exercício. Elevação ou oscilação
            excessiva, ou diferença marcante entre os lados, pode indicar **compensação postural**
            para executar a flexão do joelho. Disponível quando o arquivo contém os dados dos ombros.
            """
        )


# =============================================================================
# HELPERS
# =============================================================================

def _tempo_eixo(df: pd.DataFrame, fps: float) -> np.ndarray:
    """Retorna o eixo de tempo já calculado e validado no processamento."""
    return df[COL_TEMPO].values


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _num(x, casas: int = 1) -> str:
    """Valor numérico puro (sem unidade); '—' quando indefinido."""
    return "—" if _nan(x) else f"{x:.{casas}f}"


# =============================================================================
# GRÁFICOS
# =============================================================================

def _adicionar_picos(fig, tempo, picos, cor, **pos):
    for p in picos:
        fig.add_vrect(x0=p['inicio_seg'], x1=p['fim_seg'], fillcolor=cor,
                      opacity=0.15, layer="below", line_width=0, **pos)
        fig.add_trace(go.Scatter(
            x=[tempo[p['frame_pico']]], y=[p['amplitude_maxima']],
            mode='markers+text',
            marker=dict(color=cor, size=8, symbol='circle'),
            text=[f"P{p['pico']}<br>{p['amplitude_maxima']:.1f}°"],
            textposition='top center', textfont=dict(size=9), showlegend=False,
        ), **pos)


def _plot_sinal_com_picos(tempo, sinal_esq, sinal_dir, picos_esq, picos_dir,
                          limiar, titulo, unidade="graus") -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        subplot_titles=("Esquerdo", "Direito"), vertical_spacing=0.12)
    for row, sinal, picos, cor in [(1, sinal_esq, picos_esq, COR_ESQ),
                                   (2, sinal_dir, picos_dir, COR_DIR)]:
        nome = "Esquerdo" if row == 1 else "Direito"
        fig.add_trace(go.Scatter(x=tempo, y=sinal, mode='lines', name=nome,
                                 line=dict(color=cor, width=1.5)), row=row, col=1)
        fig.add_hline(y=limiar, line_dash="dash", line_color="#FF006E",
                      annotation_text=f"Limiar ({limiar}°)",
                      annotation_position="top right", row=row, col=1)
        _adicionar_picos(fig, tempo, picos, cor, row=row, col=1)
        fig.update_yaxes(title_text=unidade, row=row, col=1)

    fig.update_xaxes(title_text="Tempo (s)", row=2, col=1)
    fig.update_layout(title=titulo, height=520, legend=dict(orientation="h", y=-0.15),
                      margin=dict(t=60, b=20))
    return fig


def _plot_sinal_unilateral(tempo, sinal, picos, limiar, titulo, cor, lado) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=tempo, y=sinal, mode='lines', name=lado,
                             line=dict(color=cor, width=1.5)))
    fig.add_hline(y=limiar, line_dash="dash", line_color="#FF006E",
                  annotation_text=f"Limiar ({limiar}°)", annotation_position="top right")
    _adicionar_picos(fig, tempo, picos, cor)
    fig.update_layout(title=titulo, xaxis_title="Tempo (s)", yaxis_title="graus",
                      height=350, margin=dict(t=50, b=20))
    return fig


def _plot_overview_bilateral(tempo, df, titulo) -> go.Figure:
    """Overview dos dois joelhos para o terapeuta identificar o lado ativo."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=tempo, y=df[COL_JOELHO_ESQ], mode='lines', name='Esquerdo',
                             line=dict(color=COR_ESQ, width=1.2)))
    fig.add_trace(go.Scatter(x=tempo, y=df[COL_JOELHO_DIR], mode='lines', name='Direito',
                             line=dict(color=COR_DIR, width=1.2)))
    fig.update_layout(title=titulo, xaxis_title="Tempo (s)", yaxis_title="graus",
                      height=260, legend=dict(orientation="h", y=-0.4),
                      margin=dict(t=40, b=10))
    return fig


def _plot_ombros(tempo, df) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=tempo, y=df[COL_OMBRO_ESQ], mode='lines', name='Ombro esquerdo',
                             line=dict(color=COR_ESQ, width=1.3)))
    fig.add_trace(go.Scatter(x=tempo, y=df[COL_OMBRO_DIR], mode='lines', name='Ombro direito',
                             line=dict(color=COR_DIR, width=1.3)))
    fig.update_layout(title="Oscilação dos ombros ao longo da sessão",
                      xaxis_title="Tempo (s)", yaxis_title="graus", height=320,
                      legend=dict(orientation="h", y=-0.3), margin=dict(t=50, b=10))
    return fig


def _plot_comparacao_amplitudes(picos_a, picos_b, label_a, label_b, titulo) -> go.Figure:
    fig = go.Figure()
    if picos_a:
        fig.add_trace(go.Bar(x=[f"P{p['pico']}" for p in picos_a],
                             y=[p['amplitude_maxima'] for p in picos_a],
                             name=label_a, marker_color=COR_ESQ))
    if picos_b:
        fig.add_trace(go.Bar(x=[f"P{p['pico']}" for p in picos_b],
                             y=[p['amplitude_maxima'] for p in picos_b],
                             name=label_b, marker_color='#FF006E'))
    fig.update_layout(title=titulo, xaxis_title="Pico", yaxis_title="Amplitude máxima (graus)",
                      barmode='group', height=350, legend=dict(orientation="h", y=-0.3),
                      margin=dict(t=50, b=10))
    return fig


def _mostrar_tabela(df: pd.DataFrame):
    """
    Exibe uma tabela só com números (copiar/colar no Excel).
    Usa st.dataframe; se o pyarrow estiver indisponível ou bloqueado pelo sistema
    (ImportError/OSError ao carregar a DLL), cai para uma tabela HTML equivalente,
    que não depende do pyarrow e também cola corretamente no Excel.
    """
    try:
        st.dataframe(df, use_container_width=True)
    except (ImportError, OSError):
        html = df.to_html(na_rep="", border=0, justify="left")
        st.markdown(
            "<style>.sw-tabela table{border-collapse:collapse;width:100%;font-size:0.9rem}"
            ".sw-tabela th,.sw-tabela td{border:1px solid rgba(128,128,128,.35);padding:4px 10px;text-align:right}"
            ".sw-tabela th{background:rgba(128,128,128,.15);font-weight:600}"
            ".sw-tabela td:first-child,.sw-tabela th:first-child{text-align:left}</style>"
            f"<div class='sw-tabela' style='overflow-x:auto'>{html}</div>",
            unsafe_allow_html=True,
        )


# =============================================================================
# TABELAS (somente números nas células — unidades ficam nos cabeçalhos)
# =============================================================================

def _tabela_picos(picos: list[dict], fps: float):
    df = picos_para_dataframe(picos)
    if df.empty:
        st.info("Nenhum pico detectado com o limiar definido.")
        return
    df = df.copy()
    df['tempo_pico'] = df['frame_pico'] / fps
    tabela = df[['amplitude_maxima', 'tempo_pico', 'duracao', 'inicio_seg', 'fim_seg']].rename(columns={
        'amplitude_maxima': 'Amplitude (°)',
        'tempo_pico':       'Tempo do pico (s)',
        'duracao':          'Duração (s)',
        'inicio_seg':       'Início (s)',
        'fim_seg':          'Fim (s)',
    }).round(2)
    _mostrar_tabela(tabela)


def _tabela_resumo_lados(resumo: dict, chaves: list[str]):
    """Tabela de métricas por lado (mesma do arquivo exportado), pronta para copiar/colar no Excel."""
    _mostrar_tabela(tabela_resumo_lados(resumo, chaves))


def _tabela_comparativa(res_i: dict, res_f: dict, chaves: list[str]):
    """Tabela Início × Final com valores numéricos puros (mesma do arquivo exportado)."""
    _mostrar_tabela(tabela_comparativa(res_i, res_f, chaves))


# =============================================================================
# SEÇÕES REUTILIZÁVEIS
# =============================================================================

def _secao_metricas(resumo: dict, chaves: list[str], label: str = ""):
    """Métricas de uma sessão para um ou dois lados (bilateral = 2 chaves)."""
    prefixo = f"{label} — " if label else ""
    sufixo = "" if len(chaves) == 2 else f" — {NOME_LADO[chaves[0]]}"
    st.markdown(f"#### {prefixo}Métricas Biomecânicas{sufixo}")
    st.caption("Consulte a aba **📖 Guia de métricas** para a explicação de cada indicador.")

    st.metric("Duração total (s)", _num(resumo['tempo_execucao_seg']))

    st.markdown("**Amplitude de Movimento do Joelho** *(toda a sessão)*")
    cols = st.columns(len(chaves))
    for col, k in zip(cols, chaves):
        col.metric(f"Joelho {NOME_LADO[k]} — Máx. (°)", _num(resumo['amplitude'][k]['maxima']))
        col.metric(f"Joelho {NOME_LADO[k]} — Média (°)", _num(resumo['amplitude'][k]['media']))

    if len(chaves) == 2:
        st.markdown("**Simetria e Suavidade**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Índice de Simetria de Robinson (%)", _num(resumo['simetria']['si_pct']),
                  help="0 = simetria perfeita. Calculado sobre a amplitude média dos picos de flexão.")
        c2.metric("Jerk RMS Joelho Esq. (°/s³)", _num(resumo['jerk']['joelho_esq']['rms'], 0),
                  help="Calculado após filtragem e normalização temporal, apenas nos picos.")
        c3.metric("Jerk RMS Joelho Dir. (°/s³)", _num(resumo['jerk']['joelho_dir']['rms'], 0))
    else:
        st.markdown("**Suavidade**")
        k = chaves[0]
        st.metric(f"Jerk RMS Joelho {NOME_LADO[k]} (°/s³)", _num(resumo['jerk'][k]['rms'], 0),
                  help="Calculado após filtragem e normalização temporal, apenas nos picos.")

    st.markdown("**Consistência Temporal** *(CV% das durações — quanto menor, mais regular)*")
    cols = st.columns(len(chaves))
    for col, k in zip(cols, chaves):
        cons = resumo['consistencia'][k]
        col.metric(f"Joelho {NOME_LADO[k]} — CV (%)", _num(cons['cv_duracao']),
                   help=(f"{cons['n_picos']} picos detectados\n"
                         f"Média: {cons['media_duracao']:.2f} s ± {cons['desvio_duracao']:.2f} s"))

    st.markdown("**Resumo por lado** *(valores numéricos puros — selecione e copie para o Excel)*")
    _tabela_resumo_lados(resumo, chaves)


def _expander_ombros(df, tempo, resumo, key: str):
    """Seção retrátil com a oscilação dos ombros (compensação postural)."""
    with st.expander("Compensação Postural / Oscilação dos Ombros", expanded=False):
        if not tem_ombros(df):
            st.info("Os dados de ombro não foram encontrados neste arquivo.")
            return
        st.caption("Elevação ou oscilação excessiva ao longo do exercício pode indicar "
                   "compensação postural.")
        st.plotly_chart(_plot_ombros(tempo, df), use_container_width=True, key=f"ombros_{key}")
        _mostrar_tabela(tabela_ombros(resumo))


def _bloco_exportacao(resumo: dict, modo: str, lado: str | None, key: str):
    """Botões de download do relatório estruturado (JSON e Excel)."""
    st.markdown("#### 💾 Exportar dados da sessão")
    st.caption("Metadados, métricas por lado e valor/tempo de cada pico de flexão do joelho.")
    rel = construir_relatorio(resumo, modo, lado)
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Baixar JSON", data=relatorio_para_json(rel),
                       file_name="stepwise_sessao.json", mime="application/json",
                       key=f"dl_json_{key}")
    c2.download_button("⬇️ Baixar Excel (.xlsx)", data=relatorio_para_excel(rel),
                       file_name="stepwise_sessao.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key=f"dl_xlsx_{key}")


def _bloco_exportacao_comparacao(res_i: dict, res_f: dict, modo: str, lado: str | None, key: str):
    """Download da comparação Início × Final (tabela comparativa + métricas, ombros e picos das duas sessões)."""
    st.markdown("#### 💾 Exportar comparação")
    st.caption("Tabela comparativa com a variação, metadados e, por sessão, métricas, ombros e picos.")
    rel = construir_relatorio_comparacao(res_i, res_f, modo, lado)
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Baixar comparação (JSON)", data=relatorio_para_json(rel),
                       file_name="stepwise_comparacao.json", mime="application/json",
                       key=f"dl_json_{key}")
    c2.download_button("⬇️ Baixar comparação (Excel .xlsx)", data=relatorio_para_excel(rel),
                       file_name="stepwise_comparacao.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key=f"dl_xlsx_{key}")


def _secao_picos_bilateral(resumo, tempo, df, limiares, fps, key: str, label: str = ""):
    prefixo = f"{label} — " if label else ""
    st.markdown(f"#### {prefixo}Joelho")
    st.plotly_chart(_plot_sinal_com_picos(
        tempo, df[COL_JOELHO_ESQ], df[COL_JOELHO_DIR],
        resumo['picos']['joelho_esq'], resumo['picos']['joelho_dir'],
        limiares['joelho'], "Amplitude de Flexão do Joelho",
    ), use_container_width=True, key=f"grafico_joelho_{key}")

    c1, c2 = st.columns(2)
    with c1:
        st.caption("Picos — Esquerdo")
        _tabela_picos(resumo['picos']['joelho_esq'], fps)
    with c2:
        st.caption("Picos — Direito")
        _tabela_picos(resumo['picos']['joelho_dir'], fps)


def _secao_picos_unilateral(resumo, tempo, df, limiares, fps, lado, key: str, label: str = ""):
    prefixo = f"{label} — " if label else ""
    chave = 'joelho_esq' if lado == "Esquerdo" else 'joelho_dir'
    col = COL_JOELHO_ESQ if lado == "Esquerdo" else COL_JOELHO_DIR
    cor = COR_ESQ if lado == "Esquerdo" else COR_DIR
    st.markdown(f"#### {prefixo}Joelho {lado}")
    st.plotly_chart(_plot_sinal_unilateral(
        tempo, df[col], resumo['picos'][chave], limiares['joelho'],
        f"Flexão do Joelho — {lado}", cor, lado,
    ), use_container_width=True, key=f"grafico_joelho_{key}")
    _tabela_picos(resumo['picos'][chave], fps)


def _corpo_bilateral(df, resumo, tempo, limiares, fps, key, modo, label=""):
    _secao_metricas(resumo, ['joelho_esq', 'joelho_dir'], label)
    st.markdown("---")
    _secao_picos_bilateral(resumo, tempo, df, limiares, fps, key, label)
    st.markdown("---")
    _expander_ombros(df, tempo, resumo, key)
    st.markdown("---")
    _bloco_exportacao(resumo, modo, None, key)


def _corpo_unilateral(df, resumo, tempo, limiares, fps, lado, key, modo, label=""):
    chave = 'joelho_esq' if lado == "Esquerdo" else 'joelho_dir'
    _secao_metricas(resumo, [chave], label)
    st.markdown("---")
    _secao_picos_unilateral(resumo, tempo, df, limiares, fps, lado, key, label)
    st.markdown("---")
    _expander_ombros(df, tempo, resumo, key)
    st.markdown("---")
    _bloco_exportacao(resumo, modo, lado, key)


def _seletor_lado(key: str) -> str:
    return st.radio("Selecione o membro exercitado para análise detalhada:",
                    options=["Esquerdo", "Direito"], horizontal=True, key=key)


# =============================================================================
# MODOS DE SESSÃO ÚNICA
# =============================================================================

def _carregar_sessao(arquivo, limiares):
    try:
        df = carregar_arquivo(arquivo)
    except ValueError as e:
        st.error(f"Erro ao carregar arquivo: {e}")
        return None
    fps = calcular_fps(df)
    return df, fps, _tempo_eixo(df, fps), gerar_resumo_sessao(df, fps, limiares)


def _modo_bilateral(limiares: dict):
    st.markdown("### 📁 Upload da Sessão")
    arquivo = st.file_uploader("Envie o arquivo da sessão (CSV, XLSX ou XLSM)",
                               type=["csv", "xlsx", "xlsm"], key="bilateral")
    if not arquivo:
        st.info("Envie um arquivo para iniciar a análise.")
        return
    sessao = _carregar_sessao(arquivo, limiares)
    if sessao is None:
        return
    df, fps, tempo, resumo = sessao

    st.success(f"✅ {len(df)} frames | {len(df)/fps:.1f} s | {fps} FPS | origem: {resumo['fonte']}")
    st.markdown("---")
    _corpo_bilateral(df, resumo, tempo, limiares, fps, "unico_bi", MODO_UNICA_BI)


def _modo_unilateral(limiares: dict):
    st.markdown("### 📁 Upload da Sessão")
    arquivo = st.file_uploader("Envie o arquivo da sessão (CSV, XLSX ou XLSM)",
                               type=["csv", "xlsx", "xlsm"], key="unilateral")
    if not arquivo:
        st.info("Envie um arquivo para iniciar a análise.")
        return
    sessao = _carregar_sessao(arquivo, limiares)
    if sessao is None:
        return
    df, fps, tempo, resumo = sessao

    st.success(f"✅ {len(df)} frames | {len(df)/fps:.1f} s | {fps} FPS | origem: {resumo['fonte']}")

    st.markdown("---")
    st.markdown("#### 👀 Visão Geral — Identifique o lado que executou o movimento")
    st.caption("Use o gráfico para confirmar qual membro realizou o exercício antes de "
               "selecionar o lado para análise detalhada.")
    st.plotly_chart(_plot_overview_bilateral(tempo, df, "Joelho — Ambos os lados"),
                    use_container_width=True, key="overview_unico")

    st.markdown("---")
    lado = _seletor_lado("lado_unilateral")
    st.markdown("---")
    _corpo_unilateral(df, resumo, tempo, limiares, fps, lado, "unico_uni", MODO_UNICA_UNI)


# =============================================================================
# MODOS DE COMPARAÇÃO (INÍCIO vs FINAL) — BILATERAL E UNILATERAL
# =============================================================================

def _modo_comparacao(limiares: dict, unilateral: bool, limiares_final: dict = None):
    # Se não houver limiar próprio para a sessão final, usa o mesmo do início.
    limiares_final = limiares_final or limiares
    st.markdown("### 📁 Upload das Sessões")
    col1, col2 = st.columns(2)
    sufixo = "uni" if unilateral else "bi"
    with col1:
        arq_inicio = st.file_uploader("📂 Sessão de Início", type=["csv", "xlsx", "xlsm"],
                                      key=f"inicio_{sufixo}")
    with col2:
        arq_final = st.file_uploader("📂 Sessão Final", type=["csv", "xlsx", "xlsm"],
                                     key=f"final_{sufixo}")

    if not (arq_inicio and arq_final):
        st.info("Envie ambos os arquivos para iniciar a comparação.")
        return

    sess_i = _carregar_sessao(arq_inicio, limiares)
    sess_f = _carregar_sessao(arq_final, limiares_final)
    if sess_i is None or sess_f is None:
        return
    df_i, fps_i, tempo_i, res_i = sess_i
    df_f, fps_f, tempo_f, res_f = sess_f

    # Aviso: métricas dependentes de picos só são comparáveis com o mesmo limiar.
    if limiares['joelho'] != limiares_final['joelho']:
        st.warning(
            f"⚠️ Limiares diferentes: Início = {limiares['joelho']:g}° e Final = "
            f"{limiares_final['joelho']:g}°. Número de picos, amplitude dos picos, "
            "Robinson, consistência e Jerk dependem do limiar, então a comparação "
            "entre as sessões pode refletir a mudança do limiar, e não do paciente.")

    col1, col2 = st.columns(2)
    col1.success(f"✅ Início — {len(df_i)} frames | {len(df_i)/fps_i:.1f} s | {res_i['fonte']}")
    col2.success(f"✅ Final — {len(df_f)} frames | {len(df_f)/fps_f:.1f} s | {res_f['fonte']}")

    if unilateral:
        st.markdown("---")
        st.markdown("#### 👀 Visão Geral — Identifique o lado que executou o movimento")
        c1, c2 = st.columns(2)
        c1.plotly_chart(_plot_overview_bilateral(tempo_i, df_i, "Início — Joelhos"),
                        use_container_width=True, key="overview_comp_i")
        c2.plotly_chart(_plot_overview_bilateral(tempo_f, df_f, "Final — Joelhos"),
                        use_container_width=True, key="overview_comp_f")
        lado = _seletor_lado("lado_comparacao")
        chaves = ['joelho_esq' if lado == "Esquerdo" else 'joelho_dir']
        modo = MODO_COMP_UNI
    else:
        lado = None
        chaves = ['joelho_esq', 'joelho_dir']
        modo = MODO_COMP_BI

    # Métricas lado a lado
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        _secao_metricas(res_i, chaves, "Início")
    with col2:
        _secao_metricas(res_f, chaves, "Final")

    st.markdown("---")
    st.markdown("#### 🔁 Tabela comparativa")
    st.caption("Valores numéricos puros (unidade no nome da métrica) para copiar e colar.")
    _tabela_comparativa(res_i, res_f, chaves)
    _bloco_exportacao_comparacao(res_i, res_f, modo, lado, f"cmp_{sufixo}")

    # Comparação de amplitudes por pico
    st.markdown("---")
    st.markdown("#### 📊 Comparação de amplitudes por pico")
    st.caption("Picos das duas sessões lado a lado, para verificar ganho de amplitude. "
               "(Dica: ajuste o limiar antes de comparar.)")
    if len(chaves) == 2:
        tabs = st.tabs(["Joelho Esquerdo", "Joelho Direito"])
        for tab, k in zip(tabs, chaves):
            with tab:
                st.plotly_chart(_plot_comparacao_amplitudes(
                    res_i['picos'][k], res_f['picos'][k], "Início", "Final",
                    f"Joelho {NOME_LADO[k]} — Amplitude por Pico"),
                    use_container_width=True, key=f"comp_amp_{sufixo}_{k}")
    else:
        k = chaves[0]
        st.plotly_chart(_plot_comparacao_amplitudes(
            res_i['picos'][k], res_f['picos'][k], "Início", "Final",
            f"Joelho {NOME_LADO[k]} — Amplitude por Pico"),
            use_container_width=True, key=f"comp_amp_{sufixo}_{k}")

    # Sinais detalhados, ombros e exportação por sessão
    st.markdown("---")
    st.markdown("#### 🔍 Sinais detalhados")
    aba_i, aba_f = st.tabs(["Sessão Início", "Sessão Final"])
    for aba, df, res, tempo, fps, rot in [(aba_i, df_i, res_i, tempo_i, fps_i, "Início"),
                                          (aba_f, df_f, res_f, tempo_f, fps_f, "Final")]:
        with aba:
            key = f"comp_{sufixo}_{rot.lower()}"
            if unilateral:
                _secao_picos_unilateral(res, tempo, df, res['limiares'], fps, lado, key, rot)
            else:
                _secao_picos_bilateral(res, tempo, df, res['limiares'], fps, key, rot)
            st.markdown("---")
            _expander_ombros(df, tempo, res, key)
            st.markdown("---")
            _bloco_exportacao(res, f"{modo} — Sessão {rot}", lado, key)


# =============================================================================
# PONTO DE ENTRADA DA VIEW
# =============================================================================

def carregar():
    st.markdown("Análise cinemática dos membros inferiores durante a intervenção **Obstacles**. ")

    with st.sidebar:
        st.markdown("## ⚙️ Parâmetros clínicos")
        st.caption("Definidos pelo profissional de saúde para esta sessão.")
        limiar_joelho = st.number_input(
            "Limiar de **joelho** (graus)",
            min_value=0.0, max_value=180.0, value=30.0, step=1.0,
            help="Ângulo mínimo de flexão do joelho para validar o movimento.",
        )
        limiares = {'joelho': limiar_joelho}

        st.markdown("---")
        st.markdown("## 📋 Modo de análise")
        modo = st.radio("Selecione o modo:",
                        options=[MODO_UNICA_BI, MODO_UNICA_UNI, MODO_COMP_BI, MODO_COMP_UNI],
                        index=0)

        # Na comparação, o limiar acima vale para a sessão de início; a final
        # pode ter limiar próprio (ex.: paciente que evoluiu), com aviso na tela.
        limiares_final = limiares
        if modo in (MODO_COMP_BI, MODO_COMP_UNI):
            if st.checkbox("Usar limiar diferente na sessão final", value=False):
                limiar_final = st.number_input(
                    "Limiar de **joelho** — sessão final (graus)",
                    min_value=0.0, max_value=180.0, value=limiar_joelho, step=1.0)
                limiares_final = {'joelho': limiar_final}

    aba_analise, aba_guia = st.tabs(["📊 Análise", "📖 Guia de métricas"])

    with aba_analise:
        if modo == MODO_UNICA_BI:
            _modo_bilateral(limiares)
        elif modo == MODO_UNICA_UNI:
            _modo_unilateral(limiares)
        elif modo == MODO_COMP_BI:
            _modo_comparacao(limiares, unilateral=False, limiares_final=limiares_final)
        else:
            _modo_comparacao(limiares, unilateral=True, limiares_final=limiares_final)

    with aba_guia:
        _aba_metricas_info()
