import numpy as np
import pandas as pd

# =============================================================================
# COLUNAS E PADRONIZAÇÃO INTERNA
# =============================================================================
COL_QUADRIL_ESQ = 'quadril_esq'
COL_QUADRIL_DIR = 'quadril_dir'
COL_JOELHO_ESQ  = 'joelho_esq'
COL_JOELHO_DIR  = 'joelho_dir'
COL_TEMPO       = 'tempo_s'
COL_FPS_BASE    = 'fps_base'

# =============================================================================
# 1. CARREGAMENTO DO ARQUIVO E DETECÇÃO DA FONTE
# =============================================================================

def carregar_arquivo(arquivo) -> pd.DataFrame:
    """
    Carrega um arquivo de dados cinemáticos, detecta automaticamente se a origem
    é KinesiOS ou Brainn_XR, e padroniza as colunas e o eixo de tempo.
    """
    nome = arquivo.name if hasattr(arquivo, 'name') else str(arquivo)
    extensao = nome.lower().split('.')[-1]

    if extensao == 'csv':
        df = pd.read_csv(arquivo)
    elif extensao in ('xlsx', 'xlsm'):
        try:
            df = pd.read_excel(arquivo, sheet_name='KinesiOS', engine='openpyxl')
        except Exception:
            df = pd.read_excel(arquivo, sheet_name=0, engine='openpyxl')
    else:
        raise ValueError(f"Formato '{extensao}' não suportado. Use CSV, XLSX ou XLSM.")

    df = df.dropna(how='all').reset_index(drop=True)
    colunas_atuais = list(df.columns)

    # ---------------------------------------------------------
    # Detecção: KINESIOS
    # ---------------------------------------------------------
    if 'Range of Motion Hip (Left)' in colunas_atuais:
        fps_calculado = 28.0
        df = df.rename(columns={
            'Range of Motion Hip (Left)':  COL_QUADRIL_ESQ,
            'Range of Motion Hip (Right)': COL_QUADRIL_DIR,
            'Range of Motion Knee (Left)': COL_JOELHO_ESQ,
            'Range of Motion Knee (Right)': COL_JOELHO_DIR,
        })
        
    # ---------------------------------------------------------
    # Detecção: BRAINN_XR
    # ---------------------------------------------------------
    elif 'hipLangle' in colunas_atuais:
        df = df.rename(columns={
            'hipLangle':  COL_QUADRIL_ESQ,
            'hipRangle':  COL_QUADRIL_DIR,
            'kneeLangle': COL_JOELHO_ESQ,
            'kneeRangle': COL_JOELHO_DIR,
        })
        
        fps_calculado = 24.0 # Fallback de segurança
        
        if 'time' in df.columns:
            try:
                # Agrupa pela mudança de segundos para extrair o FPS real
                df['seconds'] = df['time'].astype(str).str[-2:]
                df['count'] = (df['seconds'] != df['seconds'].shift(1)).cumsum()
                result = df.groupby('count').size().reset_index(name='counts')
                
                if len(result) > 1:
                    # Pega o segundo bloco, pois o primeiro pode ser um segundo incompleto
                    fps_calculado = float(result.loc[1, 'counts'])
                    
                # Limpa as colunas temporárias
                df = df.drop(columns=['seconds', 'count'])
            except Exception:
                pass 

    else:
        raise ValueError(
            "Origem de dados não reconhecida.\n"
            "O arquivo deve conter as colunas do KinesiOS (ex: 'Range of Motion...') "
            "ou do Brainn_XR (ex: 'hipLangle')."
        )

    # ---------------------------------------------------------
    # EIXO DE TEMPO SINTÉTICO
    # ---------------------------------------------------------
    # Forçamos a criação de uma linha do tempo suave baseada no FPS real detectado.
    df[COL_TEMPO] = df.index / fps_calculado
    df[COL_FPS_BASE] = fps_calculado

    # Aplicação da correção de segurança do Pandas 
    df[COL_TEMPO] = df[COL_TEMPO].fillna(pd.Series(df.index / fps_calculado))

    return df

# =============================================================================
# 2. CÁLCULO DE FPS
# =============================================================================

def calcular_fps(df: pd.DataFrame) -> float:
    """
    Retorna o FPS calculado dinamicamente durante a leitura do arquivo.
    """
    if COL_FPS_BASE in df.columns:
        return float(df[COL_FPS_BASE].iloc[0])
    return 28.0

# =============================================================================
# 3. EXTRAÇÃO DE PICOS (OBSTÁCULOS)
# =============================================================================

def extrair_picos_marcha(
    dados: pd.Series,
    fps: float,
    limiar_selecionado: float,
    janela_minima_frames: int = 5
) -> list[dict]:
    """
    Identifica todos os picos de flexão detectados na sessão de marcha
    estacionária, independentemente da quantidade.

    Um pico é detectado quando o ângulo ultrapassa o limiar clínico definido
    pelo profissional de saúde e permanece acima dele por pelo menos
    'janela_minima_frames' frames (filtro anti-ruído). O número de picos
    encontrados pode ser menor que 10 — isso é esperado em pacientes com
    mobilidade reduzida e é em si uma informação clínica relevante.

    Parâmetros:
        dados: Série de ângulos ao longo do tempo (ex: quadril esquerdo).
        fps: Taxa de quadros por segundo (28.0 para o Kinect).
        limiar_selecionado: Ângulo mínimo (graus) para validar o movimento.
        janela_minima_frames: Frames mínimos acima do limiar para ser um pico
                              válido (padrão: 5 frames ≈ 0.18s a 28fps).

    Retorna:
        Lista de dicionários, um por pico detectado, com as chaves:
            - 'pico': índice sequencial do pico (1, 2, 3, ...)
            - 'inicio_frame': frame de início do pico
            - 'fim_frame': frame de fim do pico
            - 'inicio_seg': tempo de início em segundos
            - 'fim_seg': tempo de fim em segundos
            - 'duracao': duração do pico em segundos
            - 'amplitude_maxima': maior ângulo atingido no pico (graus)
            - 'frame_pico': frame onde a amplitude máxima ocorre
    """
    dados = dados.reset_index(drop=True)
    tempo = np.arange(len(dados)) / fps

    # Máscara binária: 1 onde está acima do limiar, 0 abaixo
    acima = (dados > limiar_selecionado).astype(int)
    mudancas = np.diff(acima.values)

    inicios = np.where(mudancas == 1)[0] + 1  # +1 para apontar para o frame real
    finais  = np.where(mudancas == -1)[0] + 1

    # Alinha inícios e finais (garante pares completos)
    if len(finais) > 0 and len(inicios) > 0:
        # Se o sinal começa já acima do limiar, descarta esse final solto
        if finais[0] < inicios[0]:
            finais = finais[1:]
        # Se termina sem baixar do limiar, descarta o início sem fim
        if len(inicios) > len(finais):
            inicios = inicios[:len(finais)]
        min_len = min(len(inicios), len(finais))
        inicios = inicios[:min_len]
        finais  = finais[:min_len]
    else:
        return []  # Nenhum pico encontrado

    picos = []
    for i, f in zip(inicios, finais):
        # Filtra eventos curtos demais (ruído)
        if (f - i) < janela_minima_frames:
            continue

        segmento = dados[i:f]
        idx_max  = segmento.idxmax()

        picos.append({
            'pico':             len(picos) + 1,
            'inicio_frame':     int(i),
            'fim_frame':        int(f),
            'inicio_seg':       float(tempo[i]),
            'fim_seg':          float(tempo[f]),
            'duracao':          float(tempo[f] - tempo[i]),
            'amplitude_maxima': float(segmento.max()),
            'frame_pico':       int(idx_max),
        })

    return picos


def picos_para_dataframe(picos: list[dict]) -> pd.DataFrame:
    """
    Converte a lista de picos em um DataFrame organizado para exibição
    no dashboard ou uso nos modelos de AM.
    """
    if not picos:
        return pd.DataFrame()
    return pd.DataFrame(picos).set_index('pico')


# =============================================================================
# 4. MÉTRICAS BIOMECÂNICAS
# =============================================================================

def calcular_amplitude_sessao(dados: pd.Series) -> dict:
    """
    Calcula a amplitude média e máxima do sinal ao longo de toda a sessão
    (independentemente de picos), para quadril ou joelho.

    Diferente da amplitude por pico (que reflete só os movimentos válidos
    acima do limiar), esta métrica dá uma visão geral do ângulo praticado
    durante toda a sessão — útil como referência rápida para o terapeuta,
    mesmo quando poucos ou nenhum pico é detectado.

    Parâmetros:
        dados: Série de ângulos ao longo do tempo (ex: quadril esquerdo).

    Retorna:
        Dicionário com:
            - 'media': amplitude média da sessão (graus)
            - 'maxima': amplitude máxima atingida na sessão (graus)
    """
    if len(dados) == 0:
        return {'media': 0.0, 'maxima': 0.0}

    return {
        'media':  float(dados.mean()),
        'maxima': float(dados.max()),
    }


def calcular_consistencia_temporal(picos: list[dict]) -> dict:
    """
    Avalia a consistência temporal entre os obstáculos transpostos.

    Analisa se o paciente manteve um ritmo regular ao longo dos 10
    obstáculos, comparando as durações de cada pico.

    Parâmetros:
        picos: Lista de dicionários retornada por extrair_picos_marcha().

    Retorna:
        Dicionário com:
            - 'media_duracao': duração média dos picos (s)
            - 'desvio_duracao': desvio padrão das durações (s)
            - 'cv_duracao': coeficiente de variação (%) — quanto menor,
                            mais consistente o ritmo
            - 'n_picos': quantidade de picos detectados
    """
    if not picos:
        return {
            'media_duracao':  0.0,
            'desvio_duracao': 0.0,
            'cv_duracao':     0.0,
            'n_picos':        0,
        }

    duracoes = np.array([p['duracao'] for p in picos])
    media    = float(np.mean(duracoes))
    desvio   = float(np.std(duracoes))
    cv       = float((desvio / media * 100) if media > 0 else 0.0)

    return {
        'media_duracao':  round(media, 3),
        'desvio_duracao': round(desvio, 3),
        'cv_duracao':     round(cv, 2),
        'n_picos':        len(picos),
    }


# =============================================================================
# 5. RESUMO COMPLETO DA SESSÃO
# =============================================================================

def gerar_resumo_sessao(df: pd.DataFrame, fps: float, limiares: dict) -> dict:
    """
    Gera um resumo completo de todas as métricas biomecânicas de uma sessão.

    Este é o ponto de entrada principal para o dashboard e para os modelos
    de AM: recebe o DataFrame bruto e os limiares definidos pelo clínico,
    e retorna todas as métricas calculadas.

    Parâmetros:
        df: DataFrame carregado via carregar_arquivo().
        fps: FPS obtido via calcular_fps() — 28.0 para o Kinect.
        limiares: Dicionário com os limiares clínicos definidos pelo clínico:
                  {
                      'quadril': 45.0,   # graus mínimos de flexão de quadril
                      'joelho':  30.0,   # graus mínimos de flexão de joelho
                  }

    Retorna:
        Dicionário aninhado com todas as métricas da sessão, incluindo:
        picos, amplitude (média/máxima de quadril e joelho), tempo de
        execução da sessão (s) e consistência temporal.
    """
    limiar_quadril = limiares.get('quadril', 45.0)
    limiar_joelho  = limiares.get('joelho',  30.0)

    # --- Extração de picos (quadril e joelho — foco clínico) ---
    picos_quadril_esq = extrair_picos_marcha(df[COL_QUADRIL_ESQ], fps, limiar_quadril)
    picos_quadril_dir = extrair_picos_marcha(df[COL_QUADRIL_DIR], fps, limiar_quadril)
    picos_joelho_esq  = extrair_picos_marcha(df[COL_JOELHO_ESQ],  fps, limiar_joelho)
    picos_joelho_dir  = extrair_picos_marcha(df[COL_JOELHO_DIR],  fps, limiar_joelho)

    # --- Amplitude de sessão (média e máxima) — quadril e joelho ---
    amplitude_quadril_esq = calcular_amplitude_sessao(df[COL_QUADRIL_ESQ])
    amplitude_quadril_dir = calcular_amplitude_sessao(df[COL_QUADRIL_DIR])
    amplitude_joelho_esq  = calcular_amplitude_sessao(df[COL_JOELHO_ESQ])
    amplitude_joelho_dir  = calcular_amplitude_sessao(df[COL_JOELHO_DIR])

    # --- Consistência temporal dos picos ---
    consistencia_quadril_esq = calcular_consistencia_temporal(picos_quadril_esq)
    consistencia_quadril_dir = calcular_consistencia_temporal(picos_quadril_dir)
    consistencia_joelho_esq  = calcular_consistencia_temporal(picos_joelho_esq)
    consistencia_joelho_dir  = calcular_consistencia_temporal(picos_joelho_dir)

    return {
        'picos': {
            'quadril_esq': picos_quadril_esq,
            'quadril_dir': picos_quadril_dir,
            'joelho_esq':  picos_joelho_esq,
            'joelho_dir':  picos_joelho_dir,
        },
        'amplitude': {
            'quadril_esq': amplitude_quadril_esq,
            'quadril_dir': amplitude_quadril_dir,
            'joelho_esq':  amplitude_joelho_esq,
            'joelho_dir':  amplitude_joelho_dir,
        },
        'tempo_execucao_seg': float(len(df) / fps),
        'consistencia': {
            'quadril_esq': consistencia_quadril_esq,
            'quadril_dir': consistencia_quadril_dir,
            'joelho_esq':  consistencia_joelho_esq,
            'joelho_dir':  consistencia_joelho_dir,
        },
        'n_frames': len(df),
        'fps':      fps,
        'limiares': limiares,
    }