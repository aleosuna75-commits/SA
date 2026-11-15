# -*- coding: utf-8 -*-
"""
Codigo de evaluacion de las variantes `forma_1` y `forma_2` (MERCADOS_ENSAMBLE.md, seccion 8).
No toca produccion.

Matriz con dispersion libre: cada marginal es Conway-Maxwell-Poisson truncada en 0..10 con la MISMA media
que la Poisson truncada del modelo y exponente nu (nu = 1 -> la Poisson de hoy), con la correccion de
Dixon-Coles del modelo, un factor de dependencia exp(kappa * (x - lam_l) * (y - lam_v) / raiz(lam_l lam_v))
y, al final, el 1X2 reescalado al del modelo (regiones local / empate / visita).
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "/home/user/SA/ligamx")
from modelo import arnes                                   # noqa: E402

N = arnes.MAX_GOLES + 1
K = np.arange(N, dtype=float)
LF = np.array([0.0] + list(np.cumsum(np.log(np.arange(1, N)))))        # ln k!
_X, _Y = np.meshgrid(K, K, indexing="ij")
GANA_L = (_X > _Y).astype(float)
EMPATE = (_X == _Y).astype(float)
GANA_V = (_X < _Y).astype(float)


def poisson_truncada(lam) -> np.ndarray:
    lam = np.atleast_1d(np.asarray(lam, float))
    p = np.exp(K[None, :] * np.log(lam)[:, None] - lam[:, None] - LF[None, :])
    return p / p.sum(axis=1, keepdims=True)


def marginal_cmp(lam, nu) -> np.ndarray:
    """(n, 11): P(k) proporcional a exp(k t - nu ln k!), con t tal que la media sea la de la Poisson truncada."""
    lam = np.atleast_1d(np.asarray(lam, float))
    nu = np.broadcast_to(np.asarray(nu, float), lam.shape)
    m = (poisson_truncada(lam) * K).sum(axis=1)
    t = nu * np.log(lam)
    for _ in range(60):
        a = K[None, :] * t[:, None] - nu[:, None] * LF[None, :]
        a -= a.max(axis=1, keepdims=True)
        f = np.exp(a)
        f /= f.sum(axis=1, keepdims=True)
        mu = (f * K).sum(axis=1)
        var = (f * K * K).sum(axis=1) - mu * mu
        paso = np.clip((m - mu) / np.maximum(var, 1e-12), -1.0, 1.0)
        t = t + paso
        if np.max(np.abs(paso)) < 1e-13:
            break
    a = K[None, :] * t[:, None] - nu[:, None] * LF[None, :]
    a -= a.max(axis=1, keepdims=True)
    f = np.exp(a)
    f /= f.sum(axis=1, keepdims=True)
    if np.max(np.abs((f * K).sum(axis=1) - m)) > 1e-9:
        raise AssertionError("la media de la marginal no convergio")
    return f


def tau(lam_l, lam_v, rho) -> np.ndarray:
    """Factores de Dixon-Coles (n, 11, 11), los mismos de arnes.matrices_marcadores."""
    n = len(lam_l)
    T = np.ones((n, N, N))
    T[:, 0, 0] = np.clip(1.0 - lam_l * lam_v * rho, 1e-10, None)
    T[:, 0, 1] = np.clip(1.0 + lam_l * rho, 1e-10, None)
    T[:, 1, 0] = np.clip(1.0 + lam_v * rho, 1e-10, None)
    T[:, 1, 1] = np.clip(1.0 - rho, 1e-10, None)
    return T


def p1x2(M) -> np.ndarray:
    return np.stack([(M * GANA_L).sum(axis=(1, 2)), (M * EMPATE).sum(axis=(1, 2)), (M * GANA_V).sum(axis=(1, 2))], axis=1)


def fijar_1x2(M, p) -> np.ndarray:
    """Reescala las tres regiones de cada matriz para que su 1X2 sea p (version por lote de arnes.ajustar_M_a_1x2)."""
    q = p1x2(M)
    r = p / q
    R = M * (GANA_L[None] * r[:, 0, None, None] + EMPATE[None] * r[:, 1, None, None] + GANA_V[None] * r[:, 2, None, None])
    return R / R.sum(axis=(1, 2), keepdims=True)


def phi(lam_l, lam_v) -> np.ndarray:
    return ((K[None, :, None] - lam_l[:, None, None]) * (K[None, None, :] - lam_v[:, None, None])
            / np.sqrt(lam_l * lam_v)[:, None, None])


def matrices_forma(lam_l, lam_v, rho, nu=1.0, kappa=0.0, p_fijo=None) -> np.ndarray:
    """Matrices (n, 11, 11) corregidas. Con nu = 1 y kappa = 0 es arnes.matrices_marcadores."""
    lam_l = np.atleast_1d(np.asarray(lam_l, float))
    lam_v = np.atleast_1d(np.asarray(lam_v, float))
    rho = np.broadcast_to(np.asarray(rho, float), lam_l.shape)
    nu = np.broadcast_to(np.asarray(nu, float), lam_l.shape)
    kappa = np.broadcast_to(np.asarray(kappa, float), lam_l.shape)
    fl, fv = marginal_cmp(lam_l, nu), marginal_cmp(lam_v, nu)
    M = fl[:, :, None] * fv[:, None, :] * tau(lam_l, lam_v, rho)
    if np.any(kappa != 0):
        M = M * np.exp(kappa[:, None, None] * phi(lam_l, lam_v))
    M = M / M.sum(axis=(1, 2), keepdims=True)
    if p_fijo is None:
        p_fijo = arnes.p1x2(arnes.matrices_marcadores(lam_l, lam_v, rho))
    return fijar_1x2(M, np.asarray(p_fijo, float))


def malla_logv(lam_l, lam_v, rho, gl, gv, nus, kappas) -> np.ndarray:
    """ln P(marcador observado) de cada partido para cada (nu, kappa) de la malla: (len(nus), len(kappas), n)."""
    lam_l, lam_v, rho = (np.asarray(a, float) for a in (lam_l, lam_v, rho))
    n = len(lam_l)
    gl = np.minimum(np.asarray(gl, int), N - 1)
    gv = np.minimum(np.asarray(gv, int), N - 1)
    p = arnes.p1x2(arnes.matrices_marcadores(lam_l, lam_v, rho))
    T = tau(lam_l, lam_v, rho)
    F = phi(lam_l, lam_v)
    ix = np.arange(n)
    out = np.empty((len(nus), len(kappas), n))
    for i, nu in enumerate(nus):
        fl, fv = marginal_cmp(lam_l, nu), marginal_cmp(lam_v, nu)
        B = fl[:, :, None] * fv[:, None, :] * T
        for j, ka in enumerate(kappas):
            M = B * np.exp(ka * F) if ka != 0 else B
            M = M / M.sum(axis=(1, 2), keepdims=True)
            M = fijar_1x2(M, p)
            out[i, j] = np.log(M[ix, gl, gv])
    return out


def _vertice(y0, y1, y2) -> float:
    """Desplazamiento (en pasos de malla, entre -0.5 y 0.5) del maximo de la parabola por tres puntos."""
    den = y0 - 2.0 * y1 + y2
    if not np.isfinite(den) or den >= 0:
        return 0.0
    return float(np.clip(0.5 * (y0 - y2) / den, -0.5, 0.5))


def maximo_malla(S, nus, kappas) -> tuple[float, float]:
    """Maximo de S (len(nus), len(kappas)) refinado con una parabola por eje."""
    i, j = np.unravel_index(int(np.argmax(S)), S.shape)
    nu, ka = float(nus[i]), float(kappas[j])
    if 0 < i < len(nus) - 1:
        nu += _vertice(S[i - 1, j], S[i, j], S[i + 1, j]) * float(nus[1] - nus[0])
    if len(kappas) > 1 and 0 < j < len(kappas) - 1:
        ka += _vertice(S[i, j - 1], S[i, j], S[i, j + 1]) * float(kappas[1] - kappas[0])
    return nu, ka
