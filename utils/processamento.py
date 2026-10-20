import io
import json
import math

import numpy as np
import pandas as pd

# =============================================================================
# COLUNAS E PADRONIZAÇÃO INTERNA
# =============================================================================
COL_JOELHO_ESQ = 'joelho_esq'
COL_JOELHO_DIR = 'joelho_dir'
COL_OMBRO_ESQ  = 'ombro_esq'
COL_OMBRO_DIR  = 'ombro_dir'
COL_TEMPO      = 'tempo_s'
COL_FPS_BASE   = 'fps_base'

# Parâmetros do pré-processamento do sinal (usados antes do cálculo do Jerk)
FPS_ALVO              = 30.0   # taxa comum para normalização temporal (Hz)
CORTE_PASSA_BAIXA_HZ  = 6.0    # frequência de corte do filtro anti-ruído (Hz)
ORDEM_BUTTERWORTH     = 4
JANELA_SAVGOL         = 9      # nº ímpar de amostras da derivada de Savitzky-Golay
ORDEM_POLINOMIO       = 4      # precisa ser >= 3 para derivada de ordem 3

# Nomes possíveis das colunas de ombro nos arquivos de origem. Ajuste aqui caso
# os softwares exportem nomes diferentes. Se nenhum nome for encontrado, há uma
# busca genérica por colunas que contenham "shoulder"/"ombro" + lado.
CANDIDATOS_OMBRO_ESQ = ['Range of Motion Shoulder (Left)', 'shoulderLangle',
                        'Shoulder (Left)', 'ombro_esq']
CANDIDATOS_OMBRO_DIR = ['Range of Motion Shoulder (Right)', 'shoulderRangle',
                        'Shoulder (Right)', 'ombro_dir']


# =============================================================================
# 1. CARREGAMENTO DO ARQUIVO E DETECÇÃO DA FONTE
# =============================================================================

def _detectar_coluna_ombro(colunas: list, candidatos: list, lado_tokens: tuple):
    """Procura a coluna do ombro por nome exato e, se falhar, por busca genérica."""
    for nome in candidatos:
        if nome in colunas:
            return nome
    for c in colunas:
        c_low = str(c).lower()
        if ('shoulder' in c_low or 'ombro' in c_low) and any(t in c_low for t in lado_tokens):
            return c
    return None


def _tempo_para_segundos(valor) -> float:
    """
    Converte o carimbo de tempo do Brainn_XR em segundos desde a meia-noite.
    Aceita HHMMSSmmm numérico (ex.: 101716149 = 10:17:16.149) ou texto
    'HH:MM:SS(.mmm)'. Retorna NaN se não for possível interpretar.
    """
    try:
        txt = str(valor).strip()
        if ':' in txt:
            h, m, s = txt.split(':')[-3:]
            return int(h) * 3600 + int(m) * 60 + float(s)
        txt = str(int(float(txt))).zfill(9)          # HHMMSSmmm
        return int(txt[:2]) * 3600 + int(txt[2:4]) * 60 + int(txt[4:6]) + int(txt[6:9]) / 1000.0
    except Exception:
        return float('nan')


def _estimar_fps_brainn(df: pd.DataFrame, fallback: float = 24.0) -> float:
    """
    Estima o FPS real do Brainn_XR a partir do intervalo total de tempo:
    (n_frames - 1) / duração. Usa o fallback se a coluna 'time' faltar, não for
    interpretável ou resultar em valor implausível (fora de 5–120 FPS).
    """
    if 'time' not in df.columns or len(df) < 2:
        return fallback
    t = df['time'].map(_tempo_para_segundos).dropna()
    if len(t) < 2:
        return fallback
    duracao = float(t.iloc[-1] - t.iloc[0])
    if duracao < 0:                                   # virada de meia-noite
        duracao += 86400.0
    if duracao <= 0:
        return fallback
    fps = (len(t) - 1) / duracao
    return round(fps, 2) if 5.0 <= fps <= 120.0 else fallback


def carregar_arquivo(arquivo) -> pd.DataFrame:
    """
    Carrega um arquivo de dados cinemáticos, detecta automaticamente se a origem
    é KinesiOS ou Brainn_XR, e padroniza as colunas (joelhos e, se existirem,
    ombros) e o eixo de tempo. A origem fica em df.attrs['fonte'].
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

    # Colunas de ombro (opcionais) — detectadas antes do rename
    col_ombro_esq = _detectar_coluna_ombro(colunas_atuais, CANDIDATOS_OMBRO_ESQ,
                                           ('left', 'esq', 'langle'))
    col_ombro_dir = _detectar_coluna_ombro(colunas_atuais, CANDIDATOS_OMBRO_DIR,
                                           ('right', 'dir', 'rangle'))

    # ---------------------------------------------------------
    # Detecção: KINESIOS
    # ---------------------------------------------------------
    if 'Range of Motion Knee (Left)' in colunas_atuais:
        fonte = 'KinesiOS'
        fps_calculado = 28.0
        mapa = {
            'Range of Motion Knee (Left)':  COL_JOELHO_ESQ,
            'Range of Motion Knee (Right)': COL_JOELHO_DIR,
        }

    # ---------------------------------------------------------
    # Detecção: BRAINN_XR
    # ---------------------------------------------------------
    elif 'kneeLangle' in colunas_atuais:
        fonte = 'Brainn_XR'
        mapa = {
            'kneeLangle': COL_JOELHO_ESQ,
            'kneeRangle': COL_JOELHO_DIR,
        }

        fps_calculado = _estimar_fps_brainn(df)
    else:
        raise ValueError(
            "Origem de dados não reconhecida.\n"
            "O arquivo deve conter as colunas do KinesiOS (ex: 'Range of Motion Knee...') "
            "ou do Brainn_XR (ex: 'kneeLangle')."
        )

    if col_ombro_esq:
        mapa[col_ombro_esq] = COL_OMBRO_ESQ
    if col_ombro_dir:
        mapa[col_ombro_dir] = COL_OMBRO_DIR
    df = df.rename(columns=mapa)

    # Garante colunas numéricas e sem buracos (interpolação linear)
    for c in (COL_JOELHO_ESQ, COL_JOELHO_DIR, COL_OMBRO_ESQ, COL_OMBRO_DIR):
        if c in df.columns:
            df[c] = (pd.to_numeric(df[c], errors='coerce')
                       .interpolate(limit_direction='both')
                       .fillna(0.0))

    # Eixo de tempo sintético baseado no FPS real detectado
    df[COL_TEMPO] = df.index / fps_calculado
    df[COL_FPS_BASE] = fps_calculado
    df.attrs['fonte'] = fonte
    df.attrs['arquivo'] = nome
    return df


# =============================================================================
# 2. CÁLCULO DE FPS
# =============================================================================

def calcular_fps(df: pd.DataFrame) -> float:
    """Retorna o FPS calculado dinamicamente durante a leitura do arquivo."""
    if COL_FPS_BASE in df.columns:
        return float(df[COL_FPS_BASE].iloc[0])
    return 28.0


def tem_ombros(df: pd.DataFrame) -> bool:
    """Indica se o arquivo possui os dados de ombro (esquerdo e direito)."""
    return COL_OMBRO_ESQ in df.columns and COL_OMBRO_DIR in df.columns


# =============================================================================
# 3. EXTRAÇÃO DE PICOS
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
    pelo profissional e permanece acima dele por pelo menos
    'janela_minima_frames' frames (filtro anti-ruído; em segundos isso se ajusta
    à taxa de amostragem de origem). Menos de 10 picos é esperado em pacientes
    com mobilidade reduzida e é, em si, uma informação clínica.

    Retorna lista de dicionários com: pico, inicio_frame, fim_frame, inicio_seg,
    fim_seg, duracao, amplitude_maxima, frame_pico.
    """
    dados = dados.reset_index(drop=True)
    tempo = np.arange(len(dados)) / fps

    acima = (dados > limiar_selecionado).astype(int)
    mudancas = np.diff(acima.values)

    inicios = np.where(mudancas == 1)[0] + 1
    finais  = np.where(mudancas == -1)[0] + 1

    if len(finais) > 0 and len(inicios) > 0:
        if finais[0] < inicios[0]:
            finais = finais[1:]
        if len(inicios) > len(finais):
            inicios = inicios[:len(finais)]
        min_len = min(len(inicios), len(finais))
        inicios = inicios[:min_len]
        finais  = finais[:min_len]
    else:
        return []

    picos = []
    for i, f in zip(inicios, finais):
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
    """Converte a lista de picos em DataFrame para exibição e modelos de AM."""
    if not picos:
        return pd.DataFrame()
    return pd.DataFrame(picos).set_index('pico')


# =============================================================================
# 4. MÉTRICAS BIOMECÂNICAS
# =============================================================================

def calcular_amplitude_sessao(dados: pd.Series) -> dict:
    """Amplitude média e máxima do sinal ao longo de toda a sessão."""
    if len(dados) == 0:
        return {'media': 0.0, 'maxima': 0.0}
    return {'media': float(dados.mean()), 'maxima': float(dados.max())}


def calcular_consistencia_temporal(picos: list[dict]) -> dict:
    """
    Consistência temporal: média, desvio e Coeficiente de Variação (CV%) das
    durações dos picos. Quanto menor o CV, mais regular o ritmo.
    """
    if not picos:
        return {'media_duracao': 0.0, 'desvio_duracao': 0.0,
                'cv_duracao': 0.0, 'n_picos': 0}

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


def amplitude_media_dos_picos(picos: list[dict]) -> float:
    """Média das amplitudes máximas dos picos de flexão (NaN se não houver picos)."""
    if not picos:
        return float('nan')
    return float(np.mean([p['amplitude_maxima'] for p in picos]))


def calcular_indice_simetria_robinson(picos_dir: list[dict], picos_esq: list[dict]) -> dict:
    """
    Índice de Simetria de Robinson:
        SI = 2 * |X_dir - X_esq| / (X_dir + X_esq) * 100 (%)
    onde X é a amplitude média dos picos de flexão do joelho.
    0% = simetria perfeita. Retorna NaN se algum lado não tiver picos ou se
    a soma das amplitudes for zero (evita divisão por zero).
    """
    x_dir = amplitude_media_dos_picos(picos_dir)
    x_esq = amplitude_media_dos_picos(picos_esq)
    si = float('nan')
    if not (math.isnan(x_dir) or math.isnan(x_esq)):
        soma = x_dir + x_esq
        if soma != 0:
            si = 2.0 * abs(x_dir - x_esq) / soma * 100.0
    return {'si_pct': si, 'x_dir': x_dir, 'x_esq': x_esq}


# -----------------------------------------------------------------------------
# Suavidade motora (Jerk RMS)
# -----------------------------------------------------------------------------

def _filtro_passa_baixa_fase_zero(y: np.ndarray, fps: float, corte_hz: float,
                                  ordem: int = ORDEM_BUTTERWORTH) -> np.ndarray:
    """
    Passa-baixa Butterworth de fase zero (equivalente ao filtfilt) feito só com
    numpy, no domínio da frequência: o filtfilt aplica o filtro nos dois sentidos,
    o que resulta em resposta |H(f)|^2 = 1 / (1 + (f/fc)^(2*ordem)) e fase nula.
    O sinal é estendido por reflexão ímpar nas bordas para reduzir efeitos de borda.
    """
    n = len(y)
    pad = min(3 * int(fps), n - 1)
    if pad > 0:
        ini = 2 * y[0] - y[pad:0:-1]
        fim = 2 * y[-1] - y[-2:-pad - 2:-1]
        ext = np.concatenate([ini, y, fim])
    else:
        ext = y
    freqs = np.fft.rfftfreq(len(ext), d=1.0 / fps)
    ganho = 1.0 / (1.0 + (freqs / corte_hz) ** (2 * ordem))
    filtrado = np.fft.irfft(np.fft.rfft(ext) * ganho, n=len(ext))
    return filtrado[pad:pad + n] if pad > 0 else filtrado


def _derivada_savgol(y: np.ndarray, janela: int, ordem_pol: int,
                     deriv: int, delta: float) -> np.ndarray:
    """
    Derivada de Savitzky-Golay só com numpy (mesmo resultado do scipy com
    mode='interp'): convolução com coeficientes de mínimos quadrados no miolo e
    ajuste polinomial na primeira/última janela para as bordas.
    """
    m = janela // 2
    x = np.arange(-m, m + 1, dtype=float)
    A = np.vander(x, ordem_pol + 1, increasing=True)
    coef = np.linalg.pinv(A)[deriv] * math.factorial(deriv) / (delta ** deriv)
    saida = np.empty(len(y), dtype=float)
    saida[m:len(y) - m] = np.convolve(y, coef[::-1], mode='valid')

    def _borda(trecho, posicoes):
        c = np.polynomial.polynomial.polyfit(np.arange(janela, dtype=float), trecho, ordem_pol)
        return np.polynomial.polynomial.polyval(
            posicoes, np.polynomial.polynomial.polyder(c, deriv)) / (delta ** deriv)

    saida[:m] = _borda(y[:janela], np.arange(m, dtype=float))
    saida[len(y) - m:] = _borda(y[-janela:], np.arange(janela - m, janela, dtype=float))
    return saida


def preprocessar_sinal(sinal: np.ndarray, fps: float, fps_alvo: float = FPS_ALVO):
    """
    Pré-processamento obrigatório antes do Jerk:
      1) filtro passa-baixa Butterworth (fase zero) para remover ruído;
      2) normalização temporal: reamostragem para uma taxa comum (fps_alvo),
         tornando comparáveis o KinesiOS (28 FPS) e o Brainn_XR (24 FPS).
    Retorna (tempo_normalizado, sinal_filtrado_normalizado).
    """
    y = np.asarray(sinal, dtype=float)
    n = len(y)
    if n < 2 or fps <= 0:
        return np.arange(n) / max(fps, 1.0), y

    corte = min(CORTE_PASSA_BAIXA_HZ, 0.45 * fps)  # sempre abaixo de Nyquist
    y = _filtro_passa_baixa_fase_zero(y, fps, corte)

    t_orig = np.arange(n) / fps
    t_novo = np.arange(0.0, t_orig[-1], 1.0 / fps_alvo)
    return t_novo, np.interp(t_novo, t_orig, y)


def calcular_jerk_rms(sinal: pd.Series, fps: float, picos: list[dict],
                      fps_alvo: float = FPS_ALVO) -> dict:
    """
    Jerk RMS = raiz da média dos quadrados de d³θ/dt³ (graus/s³), calculado:
      - SOMENTE após filtragem antirruído + normalização temporal;
      - RESTRITO às janelas dos picos de movimento ativo (repouso é ignorado,
        para não diluir a medida).
    Retorna NaN (rms) se não houver picos ou amostras suficientes.
    """
    vazio = {'rms': float('nan'), 'n_amostras': 0}
    if not picos or fps <= 0 or fps_alvo <= 0:
        return vazio

    t, y = preprocessar_sinal(sinal.values, fps, fps_alvo)
    if len(y) < JANELA_SAVGOL:
        return vazio

    # Terceira derivada via Savitzky-Golay, implementada só com numpy
    jerk = _derivada_savgol(y, JANELA_SAVGOL, ORDEM_POLINOMIO, 3, 1.0 / fps_alvo)

    # Máscara das janelas de movimento ativo, mapeadas para o eixo normalizado
    mascara = np.zeros(len(t), dtype=bool)
    for p in picos:
        i0 = int(np.searchsorted(t, p['inicio_seg'], side='left'))
        i1 = int(np.searchsorted(t, p['fim_seg'], side='right'))
        mascara[i0:i1] = True

    if not mascara.any():
        return vazio
    valores = jerk[mascara]
    return {'rms': float(np.sqrt(np.mean(valores ** 2))), 'n_amostras': int(mascara.sum())}


def calcular_oscilacao_ombro(dados: pd.Series) -> dict:
    """Resumo da oscilação do ombro: amplitude pico-a-pico, desvio padrão e média."""
    if len(dados) == 0:
        return {'pico_a_pico': 0.0, 'desvio_padrao': 0.0, 'media': 0.0}
    return {
        'pico_a_pico':   float(dados.max() - dados.min()),
        'desvio_padrao': float(dados.std(ddof=0)),
        'media':         float(dados.mean()),
    }


# =============================================================================
# 5. RESUMO COMPLETO DA SESSÃO
# =============================================================================

def gerar_resumo_sessao(df: pd.DataFrame, fps: float, limiares: dict) -> dict:
    """
    Ponto de entrada principal: recebe o DataFrame e o limiar clínico do joelho
    ({'joelho': 30.0}) e devolve picos, amplitudes, consistência, Índice de
    Simetria de Robinson, Jerk RMS e oscilação dos ombros (se disponível).
    """
    limiar_joelho = limiares.get('joelho', 30.0)
    lados = {'joelho_esq': COL_JOELHO_ESQ, 'joelho_dir': COL_JOELHO_DIR}

    picos      = {k: extrair_picos_marcha(df[c], fps, limiar_joelho) for k, c in lados.items()}
    amplitude  = {k: calcular_amplitude_sessao(df[c]) for k, c in lados.items()}
    consistencia = {k: calcular_consistencia_temporal(picos[k]) for k in lados}
    jerk       = {k: calcular_jerk_rms(df[c], fps, picos[k]) for k, c in lados.items()}
    simetria   = calcular_indice_simetria_robinson(picos['joelho_dir'], picos['joelho_esq'])

    ombro = None
    if tem_ombros(df):
        ombro = {'ombro_esq': calcular_oscilacao_ombro(df[COL_OMBRO_ESQ]),
                 'ombro_dir': calcular_oscilacao_ombro(df[COL_OMBRO_DIR])}

    return {
        'picos':        picos,
        'amplitude':    amplitude,
        'consistencia': consistencia,
        'jerk':         jerk,
        'simetria':     simetria,
        'ombro':        ombro,
        'tempo_execucao_seg': float(len(df) / fps),
        'n_frames': len(df),
        'fps':      fps,
        'limiares': limiares,
        'fonte':    df.attrs.get('fonte', 'desconhecida'),
        'arquivo':  df.attrs.get('arquivo', ''),
    }


# =============================================================================
# 6. TABELAS COMPARTILHADAS (tela e exportação saem da MESMA fonte)
# =============================================================================

_NOME_LADO = {'joelho_esq': 'Esquerdo', 'joelho_dir': 'Direito'}

# (chave no JSON, cabeçalho legível com unidade) — ordem das colunas na tela e no Excel
METRICAS_LADO = [
    ('amplitude_media_graus',        'Amplitude média (°)'),
    ('amplitude_maxima_graus',       'Amplitude máxima (°)'),
    ('indice_simetria_robinson_pct', 'Índice de Simetria de Robinson (%)'),
    ('jerk_rms_graus_por_s3',        'Jerk RMS (°/s³)'),
    ('n_picos',                      'Nº de picos'),
    ('cv_duracao_pct',               'CV da duração (%)'),
    ('duracao_media_picos_s',        'Duração média dos picos (s)'),
    ('desvio_duracao_picos_s',       'Desvio da duração dos picos (s)'),
    ('amplitude_media_picos_graus',  'Amplitude média dos picos (°)'),
]

METRICAS_OMBRO = [
    ('pico_a_pico_graus',   'Pico a pico (°)'),
    ('desvio_padrao_graus', 'Desvio padrão (°)'),
    ('media_graus',         'Média (°)'),
]

# Cabeçalhos legíveis para o Excel (chaves do JSON -> título da coluna)
CABECALHOS = {
    **dict(METRICAS_LADO), **dict(METRICAS_OMBRO),
    'lado': 'Lado', 'sessao': 'Sessão', 'pico': 'Pico',
    'tempo_pico_s': 'Tempo do pico (s)', 'valor_pico_graus': 'Amplitude do pico (°)',
    'inicio_s': 'Início (s)', 'fim_s': 'Fim (s)', 'duracao_s': 'Duração (s)',
    'metrica': 'Métrica', 'inicio': 'Início', 'final': 'Final', 'variacao': 'Variação (Final − Início)',
    'tempo_total_execucao_s': 'Duração total (s)', 'software_origem': 'Software de origem',
    'arquivo_origem': 'Arquivo de origem', 'modo_analise': 'Modo de análise',
    'lado_analisado': 'Lado analisado', 'gerado_em': 'Gerado em', 'fps': 'FPS',
    'n_frames': 'Nº de frames', 'limiar_joelho_graus': 'Limiar do joelho (°)',
    'jerk_pre_processamento': 'Pré-processamento do Jerk',
}


def _val(x, casas: int = 2):
    """Número arredondado; None/NaN viram NaN (célula vazia)."""
    if x is None:
        return float('nan')
    x = float(x)
    return float('nan') if math.isnan(x) else round(x, casas)


def _metricas_do_lado(resumo: dict, chave: str, n_lados: int) -> dict:
    """Todas as métricas de um lado, com as chaves de METRICAS_LADO."""
    amp, cons, jk = resumo['amplitude'][chave], resumo['consistencia'][chave], resumo['jerk'][chave]
    x_picos = amplitude_media_dos_picos(resumo['picos'][chave])
    return {
        'amplitude_media_graus':        _val(amp['media']),
        'amplitude_maxima_graus':       _val(amp['maxima']),
        # Robinson compara os dois lados: só existe na análise bilateral
        'indice_simetria_robinson_pct': _val(resumo['simetria']['si_pct']) if n_lados == 2 else float('nan'),
        'jerk_rms_graus_por_s3':        _val(jk['rms']),
        'n_picos':                      int(cons['n_picos']),
        'cv_duracao_pct':               _val(cons['cv_duracao']),
        'duracao_media_picos_s':        _val(cons['media_duracao'], 3),
        'desvio_duracao_picos_s':       _val(cons['desvio_duracao'], 3),
        'amplitude_media_picos_graus':  _val(x_picos),
    }


def tabela_resumo_lados(resumo: dict, chaves: list) -> pd.DataFrame:
    """Tabela 'Resumo por lado' (índice = Lado), usada na tela e igual à do arquivo exportado."""
    linhas = []
    for k in chaves:
        m = _metricas_do_lado(resumo, k, len(chaves))
        linhas.append({'Lado': _NOME_LADO[k], **{cab: m[ch] for ch, cab in METRICAS_LADO}})
    return pd.DataFrame(linhas).set_index('Lado')


def tabela_ombros(resumo: dict):
    """Tabela de oscilação dos ombros (índice Esquerdo/Direito) ou None se não houver dados."""
    o = resumo.get('ombro')
    if not o:
        return None
    linhas = {}
    for nome, k in (('Esquerdo', 'ombro_esq'), ('Direito', 'ombro_dir')):
        linhas[nome] = {cab: _val(o[k][ch.replace('_graus', '')]) for ch, cab in METRICAS_OMBRO}
    return pd.DataFrame(linhas).T


def tabela_comparativa(res_i: dict, res_f: dict, chaves: list) -> pd.DataFrame:
    """Tabela Início × Final × Variação (índice = Métrica), usada na tela e no arquivo."""
    linhas = [{'Métrica': 'Duração total (s)', 'Início': _val(res_i['tempo_execucao_seg']),
               'Final': _val(res_f['tempo_execucao_seg'])}]
    if len(chaves) == 2:
        linhas.append({'Métrica': 'Índice de Simetria de Robinson (%)',
                       'Início': _val(res_i['simetria']['si_pct']), 'Final': _val(res_f['simetria']['si_pct'])})
    itens = [('amplitude_media_graus', 'Amplitude média (°)'), ('amplitude_maxima_graus', 'Amplitude máxima (°)'),
             ('jerk_rms_graus_por_s3', 'Jerk RMS (°/s³)'), ('cv_duracao_pct', 'CV da duração (%)'),
             ('n_picos', 'Nº de picos'), ('duracao_media_picos_s', 'Duração média dos picos (s)'),
             ('amplitude_media_picos_graus', 'Amplitude média dos picos (°)')]
    for k in chaves:
        mi, mf = _metricas_do_lado(res_i, k, len(chaves)), _metricas_do_lado(res_f, k, len(chaves))
        for ch, nome in itens:
            linhas.append({'Métrica': f'Joelho {_NOME_LADO[k]} — {nome}', 'Início': mi[ch], 'Final': mf[ch]})
    t = pd.DataFrame(linhas)
    t['Variação (Final − Início)'] = (t['Final'] - t['Início']).round(2)
    return t.set_index('Métrica')


# =============================================================================
# 7. EXPORTAÇÃO ESTRUTURADA (JSON / EXCEL)
# =============================================================================

def _limpar(obj):
    """Converte NaN/numpy em tipos serializáveis (NaN -> None)."""
    if isinstance(obj, dict):
        return {k: _limpar(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_limpar(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if math.isnan(float(obj)) else float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    return obj


def _metadados(resumo: dict, modo: str, lado: str | None) -> dict:
    return {
        'tempo_total_execucao_s': round(resumo['tempo_execucao_seg'], 3),
        'software_origem':        resumo['fonte'],
        'arquivo_origem':         resumo.get('arquivo', ''),
        'modo_analise':           modo,
        'lado_analisado':         lado if lado else 'Ambos',
        'gerado_em':              pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
        'fps':                    resumo['fps'],
        'n_frames':               resumo['n_frames'],
        'limiar_joelho_graus':    resumo['limiares'].get('joelho'),
        'jerk_pre_processamento': (f"Butterworth passa-baixa {CORTE_PASSA_BAIXA_HZ:g} Hz "
                                   f"(ordem {ORDEM_BUTTERWORTH}) + reamostragem a {FPS_ALVO:g} Hz; "
                                   "janelas de movimento ativo apenas"),
    }


def _linhas_metricas(resumo, chaves, sessao=None):
    out = []
    for k in chaves:
        linha = {'lado': _NOME_LADO[k], **_metricas_do_lado(resumo, k, len(chaves))}
        out.append({'sessao': sessao, **linha} if sessao else linha)
    return out


def _linhas_ombros(resumo, sessao=None):
    t = tabela_ombros(resumo)
    if t is None:
        return []
    out = []
    for lado, linha in t.iterrows():
        d = {'lado': lado, **{ch: linha[cab] for ch, cab in METRICAS_OMBRO}}
        out.append({'sessao': sessao, **d} if sessao else d)
    return out


def _linhas_picos(resumo, chaves, sessao=None):
    fps, out = resumo['fps'], []
    for k in chaves:
        for p in resumo['picos'][k]:
            d = {'lado': _NOME_LADO[k], 'pico': p['pico'],
                 'tempo_pico_s': round(p['frame_pico'] / fps, 3),
                 'valor_pico_graus': round(p['amplitude_maxima'], 2),
                 'inicio_s': round(p['inicio_seg'], 3), 'fim_s': round(p['fim_seg'], 3),
                 'duracao_s': round(p['duracao'], 3)}
            out.append({'sessao': sessao, **d} if sessao else d)
    return out


def _chaves_do_lado(lado):
    return [k for k in _NOME_LADO if lado is None or _NOME_LADO[k] == lado]


def construir_relatorio(resumo: dict, modo_analise: str, lado: str | None = None) -> dict:
    """
    Relatório de UMA sessão com tudo o que a tela mostra:
      - metadados (duração total, software, arquivo, modo, lado, FPS, limiar, pré-processamento);
      - métricas por lado (amplitudes, Robinson, Jerk RMS, nº de picos, CV, duração e amplitude dos picos);
      - oscilação dos ombros (se o arquivo tiver ombros);
      - valor e tempo de cada pico de flexão do joelho.
    'lado' ('Esquerdo'/'Direito') restringe ao membro exercitado (unilateral); None = os dois.
    """
    chaves = _chaves_do_lado(lado)
    return _limpar({
        'tipo': 'sessao',
        'metadados': _metadados(resumo, modo_analise, lado),
        'metricas_por_lado': _linhas_metricas(resumo, chaves),
        'oscilacao_ombros': _linhas_ombros(resumo),
        'picos_flexao_joelho': _linhas_picos(resumo, chaves),
    })


def construir_relatorio_comparacao(res_i: dict, res_f: dict, modo_analise: str,
                                   lado: str | None = None) -> dict:
    """
    Relatório da comparação Início × Final: a mesma tabela comparativa da tela (com variação),
    metadados das duas sessões e, por sessão, métricas por lado, ombros e picos.
    """
    chaves = _chaves_do_lado(lado)
    comp = tabela_comparativa(res_i, res_f, chaves).reset_index()
    comparacao = [{'metrica': r['Métrica'], 'inicio': r['Início'], 'final': r['Final'],
                   'variacao': r['Variação (Final − Início)']} for _, r in comp.iterrows()]
    return _limpar({
        'tipo': 'comparacao',
        'metadados': {'modo_analise': modo_analise, 'lado_analisado': lado if lado else 'Ambos',
                      'inicio': _metadados(res_i, modo_analise, lado),
                      'final':  _metadados(res_f, modo_analise, lado)},
        'comparacao': comparacao,
        'metricas_por_lado': _linhas_metricas(res_i, chaves, 'Início') + _linhas_metricas(res_f, chaves, 'Final'),
        'oscilacao_ombros': _linhas_ombros(res_i, 'Início') + _linhas_ombros(res_f, 'Final'),
        'picos_flexao_joelho': _linhas_picos(res_i, chaves, 'Início') + _linhas_picos(res_f, chaves, 'Final'),
    })


def relatorio_para_json(relatorio: dict) -> bytes:
    return json.dumps(relatorio, ensure_ascii=False, indent=2).encode('utf-8')


def _cab(chave: str) -> str:
    return CABECALHOS.get(chave, chave)


def _tabela_excel(registros: list) -> pd.DataFrame:
    return pd.DataFrame(registros).rename(columns=_cab)


def relatorio_para_excel(relatorio: dict) -> bytes:
    """
    Gera o .xlsx com abas legíveis (cabeçalhos em português, unidade na coluna, só números nas células):
    sessão: Metadados | Metricas_por_lado | Ombros* | Picos_joelho
    comparação: Comparacao | Metadados | Metricas_por_lado | Ombros* | Picos_joelho   (* só se houver ombros)
    """
    meta = relatorio['metadados']
    abas = {}
    if relatorio.get('tipo') == 'comparacao':
        abas['Comparacao'] = _tabela_excel(relatorio['comparacao'])
        campos = list(meta['inicio'])
        abas['Metadados'] = pd.DataFrame({'Campo': [_cab(c) for c in campos],
                                          'Início': [meta['inicio'][c] for c in campos],
                                          'Final':  [meta['final'][c] for c in campos]})
    else:
        abas['Metadados'] = pd.DataFrame({'Campo': [_cab(c) for c in meta], 'Valor': list(meta.values())})
    abas['Metricas_por_lado'] = _tabela_excel(relatorio['metricas_por_lado'])
    if relatorio.get('oscilacao_ombros'):
        abas['Ombros'] = _tabela_excel(relatorio['oscilacao_ombros'])
    abas['Picos_joelho'] = _tabela_excel(relatorio['picos_flexao_joelho'])

    return _abas_para_excel(abas)


def _abas_para_excel(abas: dict) -> bytes:
    """Grava {nome_da_aba: DataFrame} num .xlsx (cabeçalho em negrito, painel congelado, larguras)."""
    from openpyxl.styles import Font
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        for nome, tabela in abas.items():
            tabela.to_excel(writer, sheet_name=nome, index=False)
            ws = writer.sheets[nome]
            ws.freeze_panes = 'A2'
            for c in ws[1]:
                c.font = Font(bold=True)
            for coluna in ws.columns:  # largura de coluna legível
                largura = max(len(str(c.value)) if c.value is not None else 0 for c in coluna)
                ws.column_dimensions[coluna[0].column_letter].width = min(largura + 2, 70)
    return buffer.getvalue()


# =============================================================================
# 8. EVOLUÇÃO ENTRE SESSÕES (UM PARTICIPANTE E GRUPO)
# =============================================================================
# Cada sessão vira UMA linha de números (linha_evolucao). Os gráficos, as tabelas
# e os arquivos exportados saem das mesmas linhas, como nas outras seções.

SEP_LADO = '__'   # 'coluna__Esquerdo' / 'coluna__Direito'

# (id da métrica, rótulo com unidade, escopo)
#   'lado'   -> uma série por joelho (as duas no bilateral; só a escolhida no unilateral)
#   'ombro'  -> uma série por ombro (sempre as duas: é a postura do corpo todo)
#   'global' -> uma série só (Robinson compara os dois joelhos: só existe no bilateral)
METRICAS_EVOLUCAO = [
    ('amplitude_media_picos_graus',  'Amplitude média dos picos (°)',           'lado'),
    ('amplitude_maxima_graus',       'Amplitude máxima (°)',                    'lado'),
    ('amplitude_media_graus',        'Amplitude média da sessão (°)',           'lado'),
    ('indice_simetria_robinson_pct', 'Índice de Simetria de Robinson (%)',      'global'),
    ('jerk_rms_graus_por_s3',        'Jerk RMS (°/s³)',                         'lado'),
    ('cv_duracao_pct',               'CV da duração (%)',                       'lado'),
    ('n_picos',                      'Nº de picos',                             'lado'),
    ('duracao_media_picos_s',        'Duração média dos picos (s)',             'lado'),
    ('ombro_pico_a_pico_graus',      'Oscilação do ombro — pico a pico (°)',    'ombro'),
    ('ombro_desvio_padrao_graus',    'Oscilação do ombro — desvio padrão (°)',  'ombro'),
    ('duracao_total_s',              'Duração total da sessão (s)',             'global'),
]
_ROTULO_EVO = {m: r for m, r, _ in METRICAS_EVOLUCAO}
_ESCOPO_EVO = {m: e for m, _, e in METRICAS_EVOLUCAO}
_METRICAS_JOELHO = [m for m, _, e in METRICAS_EVOLUCAO if e == 'lado']
_NOMES_OMBRO = (('ombro_esq', 'Esquerdo'), ('ombro_dir', 'Direito'))


def ordenar_nomes_naturalmente(nomes: list) -> list:
    """Ordem 'natural' (sessao2 antes de sessao10; datas no nome ficam em ordem cronológica)."""
    import re
    def chave(n):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', str(n))]
    return sorted(nomes, key=chave)


def linha_evolucao(resumo: dict, ordem: int) -> dict:
    """Linha numérica de uma sessão (todas as métricas dos dois joelhos, Robinson e ombros)."""
    linha = {
        'sessao': int(ordem),
        'arquivo': resumo.get('arquivo', ''),
        'limiar_joelho_graus': resumo['limiares'].get('joelho'),
        'duracao_total_s': _val(resumo['tempo_execucao_seg']),
        'indice_simetria_robinson_pct': _val(resumo['simetria']['si_pct']),
    }
    for k, nome in _NOME_LADO.items():
        m = _metricas_do_lado(resumo, k, 2)
        for ch in _METRICAS_JOELHO:
            linha[f'{ch}{SEP_LADO}{nome}'] = m[ch]
    for k, nome in _NOMES_OMBRO:
        o = (resumo.get('ombro') or {}).get(k)
        for ch in ('pico_a_pico_graus', 'desvio_padrao_graus'):
            linha[f'ombro_{ch}{SEP_LADO}{nome}'] = _val(o[ch.replace('_graus', '')]) if o else float('nan')
    return linha


def tabela_evolucao_longa(participantes: dict) -> pd.DataFrame:
    """
    {nome: {'limiar': x, 'linhas': [linha_evolucao, ...]}} -> DataFrame com uma linha por
    (participante, sessão) e colunas numéricas brutas (chaves de linha_evolucao).
    """
    registros = []
    for nome, dados in participantes.items():
        for linha in dados['linhas']:
            registros.append({'participante': nome, **linha})
    df = pd.DataFrame(registros)
    return df.sort_values(['participante', 'sessao']).reset_index(drop=True) if not df.empty else df


def series_da_metrica(metrica: str, bilateral: bool = True, lado: str | None = None) -> list:
    """
    Séries (coluna, rótulo) que representam a métrica no gráfico.
    Devolve [] quando a métrica não se aplica (Robinson no unilateral).
    """
    rotulo, escopo = _ROTULO_EVO[metrica], _ESCOPO_EVO[metrica]
    if escopo == 'global':
        if metrica == 'indice_simetria_robinson_pct' and not bilateral:
            return []
        return [(metrica, rotulo, None)]
    if escopo == 'lado' and not bilateral:
        lados = [lado or 'Esquerdo']
    else:
        lados = ['Esquerdo', 'Direito']
    return [(f'{metrica}{SEP_LADO}{n}', f'{rotulo} — {n}', n) for n in lados]


def metricas_disponiveis(bilateral: bool = True) -> list:
    """Ids das métricas que fazem sentido no modo (Robinson só no bilateral)."""
    return [m for m, _, _ in METRICAS_EVOLUCAO if bilateral or m != 'indice_simetria_robinson_pct']


def rotulo_metrica(metrica: str) -> str:
    return _ROTULO_EVO[metrica]


def agregar_grupo(longa: pd.DataFrame, coluna: str) -> pd.DataFrame:
    """Média, desvio padrão amostral e nº de participantes por sessão (ignora valores indefinidos)."""
    if longa.empty or coluna not in longa:
        return pd.DataFrame(columns=['Sessão', 'Média', 'Desvio padrão', 'Nº de participantes'])
    g = longa.groupby('sessao')[coluna].agg(['mean', 'std', 'count']).reset_index()
    g.columns = ['Sessão', 'Média', 'Desvio padrão', 'Nº de participantes']
    g['Média'] = g['Média'].round(2)
    g['Desvio padrão'] = g['Desvio padrão'].round(2)
    return g


def tabela_evolucao_exibicao(longa: pd.DataFrame, bilateral: bool = True, lado: str | None = None,
                             participante: str | None = None) -> pd.DataFrame:
    """Tabela legível (só números, unidade no cabeçalho): uma linha por participante × sessão."""
    if longa.empty:
        return pd.DataFrame()
    d = longa if participante is None else longa[longa['participante'] == participante]
    saida = pd.DataFrame({'Participante': d['participante'], 'Sessão': d['sessao'],
                          'Limiar do joelho (°)': d['limiar_joelho_graus']})
    for m in metricas_disponiveis(bilateral):
        for coluna, rotulo, _ in series_da_metrica(m, bilateral, lado):
            saida[rotulo] = d[coluna]
    return saida.reset_index(drop=True)


def tabela_grupo_exibicao(longa: pd.DataFrame, bilateral: bool = True, lado: str | None = None) -> pd.DataFrame:
    """Média/desvio/n do grupo por sessão, para todas as séries (formato longo, numérico)."""
    partes = []
    for m in metricas_disponiveis(bilateral):
        for coluna, rotulo, _ in series_da_metrica(m, bilateral, lado):
            g = agregar_grupo(longa, coluna)
            g.insert(0, 'Métrica', rotulo)
            partes.append(g)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def _meta_evolucao(participantes: dict, modo: str, lado: str | None) -> dict:
    return {
        'modo_analise': modo,
        'lado_analisado': lado if lado else 'Ambos',
        'n_participantes': len(participantes),
        'sessoes_por_participante': {n: len(d['linhas']) for n, d in participantes.items()},
        'limiar_joelho_graus_por_participante': {n: d.get('limiar') for n, d in participantes.items()},
        'gerado_em': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
        'jerk_pre_processamento': (f"Butterworth passa-baixa {CORTE_PASSA_BAIXA_HZ:g} Hz "
                                   f"(ordem {ORDEM_BUTTERWORTH}) + reamostragem a {FPS_ALVO:g} Hz; "
                                   "janelas de movimento ativo apenas"),
    }


def construir_relatorio_evolucao(participantes: dict, modo: str, lado: str | None = None) -> dict:
    """Relatório de evolução: metadados, tabela por participante × sessão e média/desvio do grupo."""
    bilateral = lado is None
    longa = tabela_evolucao_longa(participantes)
    evo = tabela_evolucao_exibicao(longa, bilateral, lado)
    grupo = tabela_grupo_exibicao(longa, bilateral, lado)
    return _limpar({
        'tipo': 'evolucao',
        'metadados': _meta_evolucao(participantes, modo, lado),
        'evolucao_por_participante': evo.to_dict(orient='records'),
        'media_do_grupo_por_sessao': grupo.to_dict(orient='records'),
    })


def evolucao_para_excel(relatorio: dict) -> bytes:
    """Excel da evolução: Metadados | Evolucao | Media_do_grupo (só números nas células)."""
    meta = relatorio['metadados']
    simples = {c: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
               for c, v in meta.items()}
    abas = {
        'Metadados': pd.DataFrame({'Campo': list(simples), 'Valor': list(simples.values())}),
        'Evolucao': pd.DataFrame(relatorio['evolucao_por_participante']),
        'Media_do_grupo': pd.DataFrame(relatorio['media_do_grupo_por_sessao']),
    }
    return _abas_para_excel(abas)
