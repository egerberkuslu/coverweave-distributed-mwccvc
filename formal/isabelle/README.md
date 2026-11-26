# NP-completeness of MWCCVC in Isabelle/HOL

This folder machine-checks the first claim of Theorem 1 of the paper: the decision version of MWCCVC, whether a
valid pair of weight at most B exists, is NP-complete. The proof reaches down to the Cook-Levin theorem, so no
step of the chain rests on a cited result.

The proof has two halves, both stated in the Turing-machine model of the Cook-Levin entry of the Archive of
Formal Proofs (Balbach).

| Statement | Theorem | File |
|---|---|---|
| MWCCVC is in NP: a 93-tape Turing machine checks a certificate in time 4·10⁶(2n+1)⁶ + 200n + 1000 | `MWCCVC_in_NP` | `CoverWeave_NP/verify/TM_Verify.thy` |
| SAT reduces to MWCCVC: a 30-tape transducer runs in time 2000(n+1)⁸ | `SAT_reducible_MWCCVC` | `CoverWeave_NP/reduce/TM_Reduce.thy` |
| MWCCVC is NP-complete | `MWCCVC_NP_complete` | `CoverWeave_NP/final/MWCCVC_NP_Complete.thy` |

The reduction runs SAT to independent set (Karp's gadget), then vertex cover by complement, then connected vertex
cover by adding a hub, then MWCCVC with unit weights and k at least the maximum degree. The middle steps are
proved inside the one transducer, because the Cook-Levin entry defines no vertex cover language.

## Modelling choices

* MWCCVC is a language of bit strings encoding [[k, B], weights, edge pairs]. Decoding is total: a weight of 0 is
  read as 1, and self-loops and out-of-range pairs are ignored. `canon_nll_correct` shows that a canonical
  encoding decodes to the instance it encodes.
* Weights are positive natural numbers, which covers rational weights after scaling. Real weights cannot be
  encoded finitely.
* The cover C is required to be nonempty. Connectivity of G is not needed, because the reduction graphs contain a
  hub and are connected.

## Not covered

The planar and maximum-degree-4 hardness, the APX and PTAS claims and the set-cover inapproximability of
Theorem 1 rest on cited results. The last two need the PCP theorem, which no proof assistant has formalized in
full.

## Checking the proofs

1. Install Isabelle2026 from <https://isabelle.in.tum.de>.
2. Download the Archive of Formal Proofs for Isabelle2026 from <https://www.isa-afp.org> and note the path of its
   `thys` folder, which contains the entry `Cook_Levin`.
3. Build:

       isabelle build -d <afp>/thys -d . -o threads=4 CoverWeave_NP

`build.sh` is the memory-capped wrapper we used (10 GB, 4 threads, an 8 GB ML heap). A clean build of the four
sessions takes about three minutes after the Cook_Levin heap exists, with a peak of 4.5 GB. No theory uses
`sorry`, `oops`, `axiomatization` or `quick_and_dirty`.
