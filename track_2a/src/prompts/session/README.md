# Session prompt map

The default is `conversation_policy="baseline"`: v8 analysis/speaker conversation with v10 verified multilingual recap and optional practice. Code in `interview_controller.py` owns progression; `hybrid.py` handles the recap/practice tasks for all four languages. All roles use the same configured Apertus model.

| Task | Files | Inputs and use |
| --- | --- | --- |
| Analyse an answer | `analysis.txt`, `analysis.de.txt`, `.fr.txt`, `.it.txt` | Actual question, separate planned wording, stage/subtype, latest answer, dialogue and evidence records. Extracts quoted facts, completeness, a necessary gap, self-doubt and company intent. |
| Opening transitions | `opening_transitions.json` | Fixed German/French/Italian transitions for adequately answered greetings and self-introductions after analysis. Concerns, company questions and clarification bypass this shortcut. |
| Speak | `speaker.txt`, `speaker.de.txt`, `.fr.txt`, `.it.txt` | Code-approved action, validated analysis, actual answer, posting and next bank question. Writes a short reaction or bounded clarification; code appends advancing bank questions. Also handles company requests and support. |
| Demonstrations | `examples.<language>.json` | Small fictional stage/action-selected examples for analysis and speaking, adapted from organiser resources. Never evidence about the candidate. The generic trial-day-to-motivation `advance` demonstration is not injected; follow-up, company and support demonstrations remain. |
| Recap | `hybrid_evaluator.<language>.txt` (`en`, `de`, `fr`, `it`) | Criterion-scoped actual question–answer pairs, eligible evidence and public rubric. Separates assessment from proposed improvement gaps. |
| Verify improvement gaps | `hybrid_verify.<language>.txt` (`en`, `de`, `fr`, `it`) | Proposed gaps and complete answer context. Gap decisions cannot assign exercises. Uncertain/rejected gaps withhold dependent or negative ratings; explicitly independent positive assessments retain their quoted evidence. This model check is fallible. |
| Learning | `hybrid_learning.<language>.txt` (`en`, `de`, `fr`, `it`) | Only an explicit voluntary topic choice. Receives the actual question and complete original answer when available, and supplies one practice exercise without asserting a weakness. |
| Revision | `hybrid_revision.<language>.txt` (`en`, `de`, `fr`, `it`) | Assigned exercise, original answer, most recent accepted answer (`previous_answer`) and new revision. Compares against the previous answer and saves successful revisions for the next comparison. |
| Legacy recap | `feedback.txt`, `feedback.fr.txt`, `feedback.it.txt` | Used only with explicit `pipeline="legacy"`; not the default recap in any language. |
| Localised rules | `guidance.<language>.json`, `instructions.json`, `smalltalk.json` | Public rubric/guidelines, correction messages, fixed responses and neutral online openings. Technical JSON keys remain stable. |

Code checks exact quote presence, IDs, schemas, permitted questions and request budgets. These checks do not guarantee semantic accuracy. Each model task allows at most one correction, counted in the session budget. Server-owned traces record attempted requests. Scenario personas, simulator instructions, annotations and success criteria are excluded from coach input.

## Retained experimental policies

`hybrid_analysis.de.txt`, `hybrid_speaker.de.txt` and `hybrid_company.de.txt` support the opt-in fixed hybrid conversation. `hybrid_connected_analysis.de.txt`, `hybrid_connected_speaker.de.txt` and `question_variants.de.json` support the opt-in connected controller in `connected.py`. They are not the default conversation path. Existing `interviewer*` prompts are historical and not invoked by the default controller. `../web/` serves only the retained stateless API.

Saved learning targets can guide a later exercise; they are never evidence about a new candidate answer. Quotes and complete question context reduce unsupported claims but do not replace human validation.

`hybrid_ui.json` localises fixed recap explanations, failure responses and practice framing. `questions.en.json` supplements bank questions that have no English source text or existing browser translation; these translations are unreviewed. The evaluator receives the localised public rubric and feedback guidelines. The verifier, learning coach and revision task use the same language as the session.

`assessment_depends_on_gap` explicitly separates factual assessment from an improvement proposal. Low scores remain dependent for safety; independent positive scores require eligible quotes. Recap generates no learning request and creates no revision target until the user selects a voluntary topic. Unassessed criteria can still be offered as practice when the conversation contains an actual relevant answer; this is not an assessment of weakness.

Voluntary practice deliberately omits the evaluator’s score, explanation and improvement proposal from the learning target. These fields may contain unverified or rejected claims. The actual question, complete original answer and literal evidence remain available.
