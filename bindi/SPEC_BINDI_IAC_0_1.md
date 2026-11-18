# BINDI Inter-Agent Communication Specification v0.1 (`BINDI-IAC-0.1`)

**Status:** Isolated Prototype & Grammar Harmonization (aligned with `BINDI-MASTER-1.0`, `BinDinG Core V1`, `bindi_protocol.py` v0.1, `bindi_grammar.py` v0.2, `BINDING Q4`, `BPDQ-Lang` v1.0, `BINDY 1`, and `QBDP`).

## 1. Compatibility Alignment with Existing Bindi Grammar

ChatGPT's `BINDI.MSG.0001` draft was evaluated read-only against all 7 existing Bindi / BinDinG language families:

| Construct in `BINDI.MSG.0001` | Existing Bindi Precedent | Classification & Evolution in `BINDI-IAC-0.1` |
| --- | --- | --- |
| Box-drawing banner (`╔══...══╗`) & `#` comments | `BPDQ-Lang` (`#`), `BINDY 1` header | Preserved as lossless `BANNER` / `COMMENT` tokens |
| `BLOCK [TARGET] { ... }` | `BINDY 1` (`ENTITY ... END`), `BINDING Q4` AST, `BinDinG Core V1` macro blocks (`B`, `D`, `G`) | Canonical macro-envelope (`B -> D -> G -> B`) |
| `LINK A <-> B <-> C { ... }` | `BPDQ-Lang` `<->` relation operator (`q LINK A <-> B`) | Canonical multi-hop agent transport header |
| Repeated keys (`SOURCE = BAUSTEIN_01`, `SOURCE = BAUSTEIN_02`, `OBSERVE = ...`) | `RawSignalStore` multi-signal lists | Preserved as ordered multi-value lists per block |
| Bare slot keywords (`BINDI_PROTOCOL`, `REPORT`, `ACKNOWLEDGE`) | `GrammarRegistry` required-field declarations | Parsed as `SlotDeclEntry` schema requirements |
| `STATE = ...` (single string in prose) | `BINDING_LANGUAGE_RECONSTRUCTION_V1.md` Conflict #2 | Canonical `STATE` blocks MUST separate `LIFECYCLE_STATE`, `EPISTEMIC_STATE`, `Q4_PHASE`, and `DIALOGUE_STATE` |
| Implicit timestamp & checksums | `binding_bdg_core.py` (`+01:00` + `BDG-0`), `bindi_bridge_secure.py` (Dual-Hash) | `STRICT_CANONICAL` adds explicit ISO-8601 TZ `TIMESTAMP` + `PROVENANCE` (`BDG_ZERO_HASH`, `PREV_HASH`, `SEMANTIC_SHA256`, `IN_REPLY_TO`) |
| Flat facts/interpretations | `bindi_protocol.py` (`FACT`, `PATTERN`, `HYPOTHESIS`) | `EVIDENCE` blocks require `RECORD_KIND = FACT \| PATTERN \| HYPOTHESIS` |

## 2. EBNF Grammar (`BINDI-IAC-0.1`)

```ebnf
message       := banner* (block | comment)* "END" "MESSAGE" comment* EOF ;
banner        := BOX_DRAWING_LINE ;
block         := IDENT [ IDENT | link_chain ] "{" entry* "}" ;
link_chain    := IDENT ( "<->" IDENT )+ ;
entry         := kv_entry | slot_entry ;
kv_entry      := IDENT "=" ( ATOM | STRING | AT_COORD ) ;
slot_entry    := IDENT ;
```

## 3. Validation Profiles

1. **`DRAFT_COMPAT` (Ingest / RawSignalStore):** Accepts incoming drafts like `BINDI.MSG.0001` losslessly while requiring valid block syntax, `IDENTITY` metadata (`SYSTEM`, `SENDER`, `RECEIVER`, `LANGUAGE = BINDI`, `MESSAGE_ID`), and `END MESSAGE`.
2. **`STRICT_CANONICAL` (Verified Outbound / Inter-Agent Responses like `BINDI.ACK.0001`):** Additionally enforces explicit ISO-8601 timezone offset (`TIMESTAMP`), `PROVENANCE` with self-consistent `SEMANTIC_SHA256` & `BDG_ZERO_HASH`, orthogonal 3-axis `STATE` fields, and explicit `RECORD_KIND` in `EVIDENCE`.

## 4. Dual-Hash Integrity & Safety Rules

- `RAW_SHA256`: SHA-256 of `\n`-normalized UTF-8 message text.
- `SEMANTIC_SHA256`: SHA-256 of sorted compact canonical JSON (`canonical_json`) of all AST blocks and entries, omitting `PROVENANCE.RAW_SHA256` and `PROVENANCE.SEMANTIC_SHA256` so the message self-authenticates against semantic tampering.
- `CORE_STATE = PROTECTED`: Readers open SQLite WAL stores strictly via `file:...?mode=ro` with write-deny authorizer.
- `MAIN_BRANCH = PROTECTED`: All inter-agent GitHub artifacts live exclusively on feature branches (e.g. `feature/bindi-communication-01`) and unmerged Pull Requests.
