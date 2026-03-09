"""Essentia audio analysis microservice.

Accepts audio file uploads and returns acoustic descriptors used by
Lyra Oracle for score validation and enrichment.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict

import numpy as np
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="Lyra Essentia Service", version="1.0.0")


def _analyze(filepath: str) -> Dict[str, Any]:
    """Run Essentia extractors on an audio file and return raw descriptors."""
    import essentia
    import essentia.standard as es

    audio = es.MonoLoader(filename=filepath, sampleRate=44100)()

    results: Dict[str, Any] = {}

    # Loudness
    try:
        loudness = es.Loudness()(audio)
        results["loudness"] = float(loudness)
    except Exception:
        pass

    # Dynamic complexity
    try:
        dc, dc_loudness = es.DynamicComplexity()(audio)
        results["dynamic_complexity"] = float(dc)
    except Exception:
        pass

    # Danceability
    try:
        danceability, _ = es.Danceability()(audio)
        results["danceability"] = float(danceability)
    except Exception:
        pass

    # Spectral centroid (mean)
    try:
        spec = es.SpectralCentroidTime()(audio)
        results["spectral_centroid"] = float(spec)
    except Exception:
        pass

    # Spectral complexity (via frame-by-frame)
    try:
        frame_gen = es.FrameGenerator(audio, frameSize=2048, hopSize=1024)
        windowing = es.Windowing(type="hann")
        spectrum_algo = es.Spectrum()
        sc_algo = es.SpectralComplexity()
        complexities = []
        for frame in frame_gen:
            spec = spectrum_algo(windowing(frame))
            complexities.append(sc_algo(spec))
        if complexities:
            results["spectral_complexity"] = float(np.mean(complexities))
    except Exception:
        pass

    # Spectral flatness (via frame-by-frame)
    try:
        frame_gen = es.FrameGenerator(audio, frameSize=2048, hopSize=1024)
        windowing = es.Windowing(type="hann")
        spectrum_algo = es.Spectrum()
        flatness_algo = es.Flatness()
        flatnesses = []
        for frame in frame_gen:
            spec = spectrum_algo(windowing(frame))
            flatnesses.append(flatness_algo(spec))
        if flatnesses:
            results["spectral_flatness"] = float(np.mean(flatnesses))
    except Exception:
        pass

    # Dissonance (via frame-by-frame spectral peaks)
    try:
        frame_gen = es.FrameGenerator(audio, frameSize=2048, hopSize=1024)
        windowing = es.Windowing(type="hann")
        spectrum_algo = es.Spectrum()
        peaks_algo = es.SpectralPeaks()
        diss_algo = es.Dissonance()
        dissonances = []
        for frame in frame_gen:
            spec = spectrum_algo(windowing(frame))
            freqs, mags = peaks_algo(spec)
            if len(freqs) > 1:
                dissonances.append(diss_algo(freqs, mags))
        if dissonances:
            results["dissonance"] = float(np.mean(dissonances))
    except Exception:
        pass

    # Rhythm (BPM)
    try:
        bpm, ticks, confidence, estimates, intervals = es.RhythmExtractor2013()(audio)
        results["bpm"] = float(bpm)
        results["bpm_confidence"] = float(confidence)
    except Exception:
        pass

    # Key
    try:
        key, scale, strength = es.KeyExtractor()(audio)
        results["key"] = key
        results["scale"] = scale
        results["key_strength"] = float(strength)
    except Exception:
        pass

    # Average loudness (normalized 0-1)
    try:
        avg_loud = es.LoudnessEBUR128()(audio)
        results["integrated_loudness"] = float(avg_loud[0])
    except Exception:
        pass

    return results


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "essentia"}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    """Analyze an uploaded audio file and return acoustic descriptors."""
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        descriptors = _analyze(tmp_path)
        return JSONResponse(content={"success": True, "descriptors": descriptors})
    except Exception as exc:
        logger.exception("Analysis failed")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(exc)},
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)
