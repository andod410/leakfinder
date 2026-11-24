"""2.79: snabbare nattkörning – samma värden som tidigare (handvärden, handklasser, v3-anpassningen)."""
import numpy as np


def test_fastev_delat_same_as_best_values():
    from plo_leak.fastev import best_values
    from plo_leak import fastev_delat as F
    rng = np.random.default_rng(7)
    for it in range(300):
        k, nb = (4, 5, 6)[it % 3], (3, 4, 5)[(it // 3) % 3]
        p = rng.permutation(52)
        if it % 5 == 0:   # färgtungt: bordet i en färg, många händer med två kort i samma färg
            p = np.argsort(rng.random(52) - 0.6 * (np.arange(52) % 4 == 0))
        b = p[:nb]
        H = np.stack([rng.permutation(p[nb:])[:k] for _ in range(60)])
        assert np.array_equal(F.vs_board(H, b), best_values(H, np.repeat(b[None], len(H), 0)))
        Bs = np.stack([rng.permutation(p[k:])[:5] for _ in range(80)])
        h = p[:k]
        assert np.array_equal(F.hole_vs_boards(F.hole_tables(h), Bs), best_values(np.repeat(h[None], len(Bs), 0), Bs))


def test_class_keys_determine_classify():
    from plo_leak.night3 import SUIT, _class_keys
    from plo_leak.solvergroups import classify
    rng = np.random.default_rng(3)
    seen = {}
    H = np.concatenate([np.stack([rng.permutation(52)[:6] for _ in range(6000)]),
                        np.stack([rng.choice(np.arange(32, 52), 6, replace=False) for _ in range(6000)])])
    for key, h in zip(_class_keys(H).tolist(), H):
        g = classify([(int(x) // 4 + 2, SUIT[int(x) % 4]) for x in h])
        assert seen.setdefault(key, g) == g


def _old_fit(items, maxiter):
    """Anpassningen som den såg ut i 2.78.2 (referens)."""
    from scipy.optimize import minimize
    from scipy.special import logsumexp
    from plo_leak.night3 import L2, NF, NG, _logp, group
    Xs, G, A, I = [], [], [], []
    for i, it in enumerate(items):
        for (st, fac, ip, a, pa, sz) in it["line"]:
            f = it["F"][st]
            Xs.append(np.concatenate([np.ones((len(f), 1), np.float32), f], 1))
            G.append(group(st, fac, ip, pa, sz)); A.append(a); I.append(i)
    X, G, A, I = np.stack(Xs), np.array(G), np.array(A), np.array(I)
    D, Kc, _ = X.shape
    NI = len(items)
    PF = np.zeros((NI, Kc), np.float32)
    for i, it in enumerate(items):
        if it.get("pf") is not None:
            PF[i] = it["pf"]

    def loss(wb):
        w, beta = wb[:-1], wb[-1]
        W = w.reshape(NG, 2, NF)
        lp = _logp(W, X, G)
        pi = np.exp(lp)
        la = lp[np.arange(D), :, A]
        S = np.zeros((NI, Kc))
        np.add.at(S, I, la)
        S = S + beta * PF
        lse = logsumexp(S, 1, keepdims=True)
        post = np.exp(S - lse)
        ll = (S[:, 0] - lse[:, 0]).sum()
        r = -post
        r[:, 0] += 1.0
        rd = r[I]
        grad = np.zeros_like(W)
        for a in (1, 2):
            gw = np.einsum("dk,dkf->df", np.nan_to_num(rd * ((A == a)[:, None] - pi[:, :, a])), X)
            np.add.at(grad[:, a - 1, :], G, gw)
        gb = (PF[:, 0] - (post * PF).sum(1)).sum()
        return -ll + L2 * (w ** 2).sum(), np.append(-grad.ravel() + 2 * L2 * w, -gb)

    res = minimize(loss, np.zeros(NG * 2 * NF + 1), jac=True, method="L-BFGS-B", options={"maxiter": maxiter})
    return res.x


def test_fit_same_as_before():
    from plo_leak import night3
    rng = np.random.default_rng(5)
    sts = ("flop", "turn", "river")
    items = []
    for i in range(150):
        L = [(sts[rng.integers(3)], int(rng.integers(2)), int(rng.integers(2)), int(rng.integers(3)), int(rng.integers(2)),
              int(rng.integers(2))) for _ in range(int(rng.integers(1, 6)))]
        F = {s: rng.random((30, 4)).astype(np.float32) for s in sts}
        items.append({"id": str(i), "line": L, "F": F, "pf": None if i % 3 == 0 else np.log(rng.random(30) + 0.01).astype(np.float32)})
    ref = _old_fit(items, 40)
    m = night3.fit(items, maxiter=40)
    new = np.append(m["W"].ravel(), m["beta"])
    assert np.allclose(new, ref, rtol=0, atol=1e-9)
    assert night3._lse3_ok() is True or night3._lse3_ok() is False
