"""Detección de sustitución LSB por ataque chi-cuadrado sobre los planos LSB.

Modelo (Westfeld & Pfitzmann, *Attacks on Steganographic Systems*, 1999): la
sustitución LSB aleatoriza el bit menos significativo de cada muestra, de modo
que los pares de valores ``(2k, 2k+1)`` tienden a la media aritmética de sus
frecuencias. El estadístico mide la distancia entre el histograma observado y
ese modelo; con ``2**8 - 1`` grados de libertad se obtiene el valor ``p`` de la
cola superior, que tiende a 1 cuando la imagen completa está sustituida y a 0
cuando el plano LSB conserva la estructura de una imagen natural.

La misma formulación la usa la implementación de referencia ``sealwatch``
(Universidad de Innsbruck) para su ataque ``chi2``: media por par, pares con
media <= 4 descartados (Fridrich, apéndice D) y ``df = 255``.

El ataque completo (el que localiza la carga) se obtiene recorriendo prefijos
de la imagen: el valor ``p`` se mantiene alto mientras el prefijo cae dentro de
la zona sustituida y se derrumba al salir de ella. De ahí se estima la tasa de
sustitución, que es el indicador continuo usado como ``anomaly_score``.

El resultado nunca es concluyente: la prueba no puede demostrar la ausencia de
datos ocultos y una imagen sintética o con ruido uniforme puede imitar el
patrón de una imagen sustituida.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from PIL import Image

TECHNIQUE: Final = "lsb_statistical_analysis"

STATUS_CLEAN: Final = "sin_indicios"
STATUS_SUSPICIOUS: Final = "sospechosos"
STATUS_INCONCLUSIVE: Final = "no_concluyentes"
STATUS_ERROR: Final = "error"

ACTION_NONE: Final = "ninguna"
ACTION_WARNING: Final = "advertencia"
ACTION_QUARANTINE: Final = "cuarentena"
ACTION_REJECTION: Final = "rechazo"

CHI_SQUARE_DEGREES_OF_FREEDOM: Final = 255
MIN_PAIR_AVERAGE: Final = 4.0
RATE_BANDS: Final = 64
PREFIX_PVALUE_CUTOFF: Final = 0.5
MIN_PREFIX_SAMPLES: Final = 4096
LSB_RATIO_TOLERANCE: Final = 0.15

_GAMMA_EPSILON = 1e-15
_GAMMA_MAX_ITERATIONS = 1000
_GAMMA_TINY = 1e-300

_SUPPORTED_MODES = frozenset({"RGB", "RGBA", "L", "LA", "P"})
_UNSUPPORTED_DEPTH_MODES = frozenset({"1", "I", "I;16", "I;16B", "I;16L", "I;16N", "F"})


@dataclass(frozen=True)
class HistogramStatistics:
    statistic: float
    pvalue: float
    retained_pairs: int
    samples: int
    ones: int


@dataclass(frozen=True)
class AnalysisOutcome:
    status: str
    action: str
    indicators: dict[str, int | float]
    limitations: str


class UnsupportedDepth(Exception):
    """Modo de imagen que el analizador LSB no procesa (p. ej. 16 bits)."""


def _regularized_upper_gamma(shape: float, value: float) -> float:
    """Q(shape, value) = 1 - P(shape, value), serie/ fracción continuada."""
    if value <= 0.0:
        return 1.0
    if shape <= 0.0:
        return 1.0
    if value < shape + 1.0:
        return 1.0 - _lower_gamma_series(shape, value)
    return _upper_gamma_fraction(shape, value)


def _lower_gamma_series(shape: float, value: float) -> float:
    log_gamma = math.lgamma(shape)
    term = 1.0 / shape
    total = term
    denominator = shape
    for _ in range(_GAMMA_MAX_ITERATIONS):
        denominator += 1.0
        term *= value / denominator
        total += term
        if abs(term) < abs(total) * _GAMMA_EPSILON:
            break
    return total * math.exp(-value + shape * math.log(value) - log_gamma)


def _upper_gamma_fraction(shape: float, value: float) -> float:
    log_gamma = math.lgamma(shape)
    denominator = value + 1.0 - shape
    inverse = 1.0 / denominator
    numerator_c = 1.0 / _GAMMA_TINY
    factor = inverse
    for iteration in range(1, _GAMMA_MAX_ITERATIONS):
        coefficient = -iteration * (iteration - shape)
        denominator += 2.0
        inverse = coefficient * inverse + denominator
        if abs(inverse) < _GAMMA_TINY:
            inverse = _GAMMA_TINY
        numerator_c = denominator + coefficient / numerator_c
        if abs(numerator_c) < _GAMMA_TINY:
            numerator_c = _GAMMA_TINY
        inverse = 1.0 / inverse
        delta = inverse * numerator_c
        factor *= delta
        if abs(delta - 1.0) < _GAMMA_EPSILON:
            break
    return math.exp(-value + shape * math.log(value) - log_gamma) * factor


def chi_square_survival(statistic: float, degrees_of_freedom: int = CHI_SQUARE_DEGREES_OF_FREEDOM) -> float:
    """P(X >= statistic) para X ~ chi-cuadrado (equivalente a chi2.sf)."""
    if statistic <= 0.0:
        return 1.0
    return _regularized_upper_gamma(degrees_of_freedom / 2.0, statistic / 2.0)


def histogram_statistics(histogram: Sequence[int]) -> HistogramStatistics:
    """Estadístico chi-cuadrado y valor p de un histograma de 256 bins."""
    if len(histogram) != 256:
        raise ValueError("el histograma debe tener 256 bins")
    statistic = 0.0
    retained_pairs = 0
    samples = 0
    ones = 0
    for pair in range(128):
        even = int(histogram[2 * pair])
        odd = int(histogram[2 * pair + 1])
        samples += even + odd
        ones += odd
        average = (even + odd) / 2.0
        if average > MIN_PAIR_AVERAGE:
            statistic += (even - average) ** 2 / average
            statistic += (odd - average) ** 2 / average
            retained_pairs += 1
    return HistogramStatistics(
        statistic=statistic,
        pvalue=chi_square_survival(statistic),
        retained_pairs=retained_pairs,
        samples=samples,
        ones=ones,
    )


def _prepare_image(image: Image.Image) -> tuple[Image.Image, list[int]]:
    mode = image.mode
    if mode in _UNSUPPORTED_DEPTH_MODES:
        raise UnsupportedDepth(mode)
    if mode in _SUPPORTED_MODES:
        channels = [0, 1, 2] if mode in ("RGB", "RGBA") else [0]
        return image, channels
    return image.convert("RGB"), [0, 1, 2]


def _estimated_embedding_rate(image: Image.Image, channels: Sequence[int], samples: int) -> float:
    """Tasa de sustitución estimada recorriendo prefijos de filas de la imagen."""
    if samples < 4 * MIN_PREFIX_SAMPLES:
        return 0.0
    width, height = image.size
    bands = min(RATE_BANDS, max(1, height))
    band_height = max(1, height // bands)
    cumulative = [0] * 256
    seen = 0
    rate = 0.0
    for index in range(bands):
        top = index * band_height
        bottom = height if index == bands - 1 else min(height, top + band_height)
        if bottom <= top:
            continue
        strip = image.crop((0, top, width, bottom))
        strip_histogram = strip.histogram()
        strip.close()
        for channel in channels:
            offset = channel * 256
            for value in range(256):
                cumulative[value] += strip_histogram[offset + value]
        seen += (bottom - top) * width * len(channels)
        if seen < MIN_PREFIX_SAMPLES:
            continue
        if histogram_statistics(cumulative).pvalue >= PREFIX_PVALUE_CUTOFF:
            rate = (index + 1) / bands
    return rate


def _clean_limitations(pvalue: float, threshold: float) -> str:
    return (
        "Resultado indicativo, no concluyente: el histograma del plano LSB no es "
        f"compatible con una sustitución LSB completa (p={pvalue:.3g} < umbral {threshold:g}). "
        "Una carga pequeña o distribuida sobre pocas muestras puede no ser detectable "
        "con esta técnica; la ausencia de indicios no demuestra que la imagen esté limpia."
    )


def _suspicious_limitations(pvalue: float, rate: float) -> str:
    return (
        "Resultado indicativo, no concluyente: el plano LSB es compatible con una "
        f"sustitución LSB en aproximadamente el {rate:.0%} de la imagen (p={pvalue:.3g}). "
        "Imágenes sintéticas, ruido uniforme o dithering pueden producir el mismo patrón. "
        "Un indicio no prueba la existencia de datos ocultos: requiere inspección manual."
    )


def _inconclusive_limitations(reason: str) -> str:
    return (
        f"Evidencia insuficiente para clasificar la imagen: {reason}. "
        "El resultado no permite afirmar ni descartar la existencia de datos ocultos; "
        "se recomienda revisión manual con otra técnica de esteganoanálisis."
    )


def error_outcome(threshold: float) -> AnalysisOutcome:
    """Resultado controlado cuando el analizador no puede completar la prueba."""
    return AnalysisOutcome(
        status=STATUS_ERROR,
        action=ACTION_REJECTION,
        indicators={"anomaly_score": 0.0, "threshold": threshold},
        limitations=(
            "El analizador no pudo completar la prueba estadística sobre el archivo "
            "(decodifica como imagen, pero no es procesable). El archivo se conserva en "
            "cuarentena; se requiere revisión manual."
        ),
    )


def analyze_image(
    image: Image.Image,
    *,
    threshold: float,
    min_pixels: int,
    min_palette_colors: int,
) -> AnalysisOutcome:
    """Aplica el ataque chi-cuadrado y clasifica según la tabla del contrato 6 §4."""
    width, height = image.size
    pixels = width * height
    try:
        prepared, channels = _prepare_image(image)
    except UnsupportedDepth as exc:
        return AnalysisOutcome(
            status=STATUS_INCONCLUSIVE,
            action=ACTION_WARNING,
            indicators={
                "anomaly_score": 0.0,
                "threshold": threshold,
                "pixels_analysed": pixels,
                "channels_analysed": 0,
            },
            limitations=_inconclusive_limitations(
                f"la profundidad de color del modo {exc} no está soportada por el analizador LSB"
            ),
        )

    histogram = prepared.histogram()
    channel_histograms = [histogram[channel * 256 : (channel + 1) * 256] for channel in channels]
    statistics = [histogram_statistics(values) for values in channel_histograms]
    with_samples = [stats for stats in statistics if stats.samples > 0]
    if not with_samples:
        return error_outcome(threshold)

    pooled = [sum(values) for values in zip(*channel_histograms)]
    pooled_statistics = histogram_statistics(pooled)

    most_suspicious = max(with_samples, key=lambda stats: stats.pvalue)
    rate = _estimated_embedding_rate(prepared, channels, pooled_statistics.samples)
    anomaly_score = round(max(most_suspicious.pvalue, rate), 6)
    ones_ratio = pooled_statistics.ones / pooled_statistics.samples if pooled_statistics.samples else 0.0
    distinct_values = sum(1 for count in pooled if count > 0)

    indicators: dict[str, int | float] = {
        "anomaly_score": anomaly_score,
        "threshold": threshold,
        "chi_square_pvalue": float(f"{most_suspicious.pvalue:.6g}"),
        "chi_square_statistic": round(most_suspicious.statistic, 3),
        "estimated_embedding_rate": round(rate, 4),
        "lsb_ones_ratio": round(ones_ratio, 6),
        "pixels_analysed": pixels,
        "channels_analysed": len(channels),
        "distinct_values": distinct_values,
        "pair_bins_retained": pooled_statistics.retained_pairs,
    }

    if pixels < min_pixels:
        return AnalysisOutcome(
            status=STATUS_INCONCLUSIVE,
            action=ACTION_WARNING,
            indicators=indicators,
            limitations=_inconclusive_limitations(
                f"la imagen tiene {pixels} píxeles y el mínimo para un resultado fiable es {min_pixels}"
            ),
        )
    if distinct_values <= min_palette_colors:
        return AnalysisOutcome(
            status=STATUS_INCONCLUSIVE,
            action=ACTION_WARNING,
            indicators=indicators,
            limitations=_inconclusive_limitations(
                f"solo hay {distinct_values} valores distintos (paleta reducida o imagen sintética)"
            ),
        )
    if anomaly_score >= threshold and abs(ones_ratio - 0.5) > LSB_RATIO_TOLERANCE:
        return AnalysisOutcome(
            status=STATUS_INCONCLUSIVE,
            action=ACTION_WARNING,
            indicators=indicators,
            limitations=_inconclusive_limitations(
                "los indicadores se contradicen: el histograma imita una sustitución LSB pero "
                f"el plano LSB está desequilibrado (proporción de unos {ones_ratio:.3f})"
            ),
        )
    if anomaly_score >= threshold:
        return AnalysisOutcome(
            status=STATUS_SUSPICIOUS,
            action=ACTION_QUARANTINE,
            indicators=indicators,
            limitations=_suspicious_limitations(most_suspicious.pvalue, rate),
        )
    return AnalysisOutcome(
        status=STATUS_CLEAN,
        action=ACTION_NONE,
        indicators=indicators,
        limitations=_clean_limitations(most_suspicious.pvalue, threshold),
    )
